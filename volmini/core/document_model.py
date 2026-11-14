"""Document model and physical print page geometry specifications for Volmini.

Stripped-down MicroPython port of volumenodex.core.document_model supporting
Creative Fiction and General Non-Fiction modes plus print-accurate page geometry.
"""


class PaperSizePreset:
    LETTER = "US Letter (8.5 x 11 in)"
    A4 = "A4 (210 x 297 mm)"
    LEGAL = "US Legal (8.5 x 14 in)"
    EXECUTIVE = "Executive (7.25 x 10.5 in)"
    BOOK_6X9 = "Trade Paperback (6 x 9 in)"

    ALL = [LETTER, A4, LEGAL, EXECUTIVE, BOOK_6X9]


class Orientation:
    PORTRAIT = "Portrait"
    LANDSCAPE = "Landscape"


class DocumentMode:
    CREATIVE_FICTION = "creative_fiction"
    NON_FICTION = "non_fiction"

    ALL = [CREATIVE_FICTION, NON_FICTION]


DOCUMENT_MODE_TITLES = {
    DocumentMode.CREATIVE_FICTION: "Creative Fiction & Narrative",
    DocumentMode.NON_FICTION: "General Non-Fiction & Essays",
}

PAPER_DIMENSIONS_INCHES = {
    PaperSizePreset.LETTER: (8.5, 11.0),
    PaperSizePreset.A4: (8.267, 11.692),
    PaperSizePreset.LEGAL: (8.5, 14.0),
    PaperSizePreset.EXECUTIVE: (7.25, 10.5),
    PaperSizePreset.BOOK_6X9: (6.0, 9.0),
}

# Standard character grid density for print-accurate layout calculation
CHARS_PER_INCH_H = 12.0   # Standard 12-CPI Pica book/manuscript horizontal pitch
LINES_PER_INCH_V = 5.5    # ~5.5 book-spaced lines per vertical inch


class PageMargins:
    """Physical page margins in inches."""

    def __init__(self, top: float = 1.0, bottom: float = 1.0, left: float = 1.0, right: float = 1.0, preset_name: str = "Normal"):
        self.top = float(top)
        self.bottom = float(bottom)
        self.left = float(left)
        self.right = float(right)
        self.preset_name = preset_name

    @classmethod
    def normal(cls) -> "PageMargins":
        return cls(1.0, 1.0, 1.0, 1.0, "Normal (1.0 in)")

    @classmethod
    def narrow(cls) -> "PageMargins":
        return cls(0.5, 0.5, 0.5, 0.5, "Narrow (0.5 in)")

    @classmethod
    def wide(cls) -> "PageMargins":
        return cls(1.0, 1.0, 1.5, 1.5, "Wide (1.5 in L/R)")

    @classmethod
    def manuscript(cls) -> "PageMargins":
        return cls(1.0, 1.0, 1.25, 1.25, "Manuscript (1.25 in)")

    def to_dict(self) -> dict:
        return {
            "top": self.top,
            "bottom": self.bottom,
            "left": self.left,
            "right": self.right,
            "preset_name": self.preset_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PageMargins":
        if not data:
            return cls.normal()
        return cls(
            top=data.get("top", 1.0),
            bottom=data.get("bottom", 1.0),
            left=data.get("left", 1.0),
            right=data.get("right", 1.0),
            preset_name=data.get("preset_name", "Custom"),
        )


class PageLayoutModel:
    """Computes print coordinates, character columns, and lines per physical page."""

    def __init__(
        self,
        paper_size: str = PaperSizePreset.LETTER,
        orientation: str = Orientation.PORTRAIT,
        margins: PageMargins = None,
        viewport_scale_cols: int = 80,
        content_width_px: int = 316,
    ):
        self.paper_size = paper_size if paper_size in PAPER_DIMENSIONS_INCHES else PaperSizePreset.LETTER
        self.orientation = orientation
        self.margins = margins or PageMargins.normal()
        self.viewport_scale_cols = int(viewport_scale_cols)
        self.content_width_px = int(content_width_px)

    @property
    def raw_dimensions_inches(self):
        w, h = PAPER_DIMENSIONS_INCHES[self.paper_size]
        if self.orientation == Orientation.LANDSCAPE:
            return (h, w)
        return (w, h)

    @property
    def printable_width_inches(self) -> float:
        w, _ = self.raw_dimensions_inches
        return max(2.0, w - self.margins.left - self.margins.right)

    @property
    def printable_height_inches(self) -> float:
        _, h = self.raw_dimensions_inches
        return max(2.0, h - self.margins.top - self.margins.bottom)

    @property
    def printable_cols(self) -> int:
        """Exact character columns across a physical line for the selected paper, margins, and display."""
        raw_cols = max(20, int(round(self.printable_width_inches * CHARS_PER_INCH_H)))
        px_cols = max(20, (self.content_width_px - 6) // 6)
        return min(raw_cols, max(20, self.viewport_scale_cols), px_cols)

    @property
    def printable_lines_per_page(self) -> int:
        """Exact body lines per physical page for the selected paper and margins."""
        return max(10, int(round(self.printable_height_inches * LINES_PER_INCH_V)))

    def to_dict(self) -> dict:
        return {
            "paper_size": self.paper_size,
            "orientation": self.orientation,
            "margins": self.margins.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PageLayoutModel":
        if not data:
            return cls()
        return cls(
            paper_size=data.get("paper_size", PaperSizePreset.LETTER),
            orientation=data.get("orientation", Orientation.PORTRAIT),
            margins=PageMargins.from_dict(data.get("margins")),
        )


class DocumentStatistics:
    """Word, character, paragraph, page, and reading-time metrics."""

    def __init__(
        self,
        word_count: int = 0,
        char_count: int = 0,
        char_no_spaces: int = 0,
        paragraph_count: int = 0,
        page_count: int = 1,
        reading_time_minutes: float = 0.0,
    ):
        self.word_count = word_count
        self.char_count = char_count
        self.char_no_spaces = char_no_spaces
        self.paragraph_count = paragraph_count
        self.page_count = max(1, page_count)
        self.reading_time_minutes = reading_time_minutes

    @classmethod
    def compute(cls, text: str, page_count: int = 1) -> "DocumentStatistics":
        if not text:
            return cls(page_count=max(1, page_count))
        words = text.split()
        word_count = len(words)
        char_count = len(text)
        char_no_spaces = 0
        for ch in text:
            if ch not in (" ", "\n", "\r", "\t"):
                char_no_spaces += 1
        paragraphs = [p for p in text.split("\n") if p.strip()]
        paragraph_count = len(paragraphs)
        reading_time = round(word_count / 225.0, 1)
        return cls(
            word_count=word_count,
            char_count=char_count,
            char_no_spaces=char_no_spaces,
            paragraph_count=paragraph_count,
            page_count=max(1, page_count),
            reading_time_minutes=reading_time,
        )

    @property
    def words(self) -> int:
        return self.word_count
