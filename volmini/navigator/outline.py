"""Chapter & Section Outline Navigator for Volmini.

Scans RichDocument paragraphs for headings (Title, H1-H3, 'Chapter ...', 'Prologue', 'Epilogue'),
computes word count per chapter, preserves status ('Draft', 'In Progress', 'Needs Revision', 'Completed'),
supports reordering entire chapters in the manuscript, and jumps cursor to any chapter.
"""

import re
from volmini.core.rich_doc import RichDocument, Paragraph, TextSpan


class ChapterItem:
    """Single chapter or section entry in the Outline Navigator."""

    STATUSES = ["Draft", "In Progress", "Needs Revision", "Completed"]

    def __init__(
        self,
        title: str,
        para_index: int,
        end_para_index: int,
        heading_level: int = 1,
        word_count: int = 0,
        status: str = "Draft",
    ):
        self.title = title or "Untitled Chapter"
        self.para_index = para_index
        self.end_para_index = end_para_index
        self.heading_level = heading_level
        self.word_count = word_count
        self.status = status if status in self.STATUSES else "Draft"

    def cycle_status(self) -> str:
        idx = self.STATUSES.index(self.status)
        self.status = self.STATUSES[(idx + 1) % len(self.STATUSES)]
        return self.status


class OutlineNavigator:
    """Discovers and manages chapter structure across the manuscript."""

    HEADING_PREFIX_RE = re.compile(
        r"^(chapter\s+\w+|part\s+\w+|section\s+\w+|prologue\b|epilogue\b|introduction\b|conclusion\b)",
        re.IGNORECASE,
    )

    def __init__(self):
        self.items = []
        self.status_map = {}  # title_lower -> status

    def load_statuses(self, status_dict: dict) -> None:
        if status_dict:
            for k, v in status_dict.items():
                self.status_map[str(k).lower()] = str(v)

    def export_statuses(self) -> dict:
        for item in self.items:
            self.status_map[item.title.lower()] = item.status
        return dict(self.status_map)

    def scan(self, doc: RichDocument) -> list:
        """Scans document paragraphs to build the ordered list of ChapterItems."""
        for item in self.items:
            self.status_map[item.title.lower()] = item.status

        discovered = []
        current_item = None
        current_words = 0

        for idx, para in enumerate(doc.paragraphs):
            txt = para.text.strip()
            is_heading = False
            lvl = 1

            if para.style in ("title", "h1"):
                is_heading = True
                lvl = 1
            elif para.style == "h2":
                is_heading = True
                lvl = 2
            elif para.style == "h3":
                is_heading = True
                lvl = 3
            elif txt and self.HEADING_PREFIX_RE.match(txt) and len(txt) < 80:
                is_heading = True
                lvl = 1

            if is_heading and txt:
                if current_item is not None:
                    current_item.word_count = current_words
                    current_item.end_para_index = idx - 1
                    discovered.append(current_item)
                saved_status = self.status_map.get(txt.lower(), "Draft")
                current_item = ChapterItem(
                    title=txt,
                    para_index=idx,
                    end_para_index=idx,
                    heading_level=lvl,
                    word_count=0,
                    status=saved_status,
                )
                current_words = 0
            else:
                w = len(txt.split()) if txt else 0
                current_words += w

        if current_item is not None:
            current_item.word_count = current_words
            current_item.end_para_index = len(doc.paragraphs) - 1
            discovered.append(current_item)

        self.items = discovered
        return self.items

    def insert_new_chapter(self, doc: RichDocument, title: str = None) -> int:
        """Appends or inserts a new chapter heading with a page break."""
        self.scan(doc)
        next_num = len(self.items) + 1
        ch_title = title or f"Chapter {next_num}"
        doc._push_undo()

        # If document is just one empty paragraph, convert it directly
        if len(doc.paragraphs) == 1 and not doc.paragraphs[0].text.strip():
            doc.paragraphs[0].style = "h1"
            doc.paragraphs[0].spans = [TextSpan(ch_title)]
            doc.paragraphs.append(Paragraph("normal", "left"))
            doc.cursor_para = 1
            doc.cursor_offset = 0
            doc.dirty = True
            self.scan(doc)
            return 0

        heading_p = Paragraph("h1", "left", [TextSpan(ch_title)], page_break_before=True)
        body_p = Paragraph("normal", "left", [])
        doc.paragraphs.append(heading_p)
        doc.paragraphs.append(body_p)
        doc.cursor_para = len(doc.paragraphs) - 1
        doc.cursor_offset = 0
        doc.dirty = True
        self.scan(doc)
        return len(self.items) - 1

    def reorder_chapter(self, doc: RichDocument, from_idx: int, direction: int) -> bool:
        """Moves chapter at `from_idx` up (-1) or down (+1) in the manuscript."""
        self.scan(doc)
        to_idx = from_idx + direction
        if not (0 <= from_idx < len(self.items) and 0 <= to_idx < len(self.items)):
            return False

        doc._push_undo()
        a_idx = min(from_idx, to_idx)
        b_idx = max(from_idx, to_idx)
        ch_a = self.items[a_idx]
        ch_b = self.items[b_idx]

        # Slice paragraphs: [before_a] + [ch_b_slice] + [between_if_any] + [ch_a_slice] + [after_b]
        before = doc.paragraphs[:ch_a.para_index]
        slice_a = doc.paragraphs[ch_a.para_index:ch_a.end_para_index + 1]
        middle = doc.paragraphs[ch_a.end_para_index + 1:ch_b.para_index]
        slice_b = doc.paragraphs[ch_b.para_index:ch_b.end_para_index + 1]
        after = doc.paragraphs[ch_b.end_para_index + 1:]

        # Preserve page_break_before on non-first chapters
        if a_idx == 0 and slice_b:
            slice_b[0].page_break_before = False
            if slice_a:
                slice_a[0].page_break_before = True

        doc.paragraphs = before + slice_b + middle + slice_a + after
        doc.dirty = True
        self.scan(doc)

        target_ch = self.items[to_idx]
        doc.cursor_para = target_ch.para_index
        doc.cursor_offset = 0
        return True
