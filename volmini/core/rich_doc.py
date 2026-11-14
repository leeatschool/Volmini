"""Structured rich-text document model for Volmini's print-accurate WYSIWYG editor.

Supports:
- Paragraph styles: title, h1, h2, h3, normal, quote
- Paragraph alignments: left, center, right
- Inline character styles: bold, italic, underline
- Explicit page breaks
- Bounded Undo/Redo stack
- Clean Markdown (.md) and Plain Text (.txt) serialization
"""

import re


class TextSpan:
    """Contiguous run of text sharing identical inline formatting."""

    def __init__(self, text: str = "", bold: bool = False, italic: bool = False, underline: bool = False):
        self.text = str(text)
        self.bold = bool(bold)
        self.italic = bool(italic)
        self.underline = bool(underline)

    def same_format(self, bold: bool, italic: bool, underline: bool) -> bool:
        return self.bold == bold and self.italic == italic and self.underline == underline

    def clone(self) -> "TextSpan":
        return TextSpan(self.text, self.bold, self.italic, self.underline)

    def to_dict(self) -> dict:
        d = {"t": self.text}
        if self.bold:
            d["b"] = 1
        if self.italic:
            d["i"] = 1
        if self.underline:
            d["u"] = 1
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextSpan":
        return cls(
            text=d.get("t", ""),
            bold=bool(d.get("b", 0)),
            italic=bool(d.get("i", 0)),
            underline=bool(d.get("u", 0)),
        )


class Paragraph:
    """Single document paragraph with block style, alignment, and inline TextSpans."""

    VALID_STYLES = ("title", "h1", "h2", "h3", "normal", "quote")
    VALID_ALIGNS = ("left", "center", "right")

    def __init__(
        self,
        style: str = "normal",
        align: str = "left",
        spans: list = None,
        page_break_before: bool = False,
    ):
        self.style = style if style in self.VALID_STYLES else "normal"
        self.align = align if align in self.VALID_ALIGNS else "left"
        self.spans = [s.clone() for s in spans] if spans else []
        self.page_break_before = bool(page_break_before)
        self._normalize_spans()

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    def __len__(self) -> int:
        return sum(len(s.text) for s in self.spans)

    def clone(self) -> "Paragraph":
        return Paragraph(
            style=self.style,
            align=self.align,
            spans=[s.clone() for s in self.spans],
            page_break_before=self.page_break_before,
        )

    def _normalize_spans(self) -> None:
        """Merges adjacent spans with identical formatting and drops empty spans."""
        merged = []
        for s in self.spans:
            if not s.text:
                continue
            if merged and merged[-1].same_format(s.bold, s.italic, s.underline):
                merged[-1].text += s.text
            else:
                merged.append(s)
        self.spans = merged

    def char_format_at(self, offset: int):
        """Returns (bold, italic, underline) at character offset."""
        if not self.spans:
            return (False, False, False)
        pos = 0
        for s in self.spans:
            end = pos + len(s.text)
            if offset <= end:
                return (s.bold, s.italic, s.underline)
            pos = end
        last = self.spans[-1]
        return (last.bold, last.italic, last.underline)

    def insert_at(self, offset: int, ch: str, bold: bool = False, italic: bool = False, underline: bool = False) -> None:
        if not ch:
            return
        if not self.spans:
            self.spans.append(TextSpan(ch, bold, italic, underline))
            return

        offset = max(0, min(len(self), offset))
        new_spans = []
        pos = 0
        inserted = False
        for s in self.spans:
            end = pos + len(s.text)
            if not inserted and pos <= offset <= end:
                rel = offset - pos
                left = s.text[:rel]
                right = s.text[rel:]
                if left:
                    new_spans.append(TextSpan(left, s.bold, s.italic, s.underline))
                new_spans.append(TextSpan(ch, bold, italic, underline))
                if right:
                    new_spans.append(TextSpan(right, s.bold, s.italic, s.underline))
                inserted = True
            else:
                new_spans.append(s)
            pos = end

        if not inserted:
            new_spans.append(TextSpan(ch, bold, italic, underline))
        self.spans = new_spans
        self._normalize_spans()

    def delete_range(self, start: int, end: int) -> None:
        if end <= start or not self.spans:
            return
        new_spans = []
        pos = 0
        for s in self.spans:
            s_end = pos + len(s.text)
            if s_end <= start or pos >= end:
                new_spans.append(s)
            else:
                keep_left = s.text[:max(0, start - pos)]
                keep_right = s.text[max(0, end - pos):]
                kept = keep_left + keep_right
                if kept:
                    new_spans.append(TextSpan(kept, s.bold, s.italic, s.underline))
            pos = s_end
        self.spans = new_spans
        self._normalize_spans()

    def slice_spans(self, start: int, end: int) -> list:
        """Extracts a list of TextSpan objects for the substring [start:end]."""
        if end <= start or not self.spans:
            return []
        result = []
        pos = 0
        for s in self.spans:
            s_end = pos + len(s.text)
            if s_end > start and pos < end:
                sub_start = max(0, start - pos)
                sub_end = min(len(s.text), end - pos)
                sub_text = s.text[sub_start:sub_end]
                if sub_text:
                    result.append(TextSpan(sub_text, s.bold, s.italic, s.underline))
            pos = s_end
        return result

    def apply_format_range(self, start: int, end: int, bold=None, italic=None, underline=None) -> None:
        """Updates inline formatting across character range [start:end]."""
        if end <= start or not self.spans:
            return
        left_spans = self.slice_spans(0, start)
        mid_spans = self.slice_spans(start, end)
        right_spans = self.slice_spans(end, len(self))
        for s in mid_spans:
            if bold is not None:
                s.bold = bool(bold)
            if italic is not None:
                s.italic = bool(italic)
            if underline is not None:
                s.underline = bool(underline)
        self.spans = left_spans + mid_spans + right_spans
        self._normalize_spans()


