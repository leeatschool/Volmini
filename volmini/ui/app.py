"""Main Application State Machine and Controller for Volmini (ESP32 MicroPython Edition)."""

import os
from volmini.compat import ticks_ms, ticks_diff, gc_collect, path_exists, makedirs_safe
from volmini.hal.base import KeyCode, KeyEvent
from volmini.core.document_model import (
    PageLayoutModel, PaperSizePreset, Orientation, PageMargins, DocumentMode
)
from volmini.core.header_footer import HeaderFooterModel
from volmini.core.rich_doc import RichDocument, Paragraph, TextSpan
from volmini.core.page_layout import PrintPaginationEngine
from volmini.core.io_manager import IOManager
from volmini.core.ble_beam import BLEBeamEngine, BLEBeamMode
from volmini.navigator.outline import OutlineNavigator
from volmini.review.lens_engine import RevisionLensEngine
from volmini.review.spell_engine import SpellCheckEngine
from volmini.reference.compendium import StrippedCompendium
from volmini.companion.corvus import CorvusCompanion
from volmini.ui.splash_screen import BootSplashRenderer
from volmini.ui.page_renderer import PageRenderer
from volmini.ui.overlays import OverlayRenderer


class ViewState:
    BOOT_SPLASH = "boot_splash"
    LAUNCHER = "launcher"
    EDITOR = "editor"
    OUTLINE = "outline"
    REFERENCE = "reference"
    REVIEW = "review"
    CORVUS = "corvus"
    BLE_BEAM = "ble_beam"
    PAGE_SETUP = "page_setup"
    FILE_BROWSER = "file_browser"
    EXPORT_DIALOG = "export_dialog"
    HELP = "help"


