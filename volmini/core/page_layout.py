"""Print-accurate pagination and line-wrapping engine for Volmini.

Slices a RichDocument into physical PageSheets matching the selected
PageLayoutModel (PaperSizePreset, Orientation, PageMargins) and HeaderFooterModel.
"""

from volmini.core.document_model import PageLayoutModel
from volmini.core.header_footer import HeaderFooterModel
from volmini.core.rich_doc import RichDocument, Paragraph, TextSpan


class LayoutLine:
    """Single wrapped visual line on a physical printed page."""

    def __init__(
        self,
        para_idx: int,
        char_start: int,
        char_end: int,
        spans: list,
        style: str = "normal",
        align: str = "left",
        line_cost: int = 1,
        is_first_of_para: bool = False,
    ):
        self.para_idx = para_idx
        self.char_start = char_start
        self.char_end = char_end
        self.spans = spans
        self.style = style
        self.align = align
        self.line_cost = line_cost  # Vertical line units consumed on the physical sheet
        self.is_first_of_para = is_first_of_para

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    def __len__(self) -> int:
        return self.char_end - self.char_start


class PageSheet:
    """Single discrete physical paper sheet with running header, body lines, and running footer."""

    def __init__(self, page_number: int):
        self.page_number = page_number
        self.header_left = ""
        self.header_center = ""
        self.header_right = ""
        self.footer_left = ""
        self.footer_center = ""
        self.footer_right = ""
        self.header_suppressed = False
        self.lines = []
        self.used_line_units = 0


class PrintPaginationEngine:
    """Computes print-accurate wrapped lines and page breaks across physical sheets."""

    @classmethod
    def paginate(
        cls,
        doc: RichDocument,
        layout: PageLayoutModel,
        hf_model: HeaderFooterModel = None,
        story_title: str = "Untitled",
        story_author: str = "",
    ) -> list:
        max_cols = layout.printable_cols
        max_lines_per_page = layout.printable_lines_per_page

        all_wrapped_lines = []
        for p_idx, para in enumerate(doc.paragraphs):
            p_lines = cls._wrap_paragraph(p_idx, para, max_cols)
            if para.page_break_before and p_lines:
                p_lines[0]._force_page_break = True
            all_wrapped_lines.extend(p_lines)

        if not all_wrapped_lines:
            all_wrapped_lines.append(LayoutLine(0, 0, 0, [], "normal", "left", 1, True))

        # Slice wrapped lines into discrete physical pages
        pages = [PageSheet(1)]
        curr_page = pages[0]

        for ln in all_wrapped_lines:
            force_break = getattr(ln, "_force_page_break", False)
            if force_break and curr_page.lines:
                curr_page = PageSheet(len(pages) + 1)
                pages.append(curr_page)
            elif curr_page.used_line_units + ln.line_cost > max_lines_per_page and curr_page.lines:
                curr_page = PageSheet(len(pages) + 1)
                pages.append(curr_page)

            curr_page.lines.append(ln)
            curr_page.used_line_units += ln.line_cost

        # Populate running headers and footers for each page
        total_pages = len(pages)
        if hf_model is None:
            hf_model = HeaderFooterModel()

        for page in pages:
            cfg = hf_model.get_config_for_page(page.page_number)
            page.header_suppressed = cfg.suppressed
            if not cfg.suppressed:
                page.header_left = HeaderFooterModel.expand_tokens(
                    cfg.header_left, page.page_number, total_pages, story_title, story_author
                )
                page.header_center = HeaderFooterModel.expand_tokens(
                    cfg.header_center, page.page_number, total_pages, story_title, story_author
                )
                page.header_right = HeaderFooterModel.expand_tokens(
                    cfg.header_right, page.page_number, total_pages, story_title, story_author
                )
                page.footer_left = HeaderFooterModel.expand_tokens(
                    cfg.footer_left, page.page_number, total_pages, story_title, story_author
                )
                page.footer_center = HeaderFooterModel.expand_tokens(
                    cfg.footer_center, page.page_number, total_pages, story_title, story_author
                )
                page.footer_right = HeaderFooterModel.expand_tokens(
                    cfg.footer_right, page.page_number, total_pages, story_title, story_author
                )

        return pages

    @classmethod
    def _wrap_paragraph(cls, para_idx: int, para: Paragraph, max_cols: int) -> list:
        """Word-wraps a single paragraph according to its style and column width."""
        eff_cols = max_cols
        line_cost = 1
        if para.style == "title":
            eff_cols = max(16, int(max_cols * 0.75))
            line_cost = 2
        elif para.style == "h1":
            eff_cols = max(18, int(max_cols * 0.85))
            line_cost = 2
        elif para.style in ("h2", "h3"):
            eff_cols = max(20, int(max_cols * 0.92))
            line_cost = 1
        elif para.style == "quote":
            eff_cols = max(16, max_cols - 6)

        text = para.text
        if not text:
            return [LayoutLine(para_idx, 0, 0, [], para.style, para.align, line_cost, True)]

        lines = []
        n = len(text)
        pos = 0
        first = True

        while pos < n:
            if pos + eff_cols >= n:
                end = n
            else:
                # Find last space within eff_cols
                window = text[pos:pos + eff_cols + 1]
                space_idx = window.rfind(" ")
                if space_idx > 0:
                    end = pos + space_idx + 1
                else:
                    end = pos + eff_cols

            spans = para.slice_spans(pos, end)
            # Trim trailing space on wrapped lines (unless at very end of paragraph)
            if end < n and spans and spans[-1].text.endswith(" "):
                spans[-1].text = spans[-1].text[:-1]
                if not spans[-1].text:
                    spans.pop()

            lines.append(
                LayoutLine(
                    para_idx=para_idx,
                    char_start=pos,
                    char_end=end,
                    spans=spans,
                    style=para.style,
                    align=para.align,
                    line_cost=line_cost,
                    is_first_of_para=first,
                )
            )
            first = False
            pos = end

        return lines

    @staticmethod
    def find_cursor_location(pages: list, cursor_para: int, cursor_offset: int):
        """Returns (page_idx, line_idx_in_page, col_in_line) for the document cursor."""
        for p_idx, page in enumerate(pages):
            for l_idx, ln in enumerate(page.lines):
                if ln.para_idx == cursor_para:
                    # Check if cursor falls on this wrapped line
                    is_last_line_of_para = True
                    if l_idx + 1 < len(page.lines) and page.lines[l_idx + 1].para_idx == cursor_para:
                        is_last_line_of_para = False
                    elif p_idx + 1 < len(pages) and pages[p_idx + 1].lines and pages[p_idx + 1].lines[0].para_idx == cursor_para:
                        is_last_line_of_para = False

                    if ln.char_start <= cursor_offset < ln.char_end or (
                        is_last_line_of_para and cursor_offset == ln.char_end
                    ):
                        col = max(0, cursor_offset - ln.char_start)
                        return (p_idx, l_idx, col)
        return (0, 0, 0)
