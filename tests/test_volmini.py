"""Comprehensive automated test suite for Volmini (ESP32 MicroPython Edition)."""

import os
import sys
import zipfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volmini.hal.base import KeyCode, KeyEvent
from volmini.hal.hal_desktop import DesktopHAL
from volmini.core.document_model import (
    PageLayoutModel, PaperSizePreset, Orientation, PageMargins, DocumentMode, DocumentStatistics
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
from volmini.companion.corvus import CorvusCompanion, PetMood
from volmini.ui.app import VolminiApp, ViewState


def test_boot_splash_and_instant_session_resume(tmp_path):
    hal = DesktopHAL(width=400, height=240, storage_root=str(tmp_path))
    app = VolminiApp(hal)
    app.run_boot_sequence(interactive_wait=False)

    assert app.view == ViewState.EDITOR
    assert hal.present_count >= 4  # 4 boot progress frames + editor render
    # Verify non-empty framebuffer pixels from rendering
    non_zero_bytes = sum(1 for b in hal.buffer if b != 0)
    assert non_zero_bytes > 100

    # Edit text, save session, and verify a second boot resumes exact file & cursor offset
    app.doc.insert_text(" Added session text.")
    app.save_now()
    saved_para = app.doc.cursor_para
    saved_offset = app.doc.cursor_offset

    hal2 = DesktopHAL(width=400, height=240, storage_root=str(tmp_path))
    app2 = VolminiApp(hal2)
    app2.run_boot_sequence(interactive_wait=False)
    assert app2.active_file_path == app.active_file_path
    assert app2.doc.cursor_para == saved_para
    assert app2.doc.cursor_offset == saved_offset
    assert "Added session text." in app2.doc.to_plain_text()


def test_rich_document_formatting_and_markdown_roundtrip():
    doc = RichDocument()
    doc.set_paragraph_style("title")
    doc.insert_text("The Brass Compass")
    doc.split_paragraph()
    doc.set_paragraph_style("h1")
    doc.insert_text("Chapter 1")
    doc.split_paragraph()
    doc.insert_text("Normal ")
    doc.toggle_bold()
    doc.insert_text("bold")
    doc.toggle_bold()
    doc.insert_text(" and ")
    doc.toggle_italic()
    doc.insert_text("italic")
    doc.toggle_italic()
    doc.insert_text(" text.")
    doc.split_paragraph()
    doc.set_paragraph_align("right")
    doc.insert_text("Signed, The Author")

    md = doc.to_markdown()
    assert "# The Brass Compass" in md
    assert "## Chapter 1" in md
    assert "**bold**" in md
    assert "*italic*" in md
    assert "{:right} Signed, The Author" in md

    doc2 = RichDocument()
    doc2.from_markdown(md)
    assert doc2.paragraphs[0].style == "title"
    assert doc2.paragraphs[0].align == "center"
    assert doc2.paragraphs[1].style == "h1"
    assert doc2.paragraphs[3].align == "right"

    # Test Undo / Redo
    prev_text = doc.to_plain_text()
    doc.insert_text(" Extra")
    assert doc.to_plain_text().endswith("Extra")
    assert doc.undo() is True
    assert doc.to_plain_text() == prev_text
    assert doc.redo() is True
    assert doc.to_plain_text().endswith("Extra")


def test_print_accurate_pagination_and_headers():
    doc = RichDocument()
    doc.set_paragraph_style("title")
    doc.insert_text("A Treatise on Navigation")
    for i in range(1, 35):
        doc.split_paragraph()
        doc.insert_text(f"Paragraph {i}: The sextant measures the angular distance between two visible objects.")

    layout = PageLayoutModel(paper_size=PaperSizePreset.BOOK_6X9, margins=PageMargins.normal())
    hf = HeaderFooterModel(different_first_page=True)
    pages = PrintPaginationEngine.paginate(doc, layout, hf, story_title="Navigation")

    assert len(pages) >= 2
    # Page 1 should have headers/footers suppressed by default book standard
    assert pages[0].header_suppressed is True
    assert pages[1].header_suppressed is False
    assert pages[1].footer_center == "- 2 -"


def test_chapter_outline_navigator_scan_and_reorder():
    doc = RichDocument()
    doc.from_markdown(
        "# Book Title\n"
        "## Chapter 1: The Harbor\n"
        "First chapter text with seven words here.\n"
        "## Chapter 2: The Sea\n"
        "Second chapter text with five words."
    )
    nav = OutlineNavigator()
    items = nav.scan(doc)
    assert len(items) == 3
    assert items[1].title == "Chapter 1: The Harbor"
    assert items[1].word_count == 7
    assert items[2].title == "Chapter 2: The Sea"
    assert items[2].word_count == 6

    # Cycle status
    assert items[1].cycle_status() == "In Progress"

    # Reorder Chapter 2 before Chapter 1
    ok = nav.reorder_chapter(doc, 2, -1)
    assert ok is True
    assert nav.items[1].title == "Chapter 2: The Sea"
    assert nav.items[2].title == "Chapter 1: The Harbor"


def test_stripped_reference_compendium_lazy_seek():
    comp = StrippedCompendium()
    assert comp.total_count >= 260
    cats = comp.get_categories()
    assert "All Categories" in cats
    assert len(cats) >= 12

    results = comp.search(query="sextant")
    assert len(results) >= 1
    body = comp.read_body(results[0])
    assert len(body) > 40
    # Verify plain text only (no HTML tags)
    assert "<p>" not in body and "<b>" not in body


def test_revision_lenses_and_binary_search_spell_check(tmp_path):
    sample = "He quietly walked in order to see the treasure that was hidden."
    findings = RevisionLensEngine.analyze_paragraph(0, sample)
    types = {f.lens_type for f in findings}
    assert "adverb" in types      # "quietly"
    assert "filler" in types      # "in order to"
    assert "passive" in types     # "was hidden" or participle

    user_dict = str(tmp_path / "user_dict.json")
    spell = SpellCheckEngine(user_dict_path=user_dict)
    assert spell.is_correct("manuscript") is True
    assert spell.is_correct("teh") is False
    suggs = spell.get_suggestions("teh")
    assert "the" in suggs

    # Test custom user dictionary persistence
    assert spell.is_correct("zylokian") is False
    spell.add_to_user_dictionary("zylokian")
    assert spell.is_correct("zylokian") is True


def test_corvus_companion_sparks_milestones_and_sprint():
    corvus = CorvusCompanion()
    assert corvus.mood == PetMood.IDLE

    # Duplicate word alert in active sentence
    corvus.on_keystroke("The dark shadow met another dark shadow.", total_words=20, now_ms=1000)
    assert corvus.mood == PetMood.ALERT
    assert "dark" in corvus.last_message

    # Milestone celebration at 100 words
    corvus.on_keystroke("Normal sentence here.", total_words=102, now_ms=2000)
    assert corvus.mood == PetMood.CELEBRATING
    assert "100 Words" in corvus.last_message

    # Mode prompts
    corvus.set_document_mode(DocumentMode.NON_FICTION)
    spark = corvus.trigger_spark()
    assert "Spark:" in spark

    # Sprint timer
    corvus.start_sprint(duration_minutes=1, current_word_count=100)
    assert corvus.sprint_active is True
    corvus.tick(corvus.sprint_start_ms + 61_000)
    assert corvus.sprint_active is False
    assert corvus.mood == PetMood.NUDGING


def test_dual_mode_ble_beam_and_radio_lockdown():
    ble = BLEBeamEngine()
    assert ble.radio_active is False

    # Mode 1: BLE UART (NUS) framing
    ble.mode = BLEBeamMode.NUS_UART
    ok = ble.beam_document("chapter1.md", "# Chapter 1\nHello phone via BLE UART!")
    assert ok is True
    # Radio must automatically power back OFF after beaming completes
    assert ble.radio_active is False
    assert len(ble._transmitted_packets) >= 3
    assert b"---VOLMINI:BEGIN:chapter1.md:" in ble._transmitted_packets[0]
    assert b"---VOLMINI:END:" in ble._transmitted_packets[-1]

    # Mode 2: BLE HID Keyboard Auto-Type
    ble.mode = BLEBeamMode.HID_AUTOTYPE
    ok2 = ble.beam_document("chapter1.txt", "Hi!")
    assert ok2 is True
    assert ble.radio_active is False
    # 3 chars * 2 reports (press + release) = 6 8-byte HID reports
    assert len(ble._transmitted_packets) == 6
    assert all(len(pkt) == 8 for pkt in ble._transmitted_packets)


def test_zero_dependency_docx_export(tmp_path):
    doc = RichDocument()
    doc.from_markdown("# Exported Codex\n## Chapter 1\nThis is **bold** and *italic* prose.")
    docx_path = str(tmp_path / "exported.docx")

    ok = IOManager.export_docx(docx_path, doc, PageLayoutModel())
    assert ok is True
    assert os.path.exists(docx_path)
    assert zipfile.is_zipfile(docx_path)

    with zipfile.ZipFile(docx_path, "r") as zf:
        names = zf.namelist()
        assert "[Content_Types].xml" in names
        assert "_rels/.rels" in names
        assert "word/document.xml" in names
        xml_body = zf.read("word/document.xml").decode("utf-8")
        assert "Exported Codex" in xml_body
        assert "<w:b/>" in xml_body
        assert "<w:i/>" in xml_body


def test_ui_overlays_and_state_transitions(tmp_path):
    hal = DesktopHAL(width=400, height=240, storage_root=str(tmp_path))
    app = VolminiApp(hal)
    app.run_boot_sequence(interactive_wait=False)

    # Toggle through every overlay F1..F7 and verify clean rendering
    for fk, expected_view in [
        (KeyCode.F1_HELP, ViewState.HELP),
        (KeyCode.F2_OUTLINE, ViewState.OUTLINE),
        (KeyCode.F3_REFERENCE, ViewState.REFERENCE),
        (KeyCode.F4_REVIEW, ViewState.REVIEW),
        (KeyCode.F5_CORVUS, ViewState.CORVUS),
        (KeyCode.F6_BLE_BEAM, ViewState.BLE_BEAM),
        (KeyCode.F7_PAGE_SETUP, ViewState.PAGE_SETUP),
    ]:
        hal.push_key(fk)
        app.tick()
        assert app.view == expected_view
        hal.push_key(KeyCode.ESC)
        app.tick()
        assert app.view == ViewState.EDITOR


def test_gdey075t7_800x480_driver_and_display_profiles(tmp_path):
    from volmini.hal.displays import DISPLAY_PROFILES, GDEY075T7Driver, load_hardware_config

    assert "gdey075t7_800x480" in DISPLAY_PROFILES
    prof = DISPLAY_PROFILES["gdey075t7_800x480"]
    assert prof.width == 800
    assert prof.height == 480
    assert prof.controller == "UC8179"
    assert prof.framebuffer_bytes == 48000

    # Verify UC8179 command sequences on GDEY075T7Driver (Full + 0.34s Partial Window + Deep Sleep)
    drv = GDEY075T7Driver(spi=None, cs_pin=None, dc_pin=None, rst_pin=None, busy_pin=None)
    buf = bytearray(48000)
    drv.refresh_full(buf)
    cmds = [c for c, _ in drv.command_log]
    assert 0x01 in cmds  # PWR
    assert 0x06 in cmds  # BTST
    assert 0x04 in cmds  # PON
    assert 0x00 in cmds  # PSR
    assert 0x61 in cmds  # TRES (800x480)
    assert 0x13 in cmds  # DTM2 (48,000 byte frame write)
    assert 0x12 in cmds  # DRF (Display Refresh)

    drv.command_log.clear()
    drv.refresh_partial_window(buf, x=16, y=12, w=160, h=24)
    p_cmds = [c for c, _ in drv.command_log]
    assert p_cmds == [0x91, 0x90, 0x13, 0x12, 0x92]  # PTIN -> PTL -> DTM2 -> DRF -> PTOUT

    drv.command_log.clear()
    drv.deep_sleep()
    s_cmds = [c for c, _ in drv.command_log]
    assert s_cmds == [0x02, 0x07]  # POF -> DSLP (0xA5)

    # Verify VolminiApp renders cleanly at 800x480 GDEY075T7 resolution
    hal_75 = DesktopHAL(display_profile="gdey075t7_800x480", storage_root=str(tmp_path))
    app_75 = VolminiApp(hal_75)
    app_75.run_boot_sequence(interactive_wait=False)
    assert hal_75.width == 800 and hal_75.height == 480
    assert app_75.layout_model.viewport_scale_cols >= 72
    cfg = load_hardware_config()
    assert "display_profile" in cfg


def test_dynamic_top_ribbon_and_pointer_touchpad_interaction(tmp_path):
    hal = DesktopHAL(display_profile="gdey075t7_800x480", storage_root=str(tmp_path))
    app = VolminiApp(hal)
    app.run_boot_sequence(interactive_wait=False)

    assert app.show_ribbon is True
    assert len(app.ribbon_hitboxes) >= 15

    # Find hitboxes for Bold ("fmt:bold"), Heading 1 ("style:h1"), Center ("align:center"), and Outline ("act:outline")
    hb_map = {act: (x, y, w, h) for (x, y, w, h, act) in app.ribbon_hitboxes}
    assert "fmt:bold" in hb_map
    assert "style:h1" in hb_map
    assert "align:center" in hb_map
    assert "act:outline" in hb_map

    # 1. Click Bold button on the Dynamic Simplified Top Ribbon with pointer
    bx, by, bw, bh = hb_map["fmt:bold"]
    assert app.doc.active_bold is False
    hal.push_pointer(bx + bw // 2, by + bh // 2, clicked=True)
    app.tick()
    assert hal.pointer_visible is True
    assert app.doc.active_bold is True

    # 2. Click Center Align button on Ribbon
    cx, cy, cw, ch = hb_map["align:center"]
    hal.push_pointer(cx + cw // 2, cy + ch // 2, clicked=True)
    app.tick()
    assert app.doc.current_paragraph.align == "center"

    # 3. Click first line on the Paper Sheet to move cursor to Paragraph 0 (Title)
    assert len(app.line_hitboxes) >= 2
    first_line = app.line_hitboxes[0]
    hal.push_pointer(first_line["x0"] + 40, (first_line["y0"] + first_line["y1"]) // 2, clicked=True)
    app.tick()
    assert app.doc.cursor_para == 0
    assert app.doc.current_paragraph.style == "title"

    # 4. Click Outline button on Ribbon to open Chapter Outline Navigator, then click [X] to close
    ox, oy, ow, oh = hb_map["act:outline"]
    hal.push_pointer(ox + ow // 2, oy + oh // 2, clicked=True)
    app.tick()
    assert app.view == ViewState.OUTLINE

    # Click [X] in top-right of modal frame
    hal.push_pointer(hal.width - 20, 16, clicked=True)
    app.tick()
    assert app.view == ViewState.EDITOR


def test_touchpad5_click_iqs550_driver():
    from volmini.hal.touchpad5 import Touchpad5ClickDriver

    class MockPin:
        def __init__(self, val=1):
            self.val = val
        def value(self, v=None):
            if v is not None:
                self.val = v
            return self.val

    class MockI2C:
        def __init__(self):
            self.writes = []
            self.next_burst = bytes([0] * 9)

        def writeto(self, addr, buf):
            self.writes.append((addr, bytes(buf)))

        def readfrom(self, addr, nbytes):
            return self.next_burst[:nbytes]

    rdy = MockPin(1)
    i2c = MockI2C()
    tp = Touchpad5ClickDriver(i2c=i2c, rdy_pin=rdy, sensitivity=1)

    # 1. Simulate single-finger move (RelX = +12, RelY = -5) + SINGLE_TAP (0x01)
    i2c.next_burst = bytes([
        0x01,        # GestureEvents0: SINGLE_TAP
        0x00,        # GestureEvents1
        0x00, 0x00,  # SystemInfo0/1
        0x01,        # NoOfFingers = 1
        0x00, 0x0C,  # RelX = +12 (big-endian int16)
        0xFF, 0xFB,  # RelY = -5 (big-endian int16)
    ])
    res = tp.poll(curr_x=100, curr_y=100, screen_w=800, screen_h=480)
    assert res is not None
    nx, ny, ev = res
    assert nx == 112
    assert ny == 95
    assert ev.clicked is True
    assert ev.pressed is True
    # Verify register 0x000D read and 0xEEEE End Communication Window write
    assert i2c.writes[0] == (0x74, b"\x00\x0d")
    assert i2c.writes[1] == (0x74, b"\xee\xee\x00")

    # 2. Simulate two-finger scroll (GestureEvents1 = TWO_FINGER_SCROLL 0x02, Fingers=2, RelY=+10)
    i2c.next_burst = bytes([0x00, 0x02, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x0A])
    res2 = tp.poll(curr_x=112, curr_y=95, screen_w=800, screen_h=480)
    assert res2 is not None
    _, _, ev2 = res2
    assert ev2.scroll_y == 1

    # 3. Verify RDY=0 skips I2C bus transaction completely
    i2c.writes.clear()
    rdy.value(0)
    assert tp.poll(112, 95, 800, 480) is None
    assert len(i2c.writes) == 0


def test_usb_hid_and_60pct_keyboard_decoder():
    from volmini.hal.usb_hid_kb import USBHIDKeyboardDecoder, MOD_LSHIFT, MOD_LCTRL, MOD_LALT

    dec = USBHIDKeyboardDecoder()

    # 1. Standard 8-byte USB HID report: Shift + 'a' (0x04) -> 'A'
    evs = dec.decode_hid_report(bytes([MOD_LSHIFT, 0x00, 0x04, 0, 0, 0, 0, 0]))
    assert len(evs) == 1
    assert evs[0].char == "A"
    # Key release report clears rollover state
    dec.decode_hid_report(bytes([0] * 8))

    # 2. CH9350L framed 11-byte UART packet: Ctrl + 'b' (0x05) -> KeyCode.CTRL_B
    ch9350_pkt = bytes([0x57, 0xAB, 0x01, MOD_LCTRL, 0x00, 0x05, 0, 0, 0, 0, 0])
    evs2 = dec.decode_hid_report(ch9350_pkt)
    assert len(evs2) == 1
    assert evs2[0].key == KeyCode.CTRL_B
    dec.decode_hid_report(bytes([0] * 8))

    # 3. 60% Keyboard Alt+2 (0x1F) -> KeyCode.F2_OUTLINE & Alt+I (0x0C) -> KeyCode.UP
    evs3 = dec.decode_hid_report(bytes([MOD_LALT, 0x00, 0x1F, 0, 0, 0, 0, 0]))
    assert len(evs3) == 1 and evs3[0].key == KeyCode.F2_OUTLINE
    dec.decode_hid_report(bytes([0] * 8))

    evs4 = dec.decode_hid_report(bytes([MOD_LALT, 0x00, 0x0C, 0, 0, 0, 0, 0]))
    assert len(evs4) == 1 and evs4[0].key == KeyCode.UP

    # 4. ANSI / UART Escape stream (Up arrow + Alt+3 -> F3_REFERENCE)
    ansi_evs = dec.decode_ansi_stream(b"\x1b[A\x1b3Hi")
    assert [e.key for e in ansi_evs] == [KeyCode.UP, KeyCode.F3_REFERENCE, "H", "i"]