class RichDocument:
    """Print-accurate document buffer with paragraph/inline formatting and Undo/Redo."""

    MAX_UNDO = 16

    def __init__(self):
        self.paragraphs = [Paragraph("normal", "left")]
        self.cursor_para = 0
        self.cursor_offset = 0
        self.active_bold = False
        self.active_italic = False
        self.active_underline = False
        self.dirty = False
        self._undo_stack = []
        self._redo_stack = []

    def clear(self) -> None:
        self.paragraphs = [Paragraph("normal", "left")]
        self.cursor_para = 0
        self.cursor_offset = 0
        self.active_bold = False
        self.active_italic = False
        self.active_underline = False
        self.dirty = False
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _push_undo(self) -> None:
        snap = (
            [p.clone() for p in self.paragraphs],
            self.cursor_para,
            self.cursor_offset,
        )
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        current = (
            [p.clone() for p in self.paragraphs],
            self.cursor_para,
            self.cursor_offset,
        )
        self._redo_stack.append(current)
        paras, cp, co = self._undo_stack.pop()
        self.paragraphs = paras
        self.cursor_para = cp
        self.cursor_offset = co
        self.dirty = True
        self._sync_active_format()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        current = (
            [p.clone() for p in self.paragraphs],
            self.cursor_para,
            self.cursor_offset,
        )
        self._undo_stack.append(current)
        paras, cp, co = self._redo_stack.pop()
        self.paragraphs = paras
        self.cursor_para = cp
        self.cursor_offset = co
        self.dirty = True
        self._sync_active_format()
        return True

    @property
    def current_paragraph(self) -> Paragraph:
        self._clamp_cursor()
        return self.paragraphs[self.cursor_para]

    def _clamp_cursor(self) -> None:
        if not self.paragraphs:
            self.paragraphs = [Paragraph("normal", "left")]
        self.cursor_para = max(0, min(len(self.paragraphs) - 1, self.cursor_para))
        p_len = len(self.paragraphs[self.cursor_para])
        self.cursor_offset = max(0, min(p_len, self.cursor_offset))

    def _sync_active_format(self) -> None:
        self._clamp_cursor()
        p = self.paragraphs[self.cursor_para]
        if len(p) > 0:
            probe = max(0, self.cursor_offset - 1) if self.cursor_offset > 0 else 0
            self.active_bold, self.active_italic, self.active_underline = p.char_format_at(probe)

    # --- Editing Operations ---

    def insert_text(self, text: str) -> None:
        if not text:
            return
        self._push_undo()
        self._clamp_cursor()
        parts = text.replace("\r\n", "\n").split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                self._split_paragraph_internal()
            if part:
                p = self.paragraphs[self.cursor_para]
                p.insert_at(
                    self.cursor_offset,
                    part,
                    bold=self.active_bold,
                    italic=self.active_italic,
                    underline=self.active_underline,
                )
                self.cursor_offset += len(part)
        self.dirty = True

    def _split_paragraph_internal(self) -> None:
        p = self.paragraphs[self.cursor_para]
        left_spans = p.slice_spans(0, self.cursor_offset)
        right_spans = p.slice_spans(self.cursor_offset, len(p))
        p.spans = left_spans
        p._normalize_spans()

        # After a heading or title, Enter automatically transitions to normal body paragraph
        next_style = "normal" if p.style in ("title", "h1", "h2", "h3") else p.style
        next_align = "left" if p.style in ("title", "h1", "h2", "h3") else p.align
        new_p = Paragraph(style=next_style, align=next_align, spans=right_spans)
        self.paragraphs.insert(self.cursor_para + 1, new_p)
        self.cursor_para += 1
        self.cursor_offset = 0

    def split_paragraph(self) -> None:
        self._push_undo()
        self._clamp_cursor()
        self._split_paragraph_internal()
        self.dirty = True

    def backspace(self) -> bool:
        self._clamp_cursor()
        if self.cursor_offset > 0:
            self._push_undo()
            p = self.paragraphs[self.cursor_para]
            p.delete_range(self.cursor_offset - 1, self.cursor_offset)
            self.cursor_offset -= 1
            self.dirty = True
            return True
        elif self.cursor_para > 0:
            self._push_undo()
            curr_p = self.paragraphs.pop(self.cursor_para)
            self.cursor_para -= 1
            prev_p = self.paragraphs[self.cursor_para]
            join_offset = len(prev_p)
            prev_p.spans.extend(curr_p.spans)
            prev_p._normalize_spans()
            self.cursor_offset = join_offset
            self.dirty = True
            return True
        elif self.paragraphs[self.cursor_para].page_break_before:
            self._push_undo()
            self.paragraphs[self.cursor_para].page_break_before = False
            self.dirty = True
            return True
        return False

    def delete_forward(self) -> bool:
        self._clamp_cursor()
        p = self.paragraphs[self.cursor_para]
        if self.cursor_offset < len(p):
            self._push_undo()
            p.delete_range(self.cursor_offset, self.cursor_offset + 1)
            self.dirty = True
            return True
        elif self.cursor_para < len(self.paragraphs) - 1:
            self._push_undo()
            next_p = self.paragraphs.pop(self.cursor_para + 1)
            p.spans.extend(next_p.spans)
            p._normalize_spans()
            self.dirty = True
            return True
        return False

    # --- Formatting Operations ---

    def _word_bounds_at_cursor(self):
        """Returns (start, end) of word under cursor only when cursor is strictly inside a word."""
        p = self.current_paragraph
        txt = p.text
        if not txt or self.cursor_offset <= 0 or self.cursor_offset >= len(txt):
            return None
        if not ((txt[self.cursor_offset - 1].isalnum() or txt[self.cursor_offset - 1] == "'") and
                (txt[self.cursor_offset].isalnum() or txt[self.cursor_offset] == "'")):
            return None
        s = self.cursor_offset - 1
        while s > 0 and (txt[s - 1].isalnum() or txt[s - 1] == "'"):
            s -= 1
        e = self.cursor_offset + 1
        while e < len(txt) and (txt[e].isalnum() or txt[e] == "'"):
            e += 1
        return (s, e) if e > s else None

    def toggle_bold(self) -> bool:
        self.active_bold = not self.active_bold
        bounds = self._word_bounds_at_cursor()
        if bounds:
            self._push_undo()
            self.current_paragraph.apply_format_range(bounds[0], bounds[1], bold=self.active_bold)
            self.dirty = True
        return self.active_bold

    def toggle_italic(self) -> bool:
        self.active_italic = not self.active_italic
        bounds = self._word_bounds_at_cursor()
        if bounds:
            self._push_undo()
            self.current_paragraph.apply_format_range(bounds[0], bounds[1], italic=self.active_italic)
            self.dirty = True
        return self.active_italic

    def toggle_underline(self) -> bool:
        self.active_underline = not self.active_underline
        bounds = self._word_bounds_at_cursor()
        if bounds:
            self._push_undo()
            self.current_paragraph.apply_format_range(bounds[0], bounds[1], underline=self.active_underline)
            self.dirty = True
        return self.active_underline

    def set_paragraph_style(self, style: str) -> None:
        if style not in Paragraph.VALID_STYLES:
            return
        self._push_undo()
        p = self.current_paragraph
        p.style = style
        if style == "title":
            p.align = "center"
        self.dirty = True

    def set_paragraph_align(self, align: str) -> None:
        if align not in Paragraph.VALID_ALIGNS:
            return
        self._push_undo()
        self.current_paragraph.align = align
        self.dirty = True

    def insert_page_break(self) -> None:
        self._push_undo()
        self._clamp_cursor()
        if self.cursor_offset > 0:
            self._split_paragraph_internal()
        self.paragraphs[self.cursor_para].page_break_before = True
        self.dirty = True

    def replace_in_paragraph(self, para_idx: int, start: int, end: int, replacement: str) -> bool:
        if not (0 <= para_idx < len(self.paragraphs)):
            return False
        self._push_undo()
        p = self.paragraphs[para_idx]
        b, i, u = p.char_format_at(start)
        p.delete_range(start, end)
        p.insert_at(start, replacement, bold=b, italic=i, underline=u)
        self.cursor_para = para_idx
        self.cursor_offset = start + len(replacement)
        self.dirty = True
        return True

    # --- Cursor Navigation & Coordinate Conversion ---

    def move_left(self) -> None:
        self._clamp_cursor()
        if self.cursor_offset > 0:
            self.cursor_offset -= 1
        elif self.cursor_para > 0:
            self.cursor_para -= 1
            self.cursor_offset = len(self.paragraphs[self.cursor_para])
        self._sync_active_format()

    def move_right(self) -> None:
        self._clamp_cursor()
        p_len = len(self.paragraphs[self.cursor_para])
        if self.cursor_offset < p_len:
            self.cursor_offset += 1
        elif self.cursor_para < len(self.paragraphs) - 1:
            self.cursor_para += 1
            self.cursor_offset = 0
        self._sync_active_format()

    def move_home(self) -> None:
        self._clamp_cursor()
        self.cursor_offset = 0
        self._sync_active_format()

    def move_end(self) -> None:
        self._clamp_cursor()
        self.cursor_offset = len(self.paragraphs[self.cursor_para])
        self._sync_active_format()

    def global_offset_from_cursor(self, para_idx: int = None, char_offset: int = None) -> int:
        if para_idx is None:
            para_idx = self.cursor_para
        if char_offset is None:
            char_offset = self.cursor_offset
        total = 0
        for idx in range(min(para_idx, len(self.paragraphs))):
            total += len(self.paragraphs[idx]) + 1
        return total + char_offset

    def cursor_from_global_offset(self, global_pos: int):
        rem = max(0, global_pos)
        for idx, p in enumerate(self.paragraphs):
            p_len = len(p)
            if rem <= p_len:
                return (idx, rem)
            rem -= (p_len + 1)
        last_idx = max(0, len(self.paragraphs) - 1)
        return (last_idx, len(self.paragraphs[last_idx]))

    # --- Serialization (Plain Text & Markdown) ---

    def to_plain_text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs)

    def from_plain_text(self, text: str) -> None:
        self.clear()
        lines = (text or "").replace("\r\n", "\n").split("\n")
        self.paragraphs = []
        for line in lines:
            style = "normal"
            if re.match(r"^(chapter\s+\w+|prologue\b|epilogue\b)", line.strip(), re.IGNORECASE):
                style = "h1"
            p = Paragraph(style=style, align="left", spans=[TextSpan(line)] if line else [])
            self.paragraphs.append(p)
        if not self.paragraphs:
            self.paragraphs = [Paragraph("normal", "left")]
        self.dirty = False

    def to_markdown(self) -> str:
        out_lines = []
        for idx, p in enumerate(self.paragraphs):
            if p.page_break_before and idx > 0:
                out_lines.append("\\pagebreak")

            prefix = ""
            if p.style == "title":
                prefix = "# "
            elif p.style == "h1":
                prefix = "## "
            elif p.style == "h2":
                prefix = "### "
            elif p.style == "h3":
                prefix = "#### "
            elif p.style == "quote":
                prefix = "> "

            align_tag = ""
            if p.align == "center" and p.style != "title":
                align_tag = "{:center} "
            elif p.align == "right":
                align_tag = "{:right} "

            inline_parts = []
            for s in p.spans:
                t = s.text
                if not t:
                    continue
                if s.underline:
                    t = f"__{t}__"
                if s.bold and s.italic:
                    t = f"**_{t}_**"
                elif s.bold:
                    t = f"**{t}**"
                elif s.italic:
                    t = f"*{t}*"
                inline_parts.append(t)

            out_lines.append(f"{prefix}{align_tag}{''.join(inline_parts)}")
        return "\n".join(out_lines)

    def from_markdown(self, md_text: str) -> None:
        self.clear()
        raw_lines = (md_text or "").replace("\r\n", "\n").split("\n")
        paras = []
        pending_page_break = False

        for line in raw_lines:
            stripped = line.strip()
            if stripped in ("\\pagebreak", "<!-- pagebreak -->", "\x0c"):
                pending_page_break = True
                continue

            style = "normal"
            align = "left"
            content = line

            if content.startswith("# "):
                style = "title"
                align = "center"
                content = content[2:]
            elif content.startswith("## "):
                style = "h1"
                content = content[3:]
            elif content.startswith("### "):
                style = "h2"
                content = content[4:]
            elif content.startswith("#### "):
                style = "h3"
                content = content[5:]
            elif content.startswith("> "):
                style = "quote"
                content = content[2:]

            if content.startswith("{:center} "):
                align = "center"
                content = content[10:]
            elif content.startswith("{:right} "):
                align = "right"
                content = content[9:]

            spans = self._parse_inline_markdown(content)
            paras.append(Paragraph(style=style, align=align, spans=spans, page_break_before=pending_page_break))
            pending_page_break = False

        self.paragraphs = paras if paras else [Paragraph("normal", "left")]
        self.dirty = False

    @staticmethod
    def _parse_inline_markdown(text: str) -> list:
        """Parses **_bold-italic_**, ***bold-italic***, **bold**, __underline__, and *italic* into TextSpans."""
        if not text:
            return []
        token_re = re.compile(r"(\*\*_[^_]+_\*\*|\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*)")
        spans = []
        pos = 0
        for m in token_re.finditer(text):
            if m.start() > pos:
                spans.append(TextSpan(text[pos:m.start()]))
            tok = m.group(0)
            if (tok.startswith("**_") and tok.endswith("_**")) or (tok.startswith("***") and tok.endswith("***")):
                spans.append(TextSpan(tok[3:-3], bold=True, italic=True))
            elif tok.startswith("**") and tok.endswith("**"):
                spans.append(TextSpan(tok[2:-2], bold=True))
            elif tok.startswith("__") and tok.endswith("__"):
                spans.append(TextSpan(tok[2:-2], underline=True))
            elif tok.startswith("*") and tok.endswith("*"):
                spans.append(TextSpan(tok[1:-1], italic=True))
            pos = m.end()
        if pos < len(text):
            spans.append(TextSpan(text[pos:]))
        return spans
