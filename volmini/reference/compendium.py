"""Stripped-down, low-RAM Offline Writer's Reference Compendium for Volmini.

Design:
- Keeps only a compact index in memory (`[title, category_id, byte_offset, byte_length]`)
- Reads plain-text article bodies on demand from `data/ref_data.txt` using `seek()` + `read()`
- Zero cross-references, zero tags, zero rich text — as simple and small as possible.
"""

import json
import os
from volmini.compat import path_exists


class CompendiumEntryStub:
    """Tiny in-memory stub representing an indexed article."""

    __slots__ = ("index", "title", "category_id", "category", "offset", "length")

    def __init__(self, index: int, title: str, category_id: int, category: str, offset: int, length: int):
        self.index = index
        self.title = title
        self.category_id = category_id
        self.category = category
        self.offset = offset
        self.length = length


class StrippedCompendium:
    """Byte-offset lazy-loading reference lookup engine."""

    def __init__(self, index_path: str = None, data_path: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.index_path = index_path or os.path.join(base_dir, "data", "ref_index.json")
        self.data_path = data_path or os.path.join(base_dir, "data", "ref_data.txt")
        self.categories = []
        self.entries = []
        self._loaded = False

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self.reload()

    def reload(self) -> None:
        self.categories = []
        self.entries = []
        if not path_exists(self.index_path):
            self._loaded = True
            return
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self.categories = payload.get("categories", [])
            raw_list = payload.get("entries", [])
            for idx, item in enumerate(raw_list):
                title, cat_id, offset, length = item[0], item[1], item[2], item[3]
                cat_name = self.categories[cat_id] if 0 <= cat_id < len(self.categories) else "General"
                self.entries.append(CompendiumEntryStub(idx, title, cat_id, cat_name, offset, length))
        except Exception as e:
            print(f"Error loading reference index: {e}")
        self._loaded = True

    @property
    def total_count(self) -> int:
        self.ensure_loaded()
        return len(self.entries)

    def get_categories(self) -> list:
        self.ensure_loaded()
        return ["All Categories"] + list(self.categories)

    def search(self, query: str = "", category: str = None) -> list:
        """Filters entries by title/category keyword without loading article bodies into RAM."""
        self.ensure_loaded()
        q = (query or "").strip().lower()
        cat_filter = category if (category and category != "All Categories") else None

        results = []
        for stub in self.entries:
            if cat_filter and stub.category != cat_filter:
                continue
            if not q:
                results.append(stub)
            else:
                t_low = stub.title.lower()
                c_low = stub.category.lower()
                if q in t_low or q in c_low:
                    results.append(stub)
        return results

    def read_body(self, stub: CompendiumEntryStub) -> str:
        """Seeks directly to `stub.offset` in `ref_data.txt` and reads `stub.length` bytes."""
        if stub is None or not path_exists(self.data_path):
            return ""
        try:
            with open(self.data_path, "rb") as f:
                f.seek(stub.offset)
                raw = f.read(stub.length)
            return raw.decode("utf-8", "ignore").strip()
        except Exception as e:
            return f"Error reading entry: {e}"
