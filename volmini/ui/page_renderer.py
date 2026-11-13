"""Monochrome Print-Accurate Page Sheet & Dynamic Top Ribbon Renderer for Volmini.

Renders:
- Top Status Bar (filename, dirty flag, mode, page number, battery, clickable `[Rib]` toggle)
- Dynamic Simplified Top Ribbon:
  - Paragraph Styles: `[Title] [H1] [H2] [Quote] [Body]` (dynamically inverted for active paragraph)
  - Inline Formatting: `[B] [I] [U]` (dynamically inverted when active at cursor)
  - Alignment: `[L] [C] [R]` (dynamically inverted for active paragraph alignment)
  - Studio Tools: `[Save] [Outl] [Ref] [Rev] [Crv] [BLE] [Pg]`
- Discrete physical paper sheet with print margins and crop ticks (no textures)
- Running page headers and footers
- Accurately aligned and styled lines (Title, H1-H3, Blockquote, Normal)
- Inline Bold, Italic, and Underline spans
- Non-destructive dotted underlines for Revision Lens / Spell Check findings
- Active cursor caret, pointer hit-testing regions, and monochrome pointer arrow cursor
"""

from volmini.ui.font5x8 import (
    draw_char, draw_text, measure_spans_px,
    CHAR_ADVANCE, LINE_HEIGHT
)


