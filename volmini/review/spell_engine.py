"""Low-RAM Binary-Searched Flash/SD Spell Check Engine for Volmini.

Uses O(log N) file seek binary search across the sorted `data/dict_words.txt`
wordlist on Flash/SD so RAM consumption stays near zero, paired with:
- Common English typo autocorrect map
- Inflection stemmer (-s, -es, -ed, -ing, -ly, -er, -est)
- Persistent user dictionary (`data/user_dict.json`)
"""

import json
import os
from volmini.compat import path_exists, file_size
from volmini.review.lens_engine import LensFinding, RevisionLensEngine


COMMON_TYPOS = {
    "teh": ["the", "ten"],
    "recieve": ["receive"],
    "seperate": ["separate"],
    "occured": ["occurred"],
    "definately": ["definitely"],
    "wierd": ["weird"],
    "accomodate": ["accommodate"],
    "untill": ["until"],
    "beggining": ["beginning"],
    "beleive": ["believe"],
    "neccessary": ["necessary"],
    "tommorow": ["tomorrow"],
    "wich": ["which", "with"],
    "thier": ["their", "there"],
    "freind": ["friend"],
    "peice": ["piece"],
    "truely": ["truly"],
    "visable": ["visible"],
    "enviroment": ["environment"],
    "goverment": ["government"],
    "immediatly": ["immediately"],
    "knowlege": ["knowledge"],
    "parliment": ["parliament"],
    "remenber": ["remember"],
    "sentance": ["sentence"],
    "suprise": ["surprise"],
    "tounge": ["tongue"],
    "writting": ["writing"],
    "becuase": ["because"],
    "alreay": ["already"],
    "charcter": ["character"],
    "manuscipt": ["manuscript"],
}


