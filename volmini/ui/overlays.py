"""Modal Overlay Renderers for Volmini (1-bit FrameBuffer).

Includes:
- Document Launcher (Resume Session, New Creative Fiction, New Non-Fiction, Open File)
- Chapter Outline Navigator (F2)
- Stripped Offline Writer's Reference Compendium (F3)
- Revision Lenses & Spell Check Inspector (F4)
- Corvus the Raven Companion & Sprint Timer (F5)
- Dual-Mode On-Demand BLE Beam to Phone (F6)
- Print Page Setup (F7)
- File Browser / Export Dialog (Ctrl+O / Ctrl+E)
- Quick Keyboard Shortcut Help Card (F1)
"""

from volmini.ui.font5x8 import draw_text, draw_bitmap_1bit, CHAR_ADVANCE, LINE_HEIGHT


class OverlayRenderer:
    """Renders crisp monochrome modal windows over the workspace."""

    @staticmethod
    def _draw_modal_frame(fb, title: str, footer_hint: str) -> tuple:
        """Draws a bordered modal box and returns (inner_x, inner_y, inner_w, inner_h)."""
        w = fb.width
        h = fb.height
        mx = 10
        my = 10
        mw = w - 20
        mh = h - 20

        # White card with double black border
        fb.fill_rect(mx, my, mw, mh, 1)
        fb.rect(mx, my, mw, mh, 0)
        fb.rect(mx + 2, my + 2, mw - 4, mh - 4, 0)

        # Inverted black title bar with clickable [X] close box
        fb.fill_rect(mx + 2, my + 2, mw - 4, 13, 0)
        draw_text(fb, title, mx + 8, my + 5, color=1, bold=True, max_width=mw - 36)
        draw_text(fb, "[X]", mx + mw - 24, my + 5, color=1, bold=True)

        # Bottom hint bar
        fy = my + mh - 14
        fb.hline(mx + 2, fy - 1, mw - 4, 0)
        draw_text(fb, footer_hint, mx + 6, fy + 2, color=0, max_width=mw - 12)

        return (mx + 8, my + 19, mw - 16, mh - 36)

    @classmethod
    def render_launcher(cls, fb, selected_idx: int, resume_file: str = "") -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            "VOLMINI DOCUMENT LAUNCHER",
            "[UP/DN: Select]  [ENTER: Open]  [ESC: Editor]",
        )
        options = [
            f"1. Resume Last Session ({resume_file.split('/')[-1] if resume_file else 'untitled.md'})",
            "2. New Creative Fiction Manuscript (Story & Narrative)",
            "3. New General Non-Fiction Document (Essays & Exposition)",
            "4. Open Existing File from Storage (/sd or /documents)",
            "5. Save & Park E-Paper Display (Safe to Switch Power OFF)",
        ]
        y = iy + 4
        for idx, label in enumerate(options):
            is_sel = idx == selected_idx
            if is_sel:
                fb.fill_rect(ix, y - 1, iw, 12, 0)
                draw_text(fb, "> " + label, ix + 4, y + 1, color=1, bold=True, max_width=iw - 8)
            else:
                draw_text(fb, "  " + label, ix + 4, y + 1, color=0, max_width=iw - 8)
            y += 15

    @classmethod
    def render_outline(cls, fb, items: list, selected_idx: int, total_words: int) -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            f"CHAPTER OUTLINE NAVIGATOR ({len(items)} Chapters | {total_words}w)",
            "[ENTER:Jump] [N:+Chap] [S:Status] [U/D:Reorder] [ESC:Close]",
        )
        if not items:
            draw_text(fb, "No chapter headings found yet.", ix + 4, iy + 12, color=0)
            draw_text(fb, "Press 'N' to insert Chapter 1, or use Ctrl+1 (H1) in editor.", ix + 4, iy + 26, color=0)
            return

        max_rows = max(1, ih // 13)
        start = max(0, selected_idx - max_rows + 1) if selected_idx >= max_rows else 0
        y = iy + 2
        for idx in range(start, min(len(items), start + max_rows)):
            item = items[idx]
            indent = "  " * max(0, item.heading_level - 1)
            row_txt = f"{idx + 1}. {indent}{item.title[:26]}  ({item.word_count}w) [{item.status}]"
            if idx == selected_idx:
                fb.fill_rect(ix, y - 1, iw, 11, 0)
                draw_text(fb, row_txt, ix + 3, y + 1, color=1, max_width=iw - 6)
            else:
                draw_text(fb, row_txt, ix + 3, y + 1, color=0, max_width=iw - 6)
            y += 12

    @classmethod
    def render_reference(
        cls,
        fb,
        query: str,
        category: str,
        results: list,
        selected_idx: int,
        reading_stub,
        reading_body: str,
        scroll_line: int,
    ) -> None:
        if reading_stub is not None:
            ix, iy, iw, ih = cls._draw_modal_frame(
                fb,
                f"REF: {reading_stub.title[:34]} [{reading_stub.category[:14]}]",
                "[UP/DN: Scroll]  [I: Insert into Manuscript]  [BKSP/ESC: Back]",
            )
            # Word-wrap reading_body to fit modal width
            max_cols = max(20, iw // CHAR_ADVANCE)
            wrapped = cls._wrap_plain_lines(reading_body, max_cols)
            max_rows = max(1, ih // LINE_HEIGHT)
            s_line = max(0, min(max(0, len(wrapped) - max_rows), scroll_line))
            y = iy
            for ln in wrapped[s_line:s_line + max_rows]:
                draw_text(fb, ln, ix, y, color=0, max_width=iw)
                y += LINE_HEIGHT
            return

        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            f"WRITER'S REFERENCE ({len(results)} topics) | Cat: {category[:18]}",
            "[Type:Search] [TAB:Category] [ENTER:Read] [I:Insert] [ESC:Close]",
        )
        # Search input box
        fb.rect(ix, iy, iw, 13, 0)
        draw_text(fb, f"Filter: {query}_", ix + 4, iy + 3, color=0, max_width=iw - 8)

        list_y = iy + 16
        avail_h = ih - 16
        max_rows = max(1, avail_h // 11)
        start = max(0, selected_idx - max_rows + 1) if selected_idx >= max_rows else 0

        for idx in range(start, min(len(results), start + max_rows)):
            stub = results[idx]
            line_str = f"{stub.title[:32]}  [{stub.category}]"
            if idx == selected_idx:
                fb.fill_rect(ix, list_y - 1, iw, 10, 0)
                draw_text(fb, line_str, ix + 3, list_y, color=1, max_width=iw - 6)
            else:
                draw_text(fb, line_str, ix + 3, list_y, color=0, max_width=iw - 6)
            list_y += 11

    @classmethod
    def render_review(cls, fb, findings: list, selected_idx: int, enabled_lenses: dict, show_highlights: bool) -> None:
        flags = []
        for k, label in (("adverb", "Adv"), ("passive", "Pas"), ("filler", "Fil"), ("pacing", "Pac"), ("spelling", "Spl")):
            flags.append(f"{label}:{'ON' if enabled_lenses.get(k, True) else 'off'}")
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            f"REVISION LENSES & SPELL CHECK ({len(findings)} findings)",
            "[ENTER:Apply Fix] [A:+Dict] [H:Highlights] [1-5:Toggle] [ESC:Close]",
        )
        draw_text(fb, " ".join(flags) + f" | Mark:{'ON' if show_highlights else 'OFF'}", ix, iy, color=0, bold=True)
        fb.hline(ix, iy + 9, iw, 0)

        if not findings:
            draw_text(fb, "No issues flagged by active lenses!", ix + 4, iy + 22, color=0)
            return

        selected_idx = max(0, min(len(findings) - 1, selected_idx))
        f = findings[selected_idx]

        # List of findings (top half)
        list_y = iy + 12
        max_list = 5
        start = max(0, selected_idx - max_list + 1) if selected_idx >= max_list else 0
        for idx in range(start, min(len(findings), start + max_list)):
            item = findings[idx]
            tag = item.lens_type.upper()[:4]
            row_str = f"[{tag}] P{item.para_idx + 1}: '{item.text[:22]}' -> {', '.join(item.suggestions[:2]) or 'inspect'}"
            if idx == selected_idx:
                fb.fill_rect(ix, list_y - 1, iw, 10, 0)
                draw_text(fb, row_str, ix + 2, list_y, color=1, max_width=iw - 4)
            else:
                draw_text(fb, row_str, ix + 2, list_y, color=0, max_width=iw - 4)
            list_y += 11

        # Inspector detail card for selected finding (bottom half)
        det_y = iy + 70
        fb.rect(ix, det_y, iw, ih - 72, 0)
        draw_text(fb, f.message[:58], ix + 4, det_y + 3, color=0, bold=True, max_width=iw - 8)
        draw_text(fb, f"Context: {f.context_snippet[:52]}", ix + 4, det_y + 14, color=0, italic=True, max_width=iw - 8)
        sug_str = "Suggestions (ENTER to apply #1): " + (", ".join(f.suggestions[:4]) if f.suggestions else "(none)")
        draw_text(fb, sug_str[:58], ix + 4, det_y + 25, color=0, max_width=iw - 8)

    @classmethod
    def render_corvus(cls, fb, corvus, total_words: int) -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            f"CORVUS THE RAVEN  *  Mood: {corvus.mood.upper()}",
            "[S: Writing Spark]  [T: Start/Stop 25m Sprint]  [M: Mode]  [ESC: Close]",
        )
        # Draw 16x16 Raven Sprite inside frame box
        fb.rect(ix + 2, iy + 2, 22, 22, 0)
        draw_bitmap_1bit(fb, corvus.sprite, 16, 16, ix + 5, iy + 5, color=0)

        draw_text(fb, f"{corvus.NAME} — {corvus.TITLE}", ix + 30, iy + 3, color=0, bold=True)
        mode_lbl = "Creative Fiction" if corvus.document_mode == "creative_fiction" else "General Non-Fiction"
        draw_text(fb, f"Active Studio Mode: {mode_lbl}", ix + 30, iy + 14, color=0, italic=True)

        # Sprint status box
        sy = iy + 28
        fb.rect(ix, sy, iw, 20, 0)
        if corvus.sprint_active:
            rem = corvus.sprint_remaining_seconds()
            delta = max(0, total_words - corvus.sprint_start_words)
            s_txt = f"SPRINT ACTIVE: {rem // 60:02d}:{rem % 60:02d} left  |  +{delta} words drafted"
        else:
            s_txt = f"Sprint Timer: Standby ({corvus.sprint_duration_minutes}m preset)  |  Manuscript: {total_words} words"
        draw_text(fb, s_txt, ix + 5, sy + 6, color=0, bold=corvus.sprint_active, max_width=iw - 10)

        # Corvus message / editorial insight bubble
        by = sy + 25
        max_cols = max(20, (iw - 8) // CHAR_ADVANCE)
        wrapped = cls._wrap_plain_lines(corvus.last_message, max_cols)
        for idx, ln in enumerate(wrapped[:5]):
            draw_text(fb, ln, ix + 4, by + idx * 10, color=0, max_width=iw - 8)

    @classmethod
    def render_ble_beam(cls, fb, ble_engine, filename: str, char_count: int) -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            "ON-DEMAND BLUETOOTH BEAM TO PHONE (Wi-Fi OFF)",
            "[1:BLE UART Stream] [2:BLE HID Auto-Type] [ENTER:Beam] [ESC:Off/Close]",
        )
        m1_sel = ble_engine.mode == "nus_uart"
        draw_text(
            fb,
            f"{'>' if m1_sel else ' '} Mode 1: BLE UART File Stream (Nordic UART / Web-BLE / Serial App)",
            ix + 2, iy + 4, color=0, bold=m1_sel, max_width=iw - 4
        )
        draw_text(
            fb,
            f"{'>' if not m1_sel else ' '} Mode 2: BLE HID Keyboard Auto-Type (Types directly into Phone Notes)",
            ix + 2, iy + 16, color=0, bold=not m1_sel, max_width=iw - 4
        )

        fb.hline(ix, iy + 30, iw, 0)
        draw_text(fb, f"Target Document: {filename} ({char_count} chars)", ix + 2, iy + 36, color=0)
        rad_state = "ACTIVE (Advertising)" if ble_engine.radio_active else "STRICTLY OFF (0mW RF)"
        draw_text(fb, f"BLE Radio State: {rad_state}", ix + 2, iy + 48, color=0, bold=True)
        draw_text(fb, f"Status: {ble_engine.status_message[:52]}", ix + 2, iy + 62, color=0, italic=True)

        # Progress bar
        bar_y = iy + 78
        fb.rect(ix + 2, bar_y, iw - 4, 12, 0)
        fill_w = int(((iw - 8) * max(0, min(100, ble_engine.progress_pct))) // 100)
        if fill_w > 0:
            fb.fill_rect(ix + 4, bar_y + 2, fill_w, 8, 0)

    @classmethod
    def render_page_setup(cls, fb, layout_model, hf_model, doc_mode: str, selected_row: int) -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            "PRINT PAGE SETUP & GEOMETRY",
            "[UP/DN: Select Field]  [LEFT/RIGHT/ENTER: Cycle Option]  [ESC: Done]",
        )
        rows = [
            f"Paper Size     : {layout_model.paper_size}",
            f"Orientation    : {layout_model.orientation}",
            f"Page Margins   : {layout_model.margins.preset_name}",
            f"Authoring Mode : {'Creative Fiction' if doc_mode == 'creative_fiction' else 'General Non-Fiction'}",
            f"1st Pg Numbers : {'Suppressed (Book Standard)' if hf_model.different_first_page else 'Shown on Page 1'}",
            f"Print Grid     : {layout_model.printable_cols} cols x {layout_model.printable_lines_per_page} lines/page",
        ]
        y = iy + 6
        for idx, r_txt in enumerate(rows):
            if idx == selected_idx if False else (idx == selected_row):
                fb.fill_rect(ix, y - 1, iw, 12, 0)
                draw_text(fb, "> " + r_txt, ix + 4, y + 1, color=1, bold=True, max_width=iw - 8)
            else:
                draw_text(fb, "  " + r_txt, ix + 4, y + 1, color=0, max_width=iw - 8)
            y += 15

    @classmethod
    def render_file_browser(cls, fb, storage_root: str, files: list, selected_idx: int, is_export: bool = False) -> None:
        title = "EXPORT DOCUMENT (.DOCX / .MD / .TXT)" if is_export else f"STORAGE FILE BROWSER ({storage_root})"
        hint = "[ENTER: Select]  [D: Export .docx]  [T: Export .txt]  [ESC: Cancel]" if is_export else "[UP/DN: Select]  [ENTER: Open]  [N: New File]  [ESC: Cancel]"
        ix, iy, iw, ih = cls._draw_modal_frame(fb, title, hint)

        if not files:
            draw_text(fb, "No documents found in storage directory.", ix + 4, iy + 12, color=0)
            return

        max_rows = max(1, ih // 12)
        start = max(0, selected_idx - max_rows + 1) if selected_idx >= max_rows else 0
        y = iy + 2
        for idx in range(start, min(len(files), start + max_rows)):
            fname = files[idx]
            if idx == selected_idx:
                fb.fill_rect(ix, y - 1, iw, 11, 0)
                draw_text(fb, f"> {fname}", ix + 4, y + 1, color=1, bold=True, max_width=iw - 8)
            else:
                draw_text(fb, f"  {fname}", ix + 4, y + 1, color=0, max_width=iw - 8)
            y += 12

    @classmethod
    def render_help(cls, fb) -> None:
        ix, iy, iw, ih = cls._draw_modal_frame(
            fb,
            "VOLMINI KEYBOARD SHORTCUTS & COMMANDS",
            "[Press ESC or F1 to return to Print Editor]",
        )
        lines = [
            "Ctrl+B / I / U : Bold / Italic / Underline (inline or word)",
            "Ctrl+T / 1..3  : Title / Heading 1 / Heading 2 / Heading 3",
            "Ctrl+Q / 0     : Blockquote / Normal Body Paragraph",
            "Ctrl+L / K / R : Align Left / Center / Right",
            "Ctrl+P         : Insert Explicit Page Break",
            "Ctrl+S / O / E : Save / Open File / Export (.docx, .md, .txt)",
            "F2: Outline  | F3: Reference | F4: Lenses/Spell | F5: Corvus",
            "F6: BLE Beam | F7: Page Setup| Ctrl+M: Fiction/Non-Fiction",
        ]
        y = iy + 2
        for ln in lines:
            draw_text(fb, ln, ix + 2, y, color=0, max_width=iw - 4)
            y += 12

    @staticmethod
    def _wrap_plain_lines(text: str, max_cols: int) -> list:
        out = []
        for raw_line in (text or "").split("\n"):
            if not raw_line:
                out.append("")
                continue
            pos = 0
            n = len(raw_line)
            while pos < n:
                if pos + max_cols >= n:
                    out.append(raw_line[pos:])
                    break
                window = raw_line[pos:pos + max_cols + 1]
                sp = window.rfind(" ")
                if sp > 0:
                    out.append(raw_line[pos:pos + sp])
                    pos += sp + 1
                else:
                    out.append(raw_line[pos:pos + max_cols])
                    pos += max_cols
        return out