class PageRenderer:
    """Renders the active PageSheet, Dynamic Top Ribbon, and status bars onto the 1-bit FrameBuffer."""

    TOP_BAR_H = 12
    RIBBON_H = 14
    BOT_BAR_H = 12

    @classmethod
    def render_editor(
        cls,
        fb,
        doc,
        pages: list,
        cursor_loc: tuple,
        layout_model,
        document_mode: str,
        corvus,
        active_filename: str,
        findings: list = None,
        show_lenses: bool = False,
        battery_pct: int = 100,
        status_toast: str = "",
        show_ribbon: bool = True,
        pointer_pos: tuple = None,
        hitboxes: list = None,
        line_hitboxes: list = None,
    ) -> None:
        w = fb.width
        h = fb.height
        if hitboxes is not None:
            hitboxes.clear()
        if line_hitboxes is not None:
            line_hitboxes.clear()

        # Desk background = 0 (black), Paper sheet = 1 (white), Ink on paper = 0 (black)
        fb.fill(0)

        page_idx, line_idx_in_page, col_in_line = cursor_loc
        page_idx = max(0, min(len(pages) - 1, page_idx))
        page = pages[page_idx]

        # 1. Top Status Bar (12px high, inverted dark bar with white text)
        cls._render_top_bar(
            fb, active_filename, doc.dirty, document_mode,
            page.page_number, len(pages), battery_pct, show_ribbon, hitboxes
        )

        # 2. Dynamic Simplified Top Ribbon (14px high, reflects active formatting at cursor)
        ribbon_offset = 0
        if show_ribbon:
            cls._render_ribbon(fb, doc, show_lenses, corvus, pointer_pos, hitboxes)
            ribbon_offset = cls.RIBBON_H

        # 3. Bottom Status Bar (12px high, word count + format summary + sprint/toast)
        cls._render_bottom_bar(fb, doc, pages, corvus, status_toast, show_lenses, findings)

        # 4. Paper Sheet Geometry inside viewport
        view_y = cls.TOP_BAR_H + ribbon_offset + 2
        view_h = h - cls.TOP_BAR_H - ribbon_offset - cls.BOT_BAR_H - 4
        sheet_margin_x = max(6, w // 50)
        sheet_x = sheet_margin_x
        sheet_w = w - sheet_margin_x * 2
        sheet_y = view_y
        sheet_h = max(60, view_h)

        # Draw crisp white paper sheet with 1px black inner border
        fb.fill_rect(sheet_x, sheet_y, sheet_w, sheet_h, 1)
        fb.rect(sheet_x, sheet_y, sheet_w, sheet_h, 0)

        # Compute horizontal margin inset in pixels proportional to layout_model.margins
        raw_w_in, _ = layout_model.raw_dimensions_inches
        left_ratio = layout_model.margins.left / max(4.0, raw_w_in)
        right_ratio = layout_model.margins.right / max(4.0, raw_w_in)
        pad_left = max(10, int(round(sheet_w * left_ratio * 0.65)))
        pad_right = max(10, int(round(sheet_w * right_ratio * 0.65)))

        content_x = sheet_x + pad_left
        content_w = max(120, sheet_w - pad_left - pad_right)
        content_right = content_x + content_w

        # Prepress crop marks at print margin corners
        crop_top_y = sheet_y + 13
        crop_bot_y = sheet_y + sheet_h - 13
        cls._draw_crop_marks(fb, content_x, content_right, crop_top_y, crop_bot_y)

        # Running Header (if not suppressed on first page)
        if not page.header_suppressed:
            hy = sheet_y + 3
            if page.header_left:
                draw_text(fb, page.header_left, content_x, hy, color=0, italic=True)
            if page.header_center:
                cw = len(page.header_center) * CHAR_ADVANCE
                draw_text(fb, page.header_center, content_x + max(0, (content_w - cw) // 2), hy, color=0, italic=True)
            if page.header_right:
                rw = len(page.header_right) * CHAR_ADVANCE
                draw_text(fb, page.header_right, max(content_x, content_right - rw), hy, color=0, italic=True)

        # Running Footer
        if not page.header_suppressed:
            fy = sheet_y + sheet_h - 10
            if page.footer_left:
                draw_text(fb, page.footer_left, content_x, fy, color=0)
            if page.footer_center:
                cw = len(page.footer_center) * CHAR_ADVANCE
                draw_text(fb, page.footer_center, content_x + max(0, (content_w - cw) // 2), fy, color=0)
            if page.footer_right:
                rw = len(page.footer_right) * CHAR_ADVANCE
                draw_text(fb, page.footer_right, max(content_x, content_right - rw), fy, color=0)

        # 5. Viewport Scrolling inside the current PageSheet
        body_top_y = crop_top_y + 3
        body_avail_h = max(36, crop_bot_y - body_top_y - 2)
        visible_line_slots = max(4, body_avail_h // LINE_HEIGHT)

        # Keep active cursor line comfortably in view (Typewriter / dynamic autoscroll)
        start_line_idx = 0
        if line_idx_in_page >= visible_line_slots - 1:
            start_line_idx = max(0, line_idx_in_page - visible_line_slots + 2)

        # Index lens findings by paragraph for fast underline rendering
        para_findings = {}
        if show_lenses and findings:
            for f in findings:
                para_findings.setdefault(f.para_idx, []).append(f)

        curr_y = body_top_y
        for l_idx in range(start_line_idx, len(page.lines)):
            ln = page.lines[l_idx]
            is_tall = ln.style in ("title", "h1")
            scale_y = 2 if is_tall else 1
            row_h = LINE_HEIGHT * scale_y

            if curr_y + row_h > crop_bot_y:
                break

            force_bold = ln.style in ("title", "h1", "h2", "h3")
            force_italic = ln.style == "quote"
            force_underline = ln.style == "h2"

            line_px_w = measure_spans_px(ln.spans, force_bold=force_bold)
            indent_x = 0
            if ln.style == "quote":
                indent_x = 12
                fb.vline(content_x + 4, curr_y, row_h - 1, 0)
                fb.vline(content_x + 5, curr_y, row_h - 1, 0)

            if ln.align == "center":
                start_x = content_x + max(0, (content_w - line_px_w) // 2)
            elif ln.align == "right":
                start_x = max(content_x, content_right - line_px_w)
            else:
                start_x = content_x + indent_x

            draw_x = start_x
            char_cursor_in_line = 0
            cursor_px_x = start_x
            char_x_positions = [start_x]

            for span in ln.spans:
                is_b = span.bold or force_bold
                is_i = span.italic or force_italic
                is_u = span.underline or force_underline
                for ch in span.text:
                    if l_idx == line_idx_in_page and char_cursor_in_line == col_in_line:
                        cursor_px_x = draw_x
                    adv = draw_char(
                        fb, ch, draw_x, curr_y,
                        color=0, bold=is_b, italic=is_i, underline=is_u, scale_y=scale_y
                    )
                    abs_char_idx = ln.char_start + char_cursor_in_line
                    if ln.para_idx in para_findings:
                        for f in para_findings[ln.para_idx]:
                            if f.start_pos <= abs_char_idx < f.end_pos:
                                sq_y = curr_y + row_h - 1
                                fb.pixel(draw_x + 1, sq_y, 0)
                                fb.pixel(draw_x + 3, sq_y, 0)
                                fb.pixel(draw_x + 5, sq_y, 0)
                                break

                    draw_x += adv
                    char_cursor_in_line += 1
                    char_x_positions.append(draw_x)

            if l_idx == line_idx_in_page and col_in_line >= char_cursor_in_line:
                cursor_px_x = draw_x

            if ln.style == "title" and ln.text:
                fb.hline(start_x, curr_y + row_h - 2, min(content_w, line_px_w), 0)

            if l_idx == line_idx_in_page:
                fb.vline(cursor_px_x, curr_y, row_h - 1, 0)
                fb.vline(cursor_px_x + 1, curr_y, row_h - 1, 0)

            # Record line hitbox for pointer click-to-place-cursor
            if line_hitboxes is not None:
                line_hitboxes.append({
                    "y0": curr_y,
                    "y1": curr_y + row_h,
                    "x0": sheet_x,
                    "x1": sheet_x + sheet_w,
                    "para_idx": ln.para_idx,
                    "char_start": ln.char_start,
                    "char_x": char_x_positions,
                })

            curr_y += row_h

    @classmethod
    def _render_ribbon(
        cls,
        fb,
        doc,
        show_lenses: bool,
        corvus,
        pointer_pos: tuple,
        hitboxes: list,
    ) -> None:
        """Draws the Dynamic Simplified Top Ribbon with live active-formatting state."""
        w = fb.width
        ry = cls.TOP_BAR_H
        rh = cls.RIBBON_H

        # Crisp light toolbar strip with black bottom rule
        fb.fill_rect(0, ry, w, rh, 1)
        fb.hline(0, ry + rh - 1, w, 0)

        p_style = doc.current_paragraph.style
        p_align = doc.current_paragraph.align
        wide = w >= 520  # Full labels on GDEY075T7 800x480, compact labels on 320..480px

        # Button tuples: (label, action_id, is_active, bold_lbl, italic_lbl, underline_lbl)
        groups = [
            # 1. Paragraph Styles
            [
                ("Title" if wide else "Ttl", "style:title", p_style == "title", True, False, False),
                ("H1", "style:h1", p_style == "h1", True, False, False),
                ("H2", "style:h2", p_style == "h2", True, False, False),
                ("Quote" if wide else "Quo", "style:quote", p_style == "quote", False, True, False),
                ("Body" if wide else "Bod", "style:normal", p_style == "normal", False, False, False),
            ],
            # 2. Inline Formatting (reflects active cursor span / toggle state)
            [
                ("B", "fmt:bold", doc.active_bold, True, False, False),
                ("I", "fmt:italic", doc.active_italic, False, True, False),
                ("U", "fmt:underline", doc.active_underline, False, False, True),
            ],
            # 3. Paragraph Alignment
            [
                ("L", "align:left", p_align == "left", False, False, False),
                ("C", "align:center", p_align == "center", False, False, False),
                ("R", "align:right", p_align == "right", False, False, False),
            ],
            # 4. Studio Actions & Overlays
            [
                ("Save" if wide else "Sav", "act:save", False, False, False, False),
                ("Outline" if wide else "Out", "act:outline", False, False, False, False),
                ("Ref", "act:reference", False, False, False, False),
                ("Review" if wide else "Rev", "act:review", show_lenses, False, False, False),
                ("Corvus" if wide else "Crv", "act:corvus", corvus.sprint_active, False, False, False),
                ("BLE", "act:ble", False, False, False, False),
                ("Page" if wide else "Pg", "act:setup", False, False, False, False),
            ],
        ]

        curr_x = 3
        btn_y = ry + 1
        btn_h = rh - 3
        pad_x = 4 if wide else 2

        for g_idx, group in enumerate(groups):
            for label, action_id, is_active, b_flag, i_flag, u_flag in group:
                char_w = CHAR_ADVANCE + (1 if b_flag else 0)
                btn_w = len(label) * char_w + pad_x * 2
                if curr_x + btn_w > w - 2:
                    break

                is_hover = False
                if pointer_pos is not None:
                    px, py = pointer_pos
                    is_hover = (curr_x <= px < curr_x + btn_w) and (btn_y <= py < btn_y + btn_h)

                if is_active:
                    # Active state: solid black button pill with white text
                    fb.fill_rect(curr_x, btn_y, btn_w, btn_h, 0)
                    draw_text(
                        fb, label, curr_x + pad_x, btn_y + 2,
                        color=1, bold=b_flag, italic=i_flag, underline=u_flag
                    )
                else:
                    # Inactive state: white pill with subtle border (or bold frame on pointer hover)
                    if is_hover:
                        fb.rect(curr_x, btn_y, btn_w, btn_h, 0)
                    draw_text(
                        fb, label, curr_x + pad_x, btn_y + 2,
                        color=0, bold=b_flag, italic=i_flag, underline=u_flag
                    )

                if hitboxes is not None:
                    hitboxes.append((curr_x, btn_y, btn_w, btn_h, action_id))

                curr_x += btn_w + (2 if wide else 1)

            # Draw vertical separator between ribbon groups
            if g_idx < len(groups) - 1 and curr_x + 4 < w:
                fb.vline(curr_x + 1, ry + 2, rh - 5, 0)
                curr_x += 4 if wide else 3

    @staticmethod
    def _draw_crop_marks(fb, left_x: int, right_x: int, top_y: int, bot_y: int) -> None:
        fb.hline(left_x - 5, top_y, 4, 0)
        fb.vline(left_x, top_y - 5, 4, 0)
        fb.hline(right_x + 2, top_y, 4, 0)
        fb.vline(right_x, top_y - 5, 4, 0)
        fb.hline(left_x - 5, bot_y, 4, 0)
        fb.vline(left_x, bot_y + 2, 4, 0)
        fb.hline(right_x + 2, bot_y, 4, 0)
        fb.vline(right_x, bot_y + 2, 4, 0)

    @staticmethod
    def _render_top_bar(
        fb,
        filename: str,
        dirty: bool,
        mode: str,
        page_num: int,
        total_pages: int,
        bat_pct: int,
        show_ribbon: bool,
        hitboxes: list = None,
    ) -> None:
        w = fb.width
        fb.fill_rect(0, 0, w, 11, 0)
        short_name = filename.replace("\\", "/").split("/")[-1] if filename else "untitled.md"
        dirty_mark = "*" if dirty else ""
        mode_tag = "FIC" if mode == "creative_fiction" else "NONFIC"

        left_str = f"V| {short_name}{dirty_mark} [{mode_tag}]"
        draw_text(fb, left_str, 4, 2, color=1)

        # Clickable mode & ribbon toggle pills in top bar
        rib_lbl = "[Rib:ON]" if show_ribbon else "[Rib:OFF]"
        right_str = f"{rib_lbl} Pg {page_num}/{total_pages} BAT:{bat_pct}%"
        rw = len(right_str) * CHAR_ADVANCE
        rx = max(150, w - rw - 4)
        draw_text(fb, right_str, rx, 2, color=1)

        if hitboxes is not None:
            rib_w = len(rib_lbl) * CHAR_ADVANCE
            hitboxes.append((rx, 0, rib_w, 11, "act:toggle_ribbon"))
            hitboxes.append((4, 0, len(left_str) * CHAR_ADVANCE, 11, "act:launcher"))

    @staticmethod
    def _render_bottom_bar(fb, doc, pages: list, corvus, status_toast: str, show_lenses: bool, findings: list) -> None:
        w = fb.width
        y = fb.height - 11
        fb.fill_rect(0, y - 1, w, 12, 0)

        fmt_flags = []
        if doc.active_bold:
            fmt_flags.append("B")
        if doc.active_italic:
            fmt_flags.append("I")
        if doc.active_underline:
            fmt_flags.append("U")
        p_style = doc.current_paragraph.style.upper()
        p_align = doc.current_paragraph.align[0].upper()
        fmt_str = f"{p_style}:{p_align}" + (f"+{''.join(fmt_flags)}" if fmt_flags else "")

        words = len(doc.to_plain_text().split())
        if status_toast:
            mid_str = status_toast[:44]
        elif corvus.sprint_active:
            rem = corvus.sprint_remaining_seconds()
            mm, ss = rem // 60, rem % 60
            mid_str = f"Sprint {mm:02d}:{ss:02d}"
        elif show_lenses and findings is not None:
            mid_str = f"Lenses: {len(findings)} items"
        else:
            mid_str = "F1:Help F2:Outl F3:Ref F4:Rev F5:Corvus F6:BLE"

        left_info = f"{words}w | {fmt_str}"
        draw_text(fb, left_info, 4, y + 1, color=1)

        mw = len(mid_str) * CHAR_ADVANCE
        draw_text(fb, mid_str, max(120, w - mw - 4), y + 1, color=1)

    @staticmethod
    def draw_pointer_cursor(fb, x: int, y: int) -> None:
        """Draws a high-contrast 8x10 monochrome arrow cursor (white outline + black fill)."""
        # Row masks: (outline_mask, fill_mask) MSB-first 8 bits wide
        cursor_rows = (
            (0b11000000, 0b10000000),
            (0b11100000, 0b11000000),
            (0b11110000, 0b11100000),
            (0b11111000, 0b11110000),
            (0b11111100, 0b11111000),
            (0b11111110, 0b11111100),
            (0b11111000, 0b11011000),
            (0b11011100, 0b10001100),
            (0b00001100, 0b00000100),
        )
        for ry, (out_m, fill_m) in enumerate(cursor_rows):
            py = y + ry
            if py < 0 or py >= fb.height:
                continue
            for rx in range(8):
                px = x + rx
                if px < 0 or px >= fb.width:
                    continue
                bit = 0x80 >> rx
                if fill_m & bit:
                    fb.pixel(px, py, 0)
                elif out_m & bit:
                    fb.pixel(px, py, 1)