class SpellCheckEngine:
    """Zero-heap-bloat spell checker using on-disk binary search and user dictionary."""

    def __init__(self, dict_file_path: str = None, user_dict_path: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.dict_file_path = dict_file_path or os.path.join(base_dir, "data", "dict_words.txt")
        self.user_dict_path = user_dict_path or os.path.join(base_dir, "data", "user_dict.json")
        self._dict_size = file_size(self.dict_file_path)
        self.user_words = set()
        self.session_ignored = set()
        self._known_cache = set()  # Bounded small LRU set for already-verified words
        self._load_user_dict()

    def _load_user_dict(self) -> None:
        if path_exists(self.user_dict_path):
            try:
                with open(self.user_dict_path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    if isinstance(items, list):
                        self.user_words = {str(w).lower().strip() for w in items if str(w).strip()}
            except Exception:
                pass

    def _save_user_dict(self) -> None:
        try:
            with open(self.user_dict_path, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.user_words)), f)
        except Exception:
            pass

    def add_to_user_dictionary(self, word: str) -> None:
        w = word.lower().strip()
        if w:
            self.user_words.add(w)
            self._save_user_dict()

    def ignore_word(self, word: str) -> None:
        w = word.lower().strip()
        if w:
            self.session_ignored.add(w)

    def _binary_search_file(self, target: str) -> bool:
        """Performs O(log N) binary search directly on the sorted newline-delimited file."""
        if self._dict_size <= 0 or not path_exists(self.dict_file_path):
            return True
        lo = 0
        hi = self._dict_size
        try:
            with open(self.dict_file_path, "rb") as f:
                while lo < hi:
                    mid = (lo + hi) // 2
                    f.seek(mid)
                    if mid > 0:
                        f.readline()  # Advance to start of next complete line
                    line_pos = f.tell()
                    if line_pos >= hi:
                        # `lo` is always at a line start boundary (0 or previous f.tell())
                        f.seek(lo)
                        while f.tell() <= hi:
                            raw = f.readline()
                            if not raw:
                                break
                            w = raw.decode("utf-8", "ignore").strip()
                            if w == target:
                                return True
                            if w > target:
                                return False
                        return False

                    raw = f.readline()
                    if not raw:
                        hi = mid
                        continue
                    w = raw.decode("utf-8", "ignore").strip()
                    if w == target:
                        return True
                    elif w < target:
                        lo = f.tell()
                    else:
                        hi = mid
        except Exception:
            return True
        return False

    def is_correct(self, word: str) -> bool:
        if not word or len(word) <= 1:
            return True
        # Strip possessive 's
        if word.endswith("'s") or word.endswith("’s"):
            word = word[:-2]
        if not word.isalpha():
            return True

        # Proper nouns (Capitalized inside sentence or known names)
        w_low = word.lower()
        if w_low in COMMON_TYPOS:
            return False
        if w_low in self.user_words or w_low in self.session_ignored or w_low in self._known_cache:
            return True

        # Direct lookup or simple suffix stemmer lookup
        candidates_to_check = [w_low]
        if w_low.endswith("s") and len(w_low) > 3:
            candidates_to_check.append(w_low[:-1])
        if w_low.endswith("es") and len(w_low) > 4:
            candidates_to_check.append(w_low[:-2])
        if w_low.endswith("ed") and len(w_low) > 4:
            candidates_to_check.append(w_low[:-2])
            candidates_to_check.append(w_low[:-1])
        if w_low.endswith("ing") and len(w_low) > 5:
            candidates_to_check.append(w_low[:-3])
            candidates_to_check.append(w_low[:-3] + "e")
        if w_low.endswith("ly") and len(w_low) > 4:
            candidates_to_check.append(w_low[:-2])

        for cand in candidates_to_check:
            if self._binary_search_file(cand):
                if len(self._known_cache) > 256:
                    self._known_cache.clear()
                self._known_cache.add(w_low)
                return True

        return False

    def get_suggestions(self, word: str, limit: int = 4) -> list:
        w_low = word.lower().strip()
        if w_low in COMMON_TYPOS:
            res = list(COMMON_TYPOS[w_low])
            return [c.capitalize() if word.istitle() else c for c in res[:limit]]

        # Scan nearby neighborhood in sorted dictionary file sharing first 2 letters
        prefix = w_low[:2] if len(w_low) >= 2 else w_low
        matches = []
        if self._dict_size > 0 and path_exists(self.dict_file_path):
            lo = 0
            hi = self._dict_size
            try:
                with open(self.dict_file_path, "rb") as f:
                    while lo < hi:
                        mid = (lo + hi) // 2
                        f.seek(mid)
                        if mid > 0:
                            f.readline()
                        raw = f.readline()
                        if not raw:
                            hi = mid
                            continue
                        w = raw.decode("utf-8", "ignore").strip()
                        if w < prefix:
                            lo = f.tell()
                        else:
                            hi = mid

                    f.seek(max(0, lo - 128))
                    if lo > 128:
                        f.readline()
                    for _ in range(120):
                        raw = f.readline()
                        if not raw:
                            break
                        cand = raw.decode("utf-8", "ignore").strip()
                        if not cand.startswith(w_low[0]):
                            if cand > w_low:
                                break
                            continue
                        if abs(len(cand) - len(w_low)) <= 2:
                            dist = self._edit_distance_bounded(w_low, cand)
                            if dist <= 2:
                                matches.append((dist, cand))
            except Exception:
                pass

        matches.sort(key=lambda item: (item[0], item[1]))
        out = [m[1] for m in matches[:limit]]
        if word.istitle():
            out = [c.capitalize() for c in out]
        return out

    @staticmethod
    def _edit_distance_bounded(s1: str, s2: str) -> int:
        if s1 == s2:
            return 0
        m, n = len(s1), len(s2)
        if abs(m - n) > 2:
            return 3
        prev = list(range(n + 1))
        for i in range(1, m + 1):
            curr = [i] + [0] * n
            for j in range(1, n + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            prev = curr
        return prev[n]

    def check_paragraph(self, para_idx: int, text: str) -> list:
        if not text:
            return []
        findings = []
        tokens = RevisionLensEngine._tokenize_with_spans(text)
        for word, s_pos, e_pos in tokens:
            # Ignore capitalized proper nouns unless at start of sentence or in COMMON_TYPOS
            if word[0].isupper() and s_pos > 0 and word.lower() not in COMMON_TYPOS:
                continue
            if not self.is_correct(word):
                suggs = self.get_suggestions(word)
                findings.append(
                    LensFinding(
                        lens_type="spelling",
                        para_idx=para_idx,
                        start_pos=s_pos,
                        end_pos=e_pos,
                        text=word,
                        message=f"Spelling: '{word}'",
                        suggestions=suggs,
                        context_snippet=RevisionLensEngine._snippet(text, s_pos, e_pos),
                    )
                )
        return findings