class VolminiApp:
    """Standalone embedded word processing & codex studio controller."""

    AUTOSAVE_INTERVAL_MS = 30_000  # Atomic autosave every 30s if dirty

    def __init__(self, hal, data_dir: str = None):
        self.hal = hal
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = data_dir or os.path.join(base_dir, "data")

        self.view = ViewState.BOOT_SPLASH
        self.doc = RichDocument()
        self.layout_model = PageLayoutModel()
        self.hf_model = HeaderFooterModel()
        self.document_mode = DocumentMode.CREATIVE_FICTION
        self.story_title = "Untitled Manuscript"
        self.story_author = "Author"
        self.active_file_path = f"{self.hal.storage_root.rstrip('/')}/manuscript.md"

        # Subsystems
        self.outline = OutlineNavigator()
        self.compendium = StrippedCompendium(
            index_path=os.path.join(self.data_dir, "ref_index.json"),
            data_path=os.path.join(self.data_dir, "ref_data.txt"),
        )
        self.spell_engine = SpellCheckEngine(
            dict_file_path=os.path.join(self.data_dir, "dict_words.txt"),
            user_dict_path=os.path.join(self.data_dir, "user_dict.json"),
        )
        self.corvus = CorvusCompanion()
        self.ble_beam = BLEBeamEngine()

        # Cached pagination & review state
        self.pages = []
        self.cursor_loc = (0, 0, 0)
        self.enabled_lenses = {
            "adverb": True,
            "passive": True,
            "filler": True,
            "pacing": False,
            "spelling": True,
        }
        self.show_lens_highlights = False
        self.findings = []

        # UI Selection indices for modal overlays & Dynamic Top Ribbon
        self.show_ribbon = True
        self.ribbon_hitboxes = []
        self.line_hitboxes = []
        self.launcher_idx = 0
        self.outline_idx = 0
        self.ref_query = ""
        self.ref_cat_idx = 0
        self.ref_results = []
        self.ref_selected_idx = 0
        self.ref_reading_stub = None
        self.ref_reading_body = ""
        self.ref_scroll_line = 0
        self.review_idx = 0
        self.page_setup_idx = 0
        self.browser_files = []
        self.browser_idx = 0

        self.status_toast = ""
        self.toast_expire_ms = 0
        self.last_autosave_ms = ticks_ms()
        self._sync_display_geometry()

    def _sync_display_geometry(self) -> None:
        """Adapts printable column cap to the physical display width (e.g. 800x480 GDEY075T7 vs 400x240)."""
        w = self.hal.width
        sheet_margin_x = max(6, w // 50)
        sheet_w = w - sheet_margin_x * 2
        raw_w_in, _ = self.layout_model.raw_dimensions_inches
        left_ratio = self.layout_model.margins.left / max(4.0, raw_w_in)
        right_ratio = self.layout_model.margins.right / max(4.0, raw_w_in)
        pad_left = max(10, int(round(sheet_w * left_ratio * 0.65)))
        pad_right = max(10, int(round(sheet_w * right_ratio * 0.65)))
        content_w = max(120, sheet_w - pad_left - pad_right)
        max_cols_fit = max(28, min(96, (content_w - 8) // 6))
        self.layout_model.viewport_scale_cols = max_cols_fit

    def set_toast(self, msg: str, duration_ms: int = 3500) -> None:
        self.status_toast = msg
        self.toast_expire_ms = ticks_ms() + duration_ms

    # --- Power-On Boot Initiating Sequence & Session Resume ---

    def run_boot_sequence(self, interactive_wait: bool = False) -> None:
        """Executes the hardware & index initialization sequence on the Boot Splash Screen."""
        self.view = ViewState.BOOT_SPLASH
        session = IOManager.load_session_state(self.hal.storage_root)
        resume_file = session.get("active_file", "")

        steps = [
            (25, f"[1/4] Mounting storage ({self.hal.storage_root})..."),
            (55, "[2/4] Indexing stripped Writer's Reference Compendium..."),
            (80, "[3/4] Initializing Spell Check & Revision Lenses..."),
            (100, "[4/4] Restoring manuscript session..."),
        ]

        for pct, msg in steps:
            BootSplashRenderer.render(self.hal.fb, status_text=msg, progress_pct=pct, resume_filename=resume_file)
            self.hal.present()
            if pct == 55:
                self.compendium.ensure_loaded()
            elif pct == 100:
                self._ensure_starter_manuscript(resume_file, session)
            gc_collect()

        # Check if user pressed SPACE during boot to open Document Launcher
        ev = self.hal.poll_key()
        if ev and (ev.key == " " or ev.char == " "):
            self.view = ViewState.LAUNCHER
        elif not interactive_wait:
            self.view = ViewState.EDITOR

        self.relayout()
        self.render()

    def _ensure_starter_manuscript(self, resume_file: str, session: dict) -> None:
        if resume_file and path_exists(resume_file):
            self.open_document(resume_file)
            if self.doc.to_plain_text().strip():
                if "cursor_para" in session and "cursor_offset" in session:
                    self.doc.cursor_para = int(session.get("cursor_para", 0))
                    self.doc.cursor_offset = int(session.get("cursor_offset", 0))
                    self.doc._clamp_cursor()
                return

        default_path = f"{self.hal.storage_root.rstrip('/')}/manuscript.md"
        if path_exists(default_path):
            self.open_document(default_path)
            if self.doc.to_plain_text().strip():
                return

        # Create clean starter manuscript
        self.active_file_path = default_path
        self.doc.from_markdown(
            "# The Uncharted Ledger\n"
            "## Chapter 1\n"
            "The **brass lantern** swayed above the *chart table* as the harbor bell tolled."
        )
        self.doc.cursor_para = 2
        self.doc.cursor_offset = len(self.doc.paragraphs[2])
        self.save_now()

    def open_document(self, file_path: str) -> bool:
        meta = IOManager.load_document(file_path, self.doc)
        self.active_file_path = file_path
        if meta:
            self.document_mode = meta.get("document_mode", DocumentMode.CREATIVE_FICTION)
            self.story_title = meta.get("story_title", "Untitled")
            self.story_author = meta.get("story_author", "")
            self.layout_model = PageLayoutModel.from_dict(meta.get("layout"))
            self.hf_model = HeaderFooterModel.from_dict(meta.get("header_footer"))
            self.outline.load_statuses(meta.get("chapter_statuses", {}))
            self.corvus.set_document_mode(self.document_mode)
        self.outline.scan(self.doc)
        self.relayout()
        return True

    def save_now(self) -> bool:
        self.outline.scan(self.doc)
        ok = IOManager.save_document(
            self.active_file_path,
            self.doc,
            layout=self.layout_model,
            hf_model=self.hf_model,
            document_mode=self.document_mode,
            chapter_statuses=self.outline.export_statuses(),
            story_title=self.story_title,
            story_author=self.story_author,
        )
        if ok:
            IOManager.save_session_state(
                self.hal.storage_root,
                self.active_file_path,
                self.doc.cursor_para,
                self.doc.cursor_offset,
            )
            self.last_autosave_ms = ticks_ms()
            self.set_toast("Saved atomically.")
        return ok

    # --- Layout & Revision Analysis ---

    def relayout(self) -> None:
        self._sync_display_geometry()
        self.pages = PrintPaginationEngine.paginate(
            self.doc,
            self.layout_model,
            self.hf_model,
            story_title=self.story_title,
            story_author=self.story_author,
        )
        self.cursor_loc = PrintPaginationEngine.find_cursor_location(
            self.pages, self.doc.cursor_para, self.doc.cursor_offset
        )
        if self.show_lens_highlights:
            self.run_review_scan(active_para_only=True)

    def run_review_scan(self, active_para_only: bool = False) -> list:
        """Runs Revision Lenses and binary-searched Spell Check."""
        findings = []
        if active_para_only:
            p_idx = self.doc.cursor_para
            p_txt = self.doc.paragraphs[p_idx].text
            findings.extend(RevisionLensEngine.analyze_paragraph(p_idx, p_txt, self.enabled_lenses))
            if self.enabled_lenses.get("spelling", True):
                findings.extend(self.spell_engine.check_paragraph(p_idx, p_txt))
        else:
            for p_idx, para in enumerate(self.doc.paragraphs):
                p_txt = para.text
                if not p_txt:
                    continue
                findings.extend(RevisionLensEngine.analyze_paragraph(p_idx, p_txt, self.enabled_lenses))
                if self.enabled_lenses.get("spelling", True):
                    findings.extend(self.spell_engine.check_paragraph(p_idx, p_txt))
        self.findings = findings
        return findings

    # --- Periodic Tick & Rendering ---

    def tick(self) -> None:
        now = ticks_ms()
        self.corvus.tick(now)
        if self.status_toast and ticks_diff(now, self.toast_expire_ms) >= 0:
            self.status_toast = ""

        # Atomic Autosave check
        if self.doc.dirty and ticks_diff(now, self.last_autosave_ms) >= self.AUTOSAVE_INTERVAL_MS:
            self.save_now()

        dirty_ui = False
        ev = self.hal.poll_key()
        if ev is not None:
            self.handle_key_event(ev)
            dirty_ui = True

        pev = self.hal.poll_pointer()
        if pev is not None:
            self.handle_pointer_event(pev)
            dirty_ui = True

        if dirty_ui:
            self.render()

    def render(self) -> None:
        fb = self.hal.fb
        if self.view == ViewState.BOOT_SPLASH:
            session = IOManager.load_session_state(self.hal.storage_root)
            BootSplashRenderer.render(
                fb,
                status_text="System Ready.",
                progress_pct=100,
                resume_filename=session.get("active_file", ""),
            )
            self.hal.present()
            return

        pointer_pos = (self.hal.pointer_x, self.hal.pointer_y) if self.hal.pointer_visible else None

        # Always render the print-accurate editor underneath overlays
        PageRenderer.render_editor(
            fb=fb,
            doc=self.doc,
            pages=self.pages,
            cursor_loc=self.cursor_loc,
            layout_model=self.layout_model,
            document_mode=self.document_mode,
            corvus=self.corvus,
            active_filename=self.active_file_path,
            findings=self.findings,
            show_lenses=self.show_lens_highlights,
            battery_pct=self.hal.battery_percent(),
            status_toast=self.status_toast,
            show_ribbon=self.show_ribbon,
            pointer_pos=pointer_pos,
            hitboxes=self.ribbon_hitboxes,
            line_hitboxes=self.line_hitboxes,
        )

        # Render active modal overlay if not in base EDITOR state
        if self.view == ViewState.LAUNCHER:
            OverlayRenderer.render_launcher(fb, self.launcher_idx, self.active_file_path)
        elif self.view == ViewState.OUTLINE:
            total_w = len(self.doc.to_plain_text().split())
            OverlayRenderer.render_outline(fb, self.outline.items, self.outline_idx, total_w)
        elif self.view == ViewState.REFERENCE:
            cats = self.compendium.get_categories()
            cat_name = cats[self.ref_cat_idx % len(cats)] if cats else "All Categories"
            OverlayRenderer.render_reference(
                fb,
                self.ref_query,
                cat_name,
                self.ref_results,
                self.ref_selected_idx,
                self.ref_reading_stub,
                self.ref_reading_body,
                self.ref_scroll_line,
            )
        elif self.view == ViewState.REVIEW:
            OverlayRenderer.render_review(
                fb, self.findings, self.review_idx, self.enabled_lenses, self.show_lens_highlights
            )
        elif self.view == ViewState.CORVUS:
            total_w = len(self.doc.to_plain_text().split())
            OverlayRenderer.render_corvus(fb, self.corvus, total_w)
        elif self.view == ViewState.BLE_BEAM:
            plain = self.doc.to_plain_text()
            short_name = self.active_file_path.replace("\\", "/").split("/")[-1]
            OverlayRenderer.render_ble_beam(fb, self.ble_beam, short_name, len(plain))
        elif self.view == ViewState.PAGE_SETUP:
            OverlayRenderer.render_page_setup(
                fb, self.layout_model, self.hf_model, self.document_mode, self.page_setup_idx
            )
        elif self.view == ViewState.FILE_BROWSER:
            OverlayRenderer.render_file_browser(
                fb, self.hal.storage_root, self.browser_files, self.browser_idx, is_export=False
            )
        elif self.view == ViewState.EXPORT_DIALOG:
            OverlayRenderer.render_file_browser(
                fb, self.hal.storage_root, self.browser_files, self.browser_idx, is_export=True
            )
        elif self.view == ViewState.HELP:
            OverlayRenderer.render_help(fb)

        # Render monochrome pointer arrow cursor on top when active
        if self.hal.pointer_visible:
            PageRenderer.draw_pointer_cursor(fb, self.hal.pointer_x, self.hal.pointer_y)

        self.hal.present()

    # --- Keyboard Dispatch ---

    def handle_key_event(self, ev: KeyEvent) -> None:
        if self.view == ViewState.BOOT_SPLASH:
            if ev.key == " " or ev.char == " ":
                self.view = ViewState.LAUNCHER
            else:
                self.view = ViewState.EDITOR
            return

        # Global Function Key Overlay Toggles
        if ev.key == KeyCode.F1_HELP:
            self.view = ViewState.EDITOR if self.view == ViewState.HELP else ViewState.HELP
            return
        if ev.key == KeyCode.F2_OUTLINE:
            if self.view == ViewState.OUTLINE:
                self.view = ViewState.EDITOR
            else:
                self.outline.scan(self.doc)
                self.outline_idx = 0
                self.view = ViewState.OUTLINE
            return
        if ev.key == KeyCode.F3_REFERENCE:
            if self.view == ViewState.REFERENCE:
                self.view = ViewState.EDITOR
            else:
                self._refresh_reference_search()
                self.view = ViewState.REFERENCE
            return
        if ev.key == KeyCode.F4_REVIEW:
            if self.view == ViewState.REVIEW:
                self.view = ViewState.EDITOR
            else:
                self.run_review_scan(active_para_only=False)
                self.review_idx = 0
                self.view = ViewState.REVIEW
            return
        if ev.key == KeyCode.F5_CORVUS:
            self.view = ViewState.EDITOR if self.view == ViewState.CORVUS else ViewState.CORVUS
            return
        if ev.key == KeyCode.F6_BLE_BEAM:
            if self.view == ViewState.BLE_BEAM:
                self.ble_beam.stop_radio()
                self.view = ViewState.EDITOR
            else:
                self.ble_beam.stop_radio()
                self.view = ViewState.BLE_BEAM
            return
        if ev.key == KeyCode.F7_PAGE_SETUP:
            self.view = ViewState.EDITOR if self.view == ViewState.PAGE_SETUP else ViewState.PAGE_SETUP
            return
        if ev.key == KeyCode.F8_RIBBON:
            self.show_ribbon = not self.show_ribbon
            self.set_toast(f"Top Ribbon: {'ON' if self.show_ribbon else 'OFF'}")
            return

        # Route to active view handler
        if self.view == ViewState.EDITOR:
            self._handle_editor_key(ev)
        elif self.view == ViewState.LAUNCHER:
            self._handle_launcher_key(ev)
        elif self.view == ViewState.OUTLINE:
            self._handle_outline_key(ev)
        elif self.view == ViewState.REFERENCE:
            self._handle_reference_key(ev)
        elif self.view == ViewState.REVIEW:
            self._handle_review_key(ev)
        elif self.view == ViewState.CORVUS:
            self._handle_corvus_key(ev)
        elif self.view == ViewState.BLE_BEAM:
            self._handle_ble_beam_key(ev)
        elif self.view == ViewState.PAGE_SETUP:
            self._handle_page_setup_key(ev)
        elif self.view in (ViewState.FILE_BROWSER, ViewState.EXPORT_DIALOG):
            self._handle_file_browser_key(ev)
        elif self.view == ViewState.HELP:
            if ev.key in (KeyCode.ESC, KeyCode.ENTER):
                self.view = ViewState.EDITOR

    def _handle_editor_key(self, ev: KeyEvent) -> None:
        k = ev.key

        # Formatting & Document Shortcuts
        if k == KeyCode.CTRL_B:
            state = self.doc.toggle_bold()
            self.set_toast(f"Bold: {'ON' if state else 'OFF'}")
            self.relayout()
            return
        if k == KeyCode.CTRL_I:
            state = self.doc.toggle_italic()
            self.set_toast(f"Italic: {'ON' if state else 'OFF'}")
            self.relayout()
            return
        if k == KeyCode.CTRL_U:
            state = self.doc.toggle_underline()
            self.set_toast(f"Underline: {'ON' if state else 'OFF'}")
            self.relayout()
            return
        if k == KeyCode.CTRL_T:
            self.doc.set_paragraph_style("title")
            self.set_toast("Style: Title")
            self.relayout()
            return
        if k == KeyCode.CTRL_1:
            self.doc.set_paragraph_style("h1")
            self.set_toast("Style: Heading 1")
            self.relayout()
            return
        if k == KeyCode.CTRL_2:
            self.doc.set_paragraph_style("h2")
            self.set_toast("Style: Heading 2")
            self.relayout()
            return
        if k == KeyCode.CTRL_3:
            self.doc.set_paragraph_style("h3")
            self.set_toast("Style: Heading 3")
            self.relayout()
            return
        if k == KeyCode.CTRL_Q:
            self.doc.set_paragraph_style("quote")
            self.set_toast("Style: Blockquote")
            self.relayout()
            return
        if k == KeyCode.CTRL_0:
            self.doc.set_paragraph_style("normal")
            self.set_toast("Style: Normal Body")
            self.relayout()
            return
        if k == KeyCode.CTRL_L:
            self.doc.set_paragraph_align("left")
            self.set_toast("Align: Left")
            self.relayout()
            return
        if k == KeyCode.CTRL_K:
            self.doc.set_paragraph_align("center")
            self.set_toast("Align: Center")
            self.relayout()
            return
        if k == KeyCode.CTRL_R:
            self.doc.set_paragraph_align("right")
            self.set_toast("Align: Right")
            self.relayout()
            return
        if k == KeyCode.CTRL_P:
            self.doc.insert_page_break()
            self.set_toast("Inserted Page Break")
            self.relayout()
            return
        if k == KeyCode.CTRL_S:
            self.save_now()
            return
        if k == KeyCode.CTRL_Z:
            if self.doc.undo():
                self.set_toast("Undo")
                self.relayout()
            return
        if k == KeyCode.CTRL_Y:
            if self.doc.redo():
                self.set_toast("Redo")
                self.relayout()
            return
        if k == KeyCode.CTRL_M:
            if self.document_mode == DocumentMode.CREATIVE_FICTION:
                self.document_mode = DocumentMode.NON_FICTION
                self.set_toast("Mode: General Non-Fiction")
            else:
                self.document_mode = DocumentMode.CREATIVE_FICTION
                self.set_toast("Mode: Creative Fiction")
            self.corvus.set_document_mode(self.document_mode)
            return
        if k == KeyCode.CTRL_N:
            self.view = ViewState.LAUNCHER
            return
        if k == KeyCode.CTRL_O:
            self._open_file_browser(is_export=False)
            return
        if k == KeyCode.CTRL_E:
            self._open_file_browser(is_export=True)
            return

        # Cursor & Editing keys
        if k == KeyCode.LEFT:
            self.doc.move_left()
            self.relayout()
        elif k == KeyCode.RIGHT:
            self.doc.move_right()
            self.relayout()
        elif k == KeyCode.HOME:
            self.doc.move_home()
            self.relayout()
        elif k == KeyCode.END:
            self.doc.move_end()
            self.relayout()
        elif k == KeyCode.UP:
            if self.doc.cursor_para > 0:
                self.doc.cursor_para -= 1
                self.doc._clamp_cursor()
                self.doc._sync_active_format()
                self.relayout()
        elif k == KeyCode.DOWN:
            if self.doc.cursor_para < len(self.doc.paragraphs) - 1:
                self.doc.cursor_para += 1
                self.doc._clamp_cursor()
                self.doc._sync_active_format()
                self.relayout()
        elif k == KeyCode.BACKSPACE:
            self.doc.backspace()
            self.relayout()
        elif k == KeyCode.DELETE:
            self.doc.delete_forward()
            self.relayout()
        elif k == KeyCode.ENTER:
            self.doc.split_paragraph()
            self.relayout()
        elif ev.char and len(ev.char) == 1 and ord(ev.char) >= 32 and not ev.ctrl:
            self.doc.insert_text(ev.char)
            total_w = len(self.doc.to_plain_text().split())
            self.corvus.on_keystroke(self.doc.current_paragraph.text, total_w)
            self.relayout()

    def _handle_launcher_key(self, ev: KeyEvent) -> None:
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP:
            self.launcher_idx = (self.launcher_idx - 1) % 5
        elif ev.key == KeyCode.DOWN:
            self.launcher_idx = (self.launcher_idx + 1) % 5
        elif ev.key == KeyCode.ENTER or ev.char in ("1", "2", "3", "4", "5"):
            choice = int(ev.char) - 1 if ev.char in ("1", "2", "3", "4", "5") else self.launcher_idx
            if choice == 0:
                self.view = ViewState.EDITOR
            elif choice == 1:
                self.document_mode = DocumentMode.CREATIVE_FICTION
                self.corvus.set_document_mode(self.document_mode)
                self.doc.from_markdown("# Untitled Story\n## Chapter 1\n")
                self.doc.cursor_para = 2
                self.doc.cursor_offset = 0
                self.active_file_path = f"{self.hal.storage_root.rstrip('/')}/story.md"
                self.relayout()
                self.view = ViewState.EDITOR
            elif choice == 2:
                self.document_mode = DocumentMode.NON_FICTION
                self.corvus.set_document_mode(self.document_mode)
                self.doc.from_markdown("# Essay Title\n## I. Introduction\n")
                self.doc.cursor_para = 2
                self.doc.cursor_offset = 0
                self.active_file_path = f"{self.hal.storage_root.rstrip('/')}/essay.md"
                self.relayout()
                self.view = ViewState.EDITOR
            elif choice == 3:
                self._open_file_browser(is_export=False)
            elif choice == 4:
                self.park_for_power_off()

    def park_for_power_off(self) -> None:
        """Atomically saves manuscript, renders parked splash screen, and puts E-Paper into 2uA Deep Sleep."""
        self.ble_beam.stop_radio()
        self.save_now()
        self.view = ViewState.BOOT_SPLASH
        BootSplashRenderer.render(
            self.hal.fb,
            status_text="SESSION SAVED & PARKED — SAFE TO SWITCH POWER OFF",
            progress_pct=100,
            resume_filename=self.active_file_path,
        )
        self.hal.present()
        if hasattr(self.hal, "_display_driver") and hasattr(self.hal._display_driver, "deep_sleep"):
            self.hal._display_driver.deep_sleep()

    def _handle_outline_key(self, ev: KeyEvent) -> None:
        items = self.outline.items
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP and items:
            self.outline_idx = max(0, self.outline_idx - 1)
        elif ev.key == KeyCode.DOWN and items:
            self.outline_idx = min(len(items) - 1, self.outline_idx + 1)
        elif ev.char in ("n", "N"):
            self.outline_idx = self.outline.insert_new_chapter(self.doc)
            self.relayout()
        elif ev.char in ("s", "S") and items:
            new_st = items[self.outline_idx].cycle_status()
            self.doc.dirty = True
            self.set_toast(f"Chapter Status: {new_st}")
        elif ev.char in ("u", "U") and items:
            if self.outline.reorder_chapter(self.doc, self.outline_idx, -1):
                self.outline_idx = max(0, self.outline_idx - 1)
                self.relayout()
        elif ev.char in ("d", "D") and items:
            if self.outline.reorder_chapter(self.doc, self.outline_idx, 1):
                self.outline_idx = min(len(self.outline.items) - 1, self.outline_idx + 1)
                self.relayout()
        elif ev.key == KeyCode.ENTER and items:
            target = items[self.outline_idx]
            self.doc.cursor_para = target.para_index
            self.doc.cursor_offset = 0
            self.relayout()
            self.view = ViewState.EDITOR

    def _refresh_reference_search(self) -> None:
        cats = self.compendium.get_categories()
        cat_name = cats[self.ref_cat_idx % len(cats)] if cats else "All Categories"
        self.ref_results = self.compendium.search(query=self.ref_query, category=cat_name)
        self.ref_selected_idx = 0

    def _handle_reference_key(self, ev: KeyEvent) -> None:
        if self.ref_reading_stub is not None:
            if ev.key in (KeyCode.ESC, KeyCode.BACKSPACE):
                self.ref_reading_stub = None
                self.ref_reading_body = ""
            elif ev.key == KeyCode.UP:
                self.ref_scroll_line = max(0, self.ref_scroll_line - 1)
            elif ev.key == KeyCode.DOWN:
                self.ref_scroll_line += 1
            elif ev.char in ("i", "I"):
                # Insert first summary sentence into manuscript at cursor
                first_line = self.ref_reading_body.split("\n")[0].strip()
                snippet = f"{self.ref_reading_stub.title}: {first_line}"
                self.doc.insert_text(snippet)
                self.relayout()
                self.ref_reading_stub = None
                self.view = ViewState.EDITOR
                self.set_toast("Inserted reference note.")
            return

        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP and self.ref_results:
            self.ref_selected_idx = max(0, self.ref_selected_idx - 1)
        elif ev.key == KeyCode.DOWN and self.ref_results:
            self.ref_selected_idx = min(len(self.ref_results) - 1, self.ref_selected_idx + 1)
        elif ev.key == KeyCode.TAB:
            self.ref_cat_idx += 1
            self._refresh_reference_search()
        elif ev.key == KeyCode.BACKSPACE:
            self.ref_query = self.ref_query[:-1]
            self._refresh_reference_search()
        elif ev.key == KeyCode.ENTER and self.ref_results:
            stub = self.ref_results[self.ref_selected_idx]
            self.ref_reading_stub = stub
            self.ref_reading_body = self.compendium.read_body(stub)
            self.ref_scroll_line = 0
        elif ev.char in ("i", "I") and self.ref_results and not self.ref_query:
            stub = self.ref_results[self.ref_selected_idx]
            body = self.compendium.read_body(stub)
            first_line = body.split("\n")[0].strip()
            self.doc.insert_text(f"{stub.title}: {first_line}")
            self.relayout()
            self.view = ViewState.EDITOR
            self.set_toast("Inserted reference note.")
        elif ev.char and len(ev.char) == 1 and ord(ev.char) >= 32 and not ev.ctrl:
            self.ref_query += ev.char
            self._refresh_reference_search()

    def _handle_review_key(self, ev: KeyEvent) -> None:
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP and self.findings:
            self.review_idx = max(0, self.review_idx - 1)
        elif ev.key == KeyCode.DOWN and self.findings:
            self.review_idx = min(len(self.findings) - 1, self.review_idx + 1)
        elif ev.char in ("h", "H"):
            self.show_lens_highlights = not self.show_lens_highlights
            self.relayout()
        elif ev.char in ("1", "2", "3", "4", "5"):
            keys = ["adverb", "passive", "filler", "pacing", "spelling"]
            k = keys[int(ev.char) - 1]
            self.enabled_lenses[k] = not self.enabled_lenses.get(k, True)
            self.run_review_scan(active_para_only=False)
            self.review_idx = 0
        elif ev.char in ("a", "A") and self.findings:
            f = self.findings[self.review_idx]
            if f.lens_type == "spelling":
                self.spell_engine.add_to_user_dictionary(f.text)
                self.run_review_scan(active_para_only=False)
                self.review_idx = max(0, min(len(self.findings) - 1, self.review_idx))
                self.set_toast(f"Added '{f.text}' to dictionary.")
        elif ev.key == KeyCode.ENTER and self.findings:
            f = self.findings[self.review_idx]
            if f.suggestions:
                rep = f.suggestions[0]
                if rep == "(remove)":
                    rep = ""
                self.doc.replace_in_paragraph(f.para_idx, f.start_pos, f.end_pos, rep)
                self.run_review_scan(active_para_only=False)
                self.review_idx = max(0, min(len(self.findings) - 1, self.review_idx))
                self.relayout()

    def _handle_corvus_key(self, ev: KeyEvent) -> None:
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.char in ("s", "S"):
            self.corvus.trigger_spark()
        elif ev.char in ("t", "T"):
            total_w = len(self.doc.to_plain_text().split())
            if self.corvus.sprint_active:
                self.corvus.stop_sprint()
            else:
                self.corvus.start_sprint(25, total_w)
        elif ev.char in ("m", "M"):
            if self.document_mode == DocumentMode.CREATIVE_FICTION:
                self.document_mode = DocumentMode.NON_FICTION
            else:
                self.document_mode = DocumentMode.CREATIVE_FICTION
            self.corvus.set_document_mode(self.document_mode)

    def _handle_ble_beam_key(self, ev: KeyEvent) -> None:
        if ev.key == KeyCode.ESC:
            self.ble_beam.stop_radio()
            self.view = ViewState.EDITOR
        elif ev.char == "1":
            self.ble_beam.stop_radio()
            self.ble_beam.mode = BLEBeamMode.NUS_UART
            self.ble_beam.status_message = "Selected Mode 1: BLE UART File Stream (Radio OFF)"
        elif ev.char == "2":
            self.ble_beam.stop_radio()
            self.ble_beam.mode = BLEBeamMode.HID_AUTOTYPE
            self.ble_beam.status_message = "Selected Mode 2: BLE HID Auto-Type (Radio OFF)"
        elif ev.key == KeyCode.ENTER:
            short_name = self.active_file_path.replace("\\", "/").split("/")[-1]
            content = self.doc.to_markdown() if self.ble_beam.mode == BLEBeamMode.NUS_UART else self.doc.to_plain_text()
            self.ble_beam.beam_document(short_name, content)
            self.set_toast("BLE Beam finished; BLE Radio OFF.")

    def _handle_page_setup_key(self, ev: KeyEvent) -> None:
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP:
            self.page_setup_idx = (self.page_setup_idx - 1) % 5
        elif ev.key == KeyCode.DOWN:
            self.page_setup_idx = (self.page_setup_idx + 1) % 5
        elif ev.key in (KeyCode.LEFT, KeyCode.RIGHT, KeyCode.ENTER):
            step = -1 if ev.key == KeyCode.LEFT else 1
            if self.page_setup_idx == 0:
                presets = PaperSizePreset.ALL
                curr = presets.index(self.layout_model.paper_size) if self.layout_model.paper_size in presets else 0
                self.layout_model.paper_size = presets[(curr + step) % len(presets)]
            elif self.page_setup_idx == 1:
                self.layout_model.orientation = (
                    Orientation.LANDSCAPE
                    if self.layout_model.orientation == Orientation.PORTRAIT
                    else Orientation.PORTRAIT
                )
            elif self.page_setup_idx == 2:
                m_presets = [
                    PageMargins.normal(),
                    PageMargins.narrow(),
                    PageMargins.wide(),
                    PageMargins.manuscript(),
                ]
                names = [m.preset_name for m in m_presets]
                curr = names.index(self.layout_model.margins.preset_name) if self.layout_model.margins.preset_name in names else 0
                self.layout_model.margins = m_presets[(curr + step) % len(m_presets)]
            elif self.page_setup_idx == 3:
                self.document_mode = (
                    DocumentMode.NON_FICTION
                    if self.document_mode == DocumentMode.CREATIVE_FICTION
                    else DocumentMode.CREATIVE_FICTION
                )
                self.corvus.set_document_mode(self.document_mode)
            elif self.page_setup_idx == 4:
                self.hf_model.different_first_page = not self.hf_model.different_first_page
            self.doc.dirty = True
            self.relayout()

    def _open_file_browser(self, is_export: bool = False) -> None:
        makedirs_safe(self.hal.storage_root)
        try:
            all_f = os.listdir(self.hal.storage_root)
        except Exception:
            all_f = []
        self.browser_files = sorted(
            [f for f in all_f if f.endswith((".md", ".txt", ".docx")) and not f.startswith(".")]
        )
        self.browser_idx = 0
        self.view = ViewState.EXPORT_DIALOG if is_export else ViewState.FILE_BROWSER

    def _handle_file_browser_key(self, ev: KeyEvent) -> None:
        is_exp = self.view == ViewState.EXPORT_DIALOG
        if ev.key == KeyCode.ESC:
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.UP and self.browser_files:
            self.browser_idx = max(0, self.browser_idx - 1)
        elif ev.key == KeyCode.DOWN and self.browser_files:
            self.browser_idx = min(len(self.browser_files) - 1, self.browser_idx + 1)
        elif is_exp and ev.char in ("d", "D"):
            base = self.active_file_path.rsplit(".", 1)[0]
            out_docx = f"{base}.docx"
            if IOManager.export_docx(out_docx, self.doc, self.layout_model):
                self.set_toast(f"Exported {out_docx.split('/')[-1]}")
            self.view = ViewState.EDITOR
        elif is_exp and ev.char in ("t", "T"):
            base = self.active_file_path.rsplit(".", 1)[0]
            out_txt = f"{base}.txt"
            IOManager.atomic_write_text(out_txt, self.doc.to_plain_text())
            self.set_toast(f"Exported {out_txt.split('/')[-1]}")
            self.view = ViewState.EDITOR
        elif not is_exp and ev.char in ("n", "N"):
            new_idx = len(self.browser_files) + 1
            new_path = f"{self.hal.storage_root.rstrip('/')}/draft_{new_idx}.md"
            self.doc.from_markdown(f"# Draft {new_idx}\n## Chapter 1\n")
            self.active_file_path = new_path
            self.save_now()
            self.relayout()
            self.view = ViewState.EDITOR
        elif ev.key == KeyCode.ENTER and self.browser_files:
            chosen = self.browser_files[self.browser_idx]
            full_path = f"{self.hal.storage_root.rstrip('/')}/{chosen}"
            if is_exp:
                IOManager.save_document(full_path, self.doc, self.layout_model, self.hf_model, self.document_mode)
                self.set_toast(f"Exported {chosen}")
            else:
                self.open_document(full_path)
                self.set_toast(f"Opened {chosen}")
            self.view = ViewState.EDITOR

    # --- Pointer / Touchpad & Dynamic Top Ribbon Dispatch ---

    def handle_pointer_event(self, pev) -> None:
        """Handles pointer/touchpad movement, clicks on Dynamic Top Ribbon, and click-to-place-cursor."""
        if pev.scroll_y != 0:
            key = KeyCode.UP if pev.scroll_y < 0 else KeyCode.DOWN
            self.handle_key_event(KeyEvent(key=key))
            return

        if not pev.clicked:
            return

        px, py = pev.x, pev.y

        if self.view == ViewState.BOOT_SPLASH:
            self.view = ViewState.EDITOR
            return

        # If a modal overlay is open, check the modal [X] close box or click-outside-to-close
        if self.view != ViewState.EDITOR:
            w, h = self.hal.width, self.hal.height
            mx, my, mw, mh = 10, 10, w - 20, h - 20
            # Close button [X] in top-right of modal title bar or click outside modal frame
            if (
                px < mx or px > mx + mw or py < my or py > my + mh
                or (mx + mw - 32 <= px <= mx + mw and my <= py <= my + 18)
            ):
                if self.view == ViewState.BLE_BEAM:
                    self.ble_beam.stop_radio()
                self.view = ViewState.EDITOR
                return
            # Click inside modal body triggers ENTER or row selection
            if self.view == ViewState.LAUNCHER:
                rel_y = py - (my + 25)
                if 0 <= rel_y < 72:
                    self.launcher_idx = max(0, min(3, rel_y // 18))
                    self._handle_launcher_key(KeyEvent(KeyCode.ENTER, "\n"))
            elif self.view == ViewState.OUTLINE and self.outline.items:
                rel_y = py - (my + 21)
                if rel_y >= 0:
                    row = rel_y // 12
                    if 0 <= row < len(self.outline.items):
                        self.outline_idx = row
                        self._handle_outline_key(KeyEvent(KeyCode.ENTER, "\n"))
            return

        # 1. Check Dynamic Simplified Top Ribbon & Top Bar hitboxes
        for hx, hy, hw, hh, action_id in self.ribbon_hitboxes:
            if hx <= px < hx + hw and hy <= py < hy + hh:
                self.execute_ribbon_action(action_id)
                return

        # 2. Check Paper Sheet line/character hitboxes to position the cursor
        for lbox in self.line_hitboxes:
            if lbox["y0"] <= py < lbox["y1"] and lbox["x0"] <= px <= lbox["x1"]:
                self.doc.cursor_para = lbox["para_idx"]
                char_xs = lbox["char_x"]
                best_col = 0
                best_dist = 999999
                for col_i, cx in enumerate(char_xs):
                    dist = abs(px - cx)
                    if dist < best_dist:
                        best_dist = dist
                        best_col = col_i
                self.doc.cursor_offset = lbox["char_start"] + best_col
                self.doc._clamp_cursor()
                self.doc._sync_active_format()
                self.relayout()
                return

    def execute_ribbon_action(self, action_id: str) -> None:
        """Executes a formatting or tool command clicked on the Dynamic Simplified Top Ribbon."""
        if action_id == "act:toggle_ribbon":
            self.show_ribbon = not self.show_ribbon
            self.set_toast(f"Top Ribbon: {'ON' if self.show_ribbon else 'OFF'}")
        elif action_id == "act:launcher":
            self.view = ViewState.LAUNCHER
        elif action_id == "style:title":
            self.doc.set_paragraph_style("title")
            self.set_toast("Style: Title")
            self.relayout()
        elif action_id == "style:h1":
            self.doc.set_paragraph_style("h1")
            self.set_toast("Style: Heading 1")
            self.relayout()
        elif action_id == "style:h2":
            self.doc.set_paragraph_style("h2")
            self.set_toast("Style: Heading 2")
            self.relayout()
        elif action_id == "style:quote":
            self.doc.set_paragraph_style("quote")
            self.set_toast("Style: Blockquote")
            self.relayout()
        elif action_id == "style:normal":
            self.doc.set_paragraph_style("normal")
            self.set_toast("Style: Normal Body")
            self.relayout()
        elif action_id == "fmt:bold":
            st = self.doc.toggle_bold()
            self.set_toast(f"Bold: {'ON' if st else 'OFF'}")
            self.relayout()
        elif action_id == "fmt:italic":
            st = self.doc.toggle_italic()
            self.set_toast(f"Italic: {'ON' if st else 'OFF'}")
            self.relayout()
        elif action_id == "fmt:underline":
            st = self.doc.toggle_underline()
            self.set_toast(f"Underline: {'ON' if st else 'OFF'}")
            self.relayout()
        elif action_id == "align:left":
            self.doc.set_paragraph_align("left")
            self.set_toast("Align: Left")
            self.relayout()
        elif action_id == "align:center":
            self.doc.set_paragraph_align("center")
            self.set_toast("Align: Center")
            self.relayout()
        elif action_id == "align:right":
            self.doc.set_paragraph_align("right")
            self.set_toast("Align: Right")
            self.relayout()
        elif action_id == "act:save":
            self.save_now()
        elif action_id == "act:outline":
            self.handle_key_event(KeyEvent(KeyCode.F2_OUTLINE))
        elif action_id == "act:reference":
            self.handle_key_event(KeyEvent(KeyCode.F3_REFERENCE))
        elif action_id == "act:review":
            self.handle_key_event(KeyEvent(KeyCode.F4_REVIEW))
        elif action_id == "act:corvus":
            self.handle_key_event(KeyEvent(KeyCode.F5_CORVUS))
        elif action_id == "act:ble":
            self.handle_key_event(KeyEvent(KeyCode.F6_BLE_BEAM))
        elif action_id == "act:setup":
            self.handle_key_event(KeyEvent(KeyCode.F7_PAGE_SETUP))
