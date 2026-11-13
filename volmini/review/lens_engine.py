"""MicroPython-compatible Revision and Proofreading Lenses for Volmini.

Ported from volumenodex.review.lens_engine with zero Qt/PySide6 dependencies:
1. Adverbs Lens (flags weak -ly modifiers with active verb alternatives)
2. Passive Voice Lens (detects 'was/were + past participle' passive constructions)
3. Filler & Crutch Phrases (wordiness and throat-clearing locutions)
4. Pacing & Rhythm Analysis (sentence length tempo classification)
"""

import re


class LensFinding:
    """Single flagged issue or insight detected by an editorial lens or spell check."""

    def __init__(
        self,
        lens_type: str,
        para_idx: int,
        start_pos: int,
        end_pos: int,
        text: str,
        message: str,
        suggestions: list = None,
        context_snippet: str = "",
        pacing_tier: str = "",
    ):
        self.lens_type = lens_type        # "adverb", "passive", "filler", "pacing", "spelling"
        self.para_idx = para_idx
        self.start_pos = start_pos        # Character offset within paragraph
        self.end_pos = end_pos
        self.text = text
        self.message = message
        self.suggestions = suggestions or []
        self.context_snippet = context_snippet
        self.pacing_tier = pacing_tier


class RevisionLensEngine:
    """Lightweight manuscript analyzer producing non-destructive revision findings."""

    LY_FALSE_POSITIVES = {
        "family", "lovely", "friendly", "early", "silly", "lonely", "ugly", "daily",
        "orderly", "holy", "jelly", "belly", "ally", "rally", "bully", "apply",
        "supply", "reply", "comply", "rely", "fly", "multiply", "butterfly", "lily",
        "monopoly", "anomaly", "homily", "italy", "folly", "gully", "chilly", "dolly",
        "holly", "woolly", "oily", "wily", "steely", "grisly", "bubbly", "sickly",
        "prickly", "elderly", "scholarly", "kingly", "queenly", "heavenly", "ghostly",
        "beastly", "only", "likely",
    }

    SOFT_MODIFIERS = {
        "very", "really", "quite", "somewhat", "extremely", "absolutely", "totally",
        "fairly", "rather", "mostly", "barely", "scarcely", "virtually",
        "literally", "definitely", "completely", "truly",
    }

    ADVERB_REPLACEMENTS = {
        "quietly": ["whispered", "murmured", "tiptoed", "crept", "(remove)"],
        "quickly": ["bolted", "dashed", "sprinted", "hurried", "(remove)"],
        "loudly": ["bellowed", "thundered", "roared", "barked", "(remove)"],
        "slowly": ["inched", "drifted", "crawled", "lingered", "(remove)"],
        "softly": ["breathed", "murmured", "whispered", "(remove)"],
        "angrily": ["snapped", "fumed", "seethed", "glowered", "(remove)"],
        "happily": ["beamed", "grinned", "rejoiced", "(remove)"],
        "sadly": ["mourned", "grieved", "sighed", "(remove)"],
        "suddenly": ["erupted", "burst", "jolted", "(remove)"],
        "calmly": ["steadied", "composed", "(remove)"],
        "carefully": ["measured", "studied", "scrutinized", "(remove)"],
        "nervously": ["fidgeted", "trembled", "hesitated", "(remove)"],
        "eagerly": ["yearned", "hungered", "leaped", "(remove)"],
        "fiercely": ["clashed", "fought", "raged", "(remove)"],
        "gently": ["stroked", "cradled", "nudged", "(remove)"],
        "heavily": ["slumped", "collapsed", "sank", "(remove)"],
        "tightly": ["gripped", "clutched", "grasped", "(remove)"],
        "sharply": ["snapped", "pierced", "jabbed", "(remove)"],
        "coldly": ["sneered", "dismissed", "glared", "(remove)"],
        "silently": ["crept", "slipped", "watched", "(remove)"],
        "wearily": ["trudged", "slumped", "plodded", "(remove)"],
        "urgently": ["pleaded", "demanded", "pressed", "(remove)"],
        "cautiously": ["tiptoed", "hesitated", "probed", "(remove)"],
        "desperately": ["scrambled", "clawed", "begged", "(remove)"],
        "hastily": ["scribbled", "retreated", "(remove)"],
        "swiftly": ["darted", "struck", "intercepted", "(remove)"],
        "very": ["(remove)", "exceptionally", "profoundly"],
        "really": ["(remove)", "genuinely", "truly"],
        "quite": ["(remove)", "rather"],
        "actually": ["(remove)"],
        "basically": ["(remove)"],
        "simply": ["(remove)"],
    }

    FILLER_PHRASES = {
        "in order to": ["to"],
        "due to the fact that": ["because", "since"],
        "at the end of the day": ["ultimately", "(remove)"],
        "all of a sudden": ["suddenly", "(remove)"],
        "needless to say": ["(remove)"],
        "for the purpose of": ["to", "for"],
        "in the process of": ["(remove)"],
        "a number of": ["several", "many"],
        "as a matter of fact": ["in fact", "(remove)"],
        "it goes without saying": ["(remove)"],
        "at this point in time": ["now", "currently"],
        "by means of": ["by", "using"],
        "in light of the fact that": ["because"],
        "there is no doubt that": ["doubtless", "certainly"],
        "for all intents and purposes": ["effectively", "(remove)"],
        "in spite of the fact that": ["although", "even though"],
        "has the ability to": ["can"],
        "is able to": ["can"],
        "take into consideration": ["consider"],
        "came to the conclusion": ["concluded", "decided"],
    }

    PASSIVE_AUX = {"is", "are", "was", "were", "been", "being", "be"}
    IRREGULAR_PARTICIPLES = {
        "transcribed": ["transcribed", "copied"],
        "confiscated": ["confiscated", "seized"],
        "written": ["wrote", "drafted", "penned"],
        "seen": ["saw", "spotted", "observed"],
        "taken": ["took", "seized", "captured"],
        "given": ["gave", "granted"],
        "done": ["did", "executed"],
        "known": ["knew", "recognized"],
        "found": ["found", "discovered"],
        "chosen": ["chose", "selected"],
        "spoken": ["spoke", "uttered"],
        "broken": ["broke", "shattered"],
        "felt": ["felt", "sensed"],
        "heard": ["heard", "caught"],
        "drawn": ["drew", "sketched"],
        "built": ["built", "constructed"],
        "held": ["held", "gripped"],
        "kept": ["kept", "preserved"],
        "made": ["made", "crafted"],
        "sent": ["sent", "dispatched"],
        "told": ["told", "informed"],
        "left": ["left", "abandoned"],
        "hidden": ["hid", "concealed"],
        "forgotten": ["forgot", "overlooked"],
        "stolen": ["stole", "pilfered"],
        "frozen": ["froze", "halted"],
    }

    WORD_RE = re.compile(r"[A-Za-z']+")

    @classmethod
    def _tokenize_with_spans(cls, text: str) -> list:
        """Tokenizes text into (word, start_idx, end_idx) without requiring re.finditer."""
        tokens = []
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch.isalpha():
                start = i
                i += 1
                while i < n and (text[i].isalpha() or text[i] == "'"):
                    i += 1
                tokens.append((text[start:i], start, i))
            else:
                i += 1
        return tokens

    @classmethod
    def analyze_paragraphs(cls, paragraphs: list, enabled_lenses: dict = None) -> list:
        if enabled_lenses is None:
            enabled_lenses = {
                "adverb": True,
                "passive": True,
                "filler": True,
                "pacing": False,
            }

        findings = []
        for p_idx, para in enumerate(paragraphs):
            txt = para.text if hasattr(para, "text") else str(para)
            if not txt:
                continue
            findings.extend(cls.analyze_paragraph(p_idx, txt, enabled_lenses))
        return findings

    @classmethod
    def analyze_paragraph(cls, para_idx: int, text: str, enabled_lenses: dict = None) -> list:
        if not text:
            return []
        if enabled_lenses is None:
            enabled_lenses = {"adverb": True, "passive": True, "filler": True, "pacing": False}

        findings = []
        tokens = cls._tokenize_with_spans(text)

        # 1. Adverbs & Soft Modifiers
        if enabled_lenses.get("adverb", True):
            for word, s_pos, e_pos in tokens:
                w_low = word.lower()
                is_adv = (w_low.endswith("ly") and len(w_low) > 3 and w_low not in cls.LY_FALSE_POSITIVES) or (
                    w_low in cls.SOFT_MODIFIERS
                )
                if is_adv:
                    suggs = cls.ADVERB_REPLACEMENTS.get(w_low, ["(remove)", "surged", "darted", "pressed"])
                    findings.append(
                        LensFinding(
                            lens_type="adverb",
                            para_idx=para_idx,
                            start_pos=s_pos,
                            end_pos=e_pos,
                            text=word,
                            message=f"Weak modifier '{word}'. Prefer strong verbs.",
                            suggestions=list(suggs),
                            context_snippet=cls._snippet(text, s_pos, e_pos),
                        )
                    )

        # 2. Passive Voice (aux + participle)
        if enabled_lenses.get("passive", True):
            for idx in range(len(tokens) - 1):
                w1, s1, _ = tokens[idx]
                w2, _, e2 = tokens[idx + 1]
                # Ensure tokens are adjacent separated only by whitespace
                between = text[tokens[idx][2]:tokens[idx + 1][1]]
                if between.strip() != "":
                    continue
                w1_low = w1.lower()
                w2_low = w2.lower()
                if w1_low in cls.PASSIVE_AUX and (
                    (w2_low.endswith("ed") and len(w2_low) > 3) or w2_low in cls.IRREGULAR_PARTICIPLES
                ):
                    phrase = text[s1:e2]
                    suggs = cls.IRREGULAR_PARTICIPLES.get(w2_low, [w2_low])
                    findings.append(
                        LensFinding(
                            lens_type="passive",
                            para_idx=para_idx,
                            start_pos=s1,
                            end_pos=e2,
                            text=phrase,
                            message=f"Passive voice '{phrase}'. Place the actor first.",
                            suggestions=list(suggs),
                            context_snippet=cls._snippet(text, s1, e2),
                        )
                    )

        # 3. Filler & Crutch Phrases
        if enabled_lenses.get("filler", True):
            t_low = text.lower()
            for phrase, suggs in cls.FILLER_PHRASES.items():
                search_from = 0
                p_len = len(phrase)
                while True:
                    idx = t_low.find(phrase, search_from)
                    if idx < 0:
                        break
                    end_idx = idx + p_len
                    # Check word boundaries
                    left_ok = idx == 0 or not t_low[idx - 1].isalpha()
                    right_ok = end_idx >= len(t_low) or not t_low[end_idx].isalpha()
                    if left_ok and right_ok:
                        matched = text[idx:end_idx]
                        findings.append(
                            LensFinding(
                                lens_type="filler",
                                para_idx=para_idx,
                                start_pos=idx,
                                end_pos=end_idx,
                                text=matched,
                                message=f"Wordy crutch '{matched}'. Tighten prose.",
                                suggestions=list(suggs),
                                context_snippet=cls._snippet(text, idx, end_idx),
                            )
                        )
                    search_from = end_idx

        # 4. Pacing & Cadence
        if enabled_lenses.get("pacing", False):
            # Split into sentences by . ! ?
            sent_start = 0
            for i, ch in enumerate(text):
                if ch in ".!?" or i == len(text) - 1:
                    s_end = i + 1
                    s_txt = text[sent_start:s_end].strip()
                    if s_txt:
                        w_count = len(s_txt.split())
                        if w_count <= 5:
                            tier = "staccato"
                            msg = f"Staccato tempo ({w_count}w). High-impact punchy beat."
                        elif w_count <= 14:
                            tier = "brisk"
                            msg = f"Brisk cadence ({w_count}w). Swift progression."
                        elif w_count <= 25:
                            tier = "moderate"
                            msg = f"Moderate flow ({w_count}w). Balanced tempo."
                        else:
                            tier = "lyrical"
                            msg = f"Long lyrical sentence ({w_count}w). Verify clarity."
                        if tier in ("staccato", "lyrical"):
                            findings.append(
                                LensFinding(
                                    lens_type="pacing",
                                    para_idx=para_idx,
                                    start_pos=sent_start,
                                    end_pos=s_end,
                                    text=s_txt[:32] + ("..." if len(s_txt) > 32 else ""),
                                    message=msg,
                                    suggestions=[],
                                    context_snippet=s_txt[:48],
                                    pacing_tier=tier,
                                )
                            )
                    sent_start = s_end

        findings.sort(key=lambda f: f.start_pos)
        return findings

    @classmethod
    def analyze_document(cls, text: str, enabled_lenses: dict = None) -> list:
        lines = (text or "").split("\n")
        findings = []
        for idx, ln in enumerate(lines):
            findings.extend(cls.analyze_paragraph(idx, ln, enabled_lenses))
        return findings

    @staticmethod
    def _snippet(text: str, start: int, end: int, window: int = 20) -> str:
        s = max(0, start - window)
        e = min(len(text), end + window)
        pre = ".." if s > 0 else ""
        suf = ".." if e < len(text) else ""
        return f"{pre}{text[s:start]}[{text[start:end]}]{text[end:e]}{suf}"
