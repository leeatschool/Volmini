"""Asset builder for Volmini (ESP32 MicroPython Edition).

Extracts and strips assets from the desktop Volumenodex repository:
1. Converts assets/icon.png ('V|' emblem) into a 1-bit packed byte array for the Boot Initiating Screen.
2. Strips volumenodex/reference/bundled_knowledge.json into a minimal plain-text data file
   (data/ref_data.txt) + compact byte-offset index (data/ref_index.json) with no cross-references
   and no rich text.
3. Builds a sorted, newline-delimited dictionary file (data/dict_words.txt) for O(log N)
   on-disk binary search spell checking with near-zero RAM usage.
"""

import json
import os
import re
import sys

VOLUMENODEX_ROOT = r"C:\Users\Aaron\Projects\Volumnodex\Volumenodex-main"
VOLMINI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def clean_plain_text(text: str) -> str:
    """Strips HTML tags, markdown markers, and extra whitespace for plain-text display."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&mdash;", "--").replace("&ndash;", "-").replace("&amp;", "&")
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2022", "*").replace("\u00a0", " ")
    # Collapse multiple blank lines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank and cleaned_lines:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False
    return "\n".join(cleaned_lines).strip()


def build_splash_logo() -> None:
    """Samples assets/icon.png into a 48x48 1-bit bitmap for the ESP32 boot splash."""
    icon_path = os.path.join(VOLUMENODEX_ROOT, "assets", "icon.png")
    out_path = os.path.join(VOLMINI_ROOT, "volmini", "ui", "splash_logo.py")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    width, height = 48, 48
    packed_bytes = bytearray((width * height) // 8)

    try:
        from PIL import Image
        img = Image.open(icon_path).convert("L").resize((width, height), Image.Resampling.BILINEAR)
        pixels = img.load()
        for y in range(height):
            for x in range(width):
                if pixels[x, y] > 100:
                    bit_idx = y * width + x
                    packed_bytes[bit_idx >> 3] |= (0x80 >> (bit_idx & 7))
    except Exception as exc:
        print(f"Warning: PIL icon conversion fallback ({exc})")

    hex_lines = []
    for i in range(0, len(packed_bytes), 12):
        chunk = packed_bytes[i:i + 12]
        hex_lines.append("    " + ", ".join(f"0x{b:02x}" for b in chunk) + ",")

    code = (
        '"""1-bit 48x48 bitmap of the Volumenodex V| emblem for the ESP32 Initiating Splash Screen."""\n\n'
        f"LOGO_WIDTH = {width}\n"
        f"LOGO_HEIGHT = {height}\n"
        "LOGO_BITMAP = bytes([\n"
        + "\n".join(hex_lines)
        + "\n])\n"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[OK] Built splash logo: {out_path} ({len(packed_bytes)} bytes)")


def build_stripped_compendium() -> None:
    """Strips bundled_knowledge.json into data/ref_data.txt + data/ref_index.json."""
    src_path = os.path.join(VOLUMENODEX_ROOT, "volumenodex", "reference", "bundled_knowledge.json")
    data_dir = os.path.join(VOLMINI_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)

    index_path = os.path.join(data_dir, "ref_index.json")
    data_path = os.path.join(data_dir, "ref_data.txt")

    with open(src_path, "r", encoding="utf-8") as f:
        raw_entries = json.load(f)

    # Sort entries alphabetically by title for clean browsing
    raw_entries.sort(key=lambda e: e.get("title", "").lower())

    # Build category table to store category as a single integer ID in index
    categories = []
    cat_to_id = {}
    for item in raw_entries:
        cat = clean_plain_text(item.get("category", "General"))
        if cat not in cat_to_id:
            cat_to_id[cat] = len(categories)
            categories.append(cat)

    index_items = []
    with open(data_path, "wb") as df:
        for item in raw_entries:
            title = clean_plain_text(item.get("title", "Untitled"))
            cat = clean_plain_text(item.get("category", "General"))
            cat_id = cat_to_id[cat]
            summary = clean_plain_text(item.get("summary", ""))
            content = clean_plain_text(item.get("content", ""))

            # Format compact plain-text body (no cross-references, no tags, no rich text)
            parts = []
            if summary:
                parts.append(summary)
            quick_facts = item.get("quick_facts") or {}
            if quick_facts:
                qf_lines = [f"- {clean_plain_text(str(k))}: {clean_plain_text(str(v))}" for k, v in quick_facts.items()]
                parts.append("\n".join(qf_lines))
            if content:
                parts.append(content)

            body_text = "\n\n".join(parts).strip() + "\n"
            body_bytes = body_text.encode("utf-8")

            offset = df.tell()
            df.write(body_bytes)
            length = len(body_bytes)

            # Compact tuple: [title, category_id, byte_offset, byte_length]
            index_items.append([title, cat_id, offset, length])

    index_payload = {
        "categories": categories,
        "entries": index_items,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_payload, f, separators=(",", ":"))

    print(
        f"[OK] Built stripped compendium: {len(index_items)} entries across {len(categories)} categories "
        f"(index: {os.path.getsize(index_path):,} bytes, data: {os.path.getsize(data_path):,} bytes)"
    )


def build_compact_dictionary() -> None:
    """Builds a sorted lowercase word list for O(log N) binary search on Flash/SD."""
    data_dir = os.path.join(VOLMINI_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    dict_path = os.path.join(data_dir, "dict_words.txt")
    user_dict_path = os.path.join(data_dir, "user_dict.json")

    words = set()
    try:
        from spellchecker import SpellChecker
        sp = SpellChecker(language="en")
        # Extract top ~15,000 most frequent English words to keep Flash footprint small (~120KB)
        freq_dict = sp.word_frequency.dictionary
        sorted_by_freq = sorted(freq_dict.items(), key=lambda kv: kv[1], reverse=True)
        for w, _ in sorted_by_freq[:15000]:
            w_clean = w.strip().lower()
            if w_clean.isalpha() and len(w_clean) > 1:
                words.add(w_clean)
    except Exception as exc:
        print(f"Notice: spellchecker package fallback ({exc})")

    # Ensure core literary & common vocabulary is present
    baseline_words = [
        "about", "above", "across", "action", "actually", "after", "again", "against", "almost",
        "alone", "along", "already", "also", "although", "always", "among", "ancient", "another",
        "answer", "anything", "appear", "approach", "archive", "around", "arrive", "article",
        "author", "autumn", "before", "began", "begin", "behind", "believe", "below", "Beneath",
        "beside", "between", "beyond", "black", "blood", "board", "Brass", "breath", "breathe",
        "bridge", "bright", "bring", "brother", "brought", "build", "building", "captain",
        "carefully", "carried", "carry", "castle", "catch", "cathedral", "cause", "center",
        "century", "certain", "chamber", "change", "chapter", "character", "chart", "child",
        "children", "church", "circle", "city", "clear", "clearly", "close", "closed", "cloud",
        "coast", "codex", "coffee", "cold", "color", "column", "come", "common", "companion",
        "compass", "complete", "consider", "continue", "corkboard", "corner", "corvus", "could",
        "council", "country", "Indexing", "course", "court", "cover", "create", "creative",
        "across", "crowd", "crown", "crystal", "current", "cursor", "custom", "dagger", "danger",
        "dark", "darkness", "daughter", "death", "decide", "deep", "describe", "desert", "design",
        "desire", "desk", "detail", "device", "dialogue", "dictionary", "different", "direction",
        "discover", "distance", "distant", "doctor", "document", "door", "double", "doubt",
        "draft", "dragon", "dream", "dress", "drink", "drive", "during", "early", "earth",
        "easily", "east", "editor", "effect", "effort", "either", "eleven", "empire", "empty",
        "enemy", "energy", "engine", "enough", "enter", "entire", "entry", "epilogue", "escape",
        "especially", "essay", "evening", "event", "every", "everyone", "everything", "evidence",
        "exact", "example", "except", "expect", "experience", "explain", "export", "express",
        "faction", "family", "father", "feather", "feeling", "fiction", "field", "fifteen",
        "fight", "figure", "final", "finally", "finger", "finish", "first", "flame", "flash",
        "flight", "floor", "flower", "follow", "Footsteps", "force", "forest", "forever",
        "forget", "form", "format", "fortress", "forward", "found", "fourteen", "frame", "friend",
        "front", "future", "garden", "gather", "general", "gentle", "gently", "ghost", "glass",
        "glimpse", "golden", "government", "grand", "grass", "great", "green", "ground", "group",
        "guard", "guide", "guild", "habit", "handle", "happen", "harbor", "hardly", "header",
        "heading", "heart", "heavy", "height", "herself", "hidden", "himself", "history",
        "holding", "hollow", "honor", "horizon", "horse", "house", "however", "human", "hundred",
        "imagine", "important", "include", "indeed", "index", "inkwell", "inside", "instead",
        "interest", "island", "itself", "journal", "journey", "judgment", "keeper", "kingdom",
        "knight", "knowledge", "known", "language", "lantern", "large", "later", "laugh",
        "laughed", "leader", "leave", "ledger", "length", "letter", "level", "library", "light",
        "likely", "listen", "little", "living", "location", "lonely", "looking", "machine",
        "magic", "manuscript", "margin", "market", "master", "matter", "measure", "medicine",
        "memory", "mention", "merchant", "message", "metal", "method", "middle", "midnight",
        "might", "military", "million", "minute", "mirror", "modern", "moment", "morning",
        "mother", "mountain", "movement", "murmur", "murmured", "music", "mystery", "narrative",
        "narrow", "nation", "natural", "nature", "nearly", "necessary", "neither", "network",
        "never", "night", "noble", "normal", "north", "nothing", "notice", "novel", "number",
        "object", "observe", "ocean", "office", "officer", "official", "often", "order",
        "ordinary", "origin", "other", "outside", "outline", "page", "palace", "paper",
        "paragraph", "parchment", "parent", "particular", "passage", "passive", "pattern",
        "pause", "paused", "peace", "people", "perhaps", "period", "person", "personal",
        "phrase", "physical", "picture", "piece", "place", "plain", "planet", "point", "poison",
        "police", "policy", "portable", "position", "possible", "power", "practice", "prepare",
        "present", "president", "pressure", "pretty", "previous", "prince", "princess", "print",
        "private", "probably", "problem", "process", "produce", "professor", "profile",
        "program", "project", "prologue", "promise", "prompt", "proper", "protect", "provide",
        "public", "publish", "purpose", "quality", "quarter", "queen", "question", "quick",
        "quickly", "quiet", "quietly", "quite", "quote", "rather", "raven", "reach", "reached",
        "reader", "reading", "ready", "reality", "realize", "really", "reason", "receive",
        "recent", "record", "reference", "reflect", "region", "remain", "remember", "remove",
        "repeat", "replace", "replied", "reply", "report", "require", "research", "resource",
        "respect", "result", "return", "reveal", "review", "revision", "rhythm", "right",
        "river", "royal", "ruler", "running", "sacred", "Sailing", "sample", "scene", "scholar",
        "school", "science", "screen", "script", "search", "season", "second", "secret",
        "section", "security", "select", "Celtic", "sense", "sentence", "separate", "series",
        "serious", "service", "session", "setting", "seven", "several", "shadow", "shake",
        "shall", "shape", "share", "sharp", "sheet", "shield", "shift", "shining", "short",
        "should", "shoulder", "shouted", "signal", "silence", "silent", "silently", "silver",
        "similar", "simple", "simply", "since", "single", "sister", "situation", "sixteen",
        "sleep", "sleeping", "slightly", "sloop", "slowly", "small", "smile", "smiled", "smoke",
        "smooth", "society", "softly", "soldier", "solution", "someone", "something", "sometimes",
        "somewhat", "sound", "source", "south", "space", "speak", "special", "species", "speech",
        "speed", "spell", "spirit", "spoke", "spoken", "spring", "sprint", "square", "stage",
        "stand", "standard", "start", "state", "statement", "station", "status", "steady",
        "steel", "stepped", "still", "stone", "stood", "storage", "storm", "story", "straight",
        "strange", "stranger", "stream", "street", "strength", "stretch", "strike", "string",
        "strong", "structure", "struggle", "student", "studio", "study", "style", "subject",
        "sudden", "suddenly", "suffer", "suggest", "summer", "Summary", "support", "suppose",
        "surface", "surprise", "survival", "sword", "symbol", "system", "table", "taken",
        "target", "tavern", "teach", "teacher", "temple", "tension", "thousand", "though",
        "thought", "three", "through", "throughout", "throw", "thunder", "timer", "title",
        "today", "together", "tomorrow", "tonight", "total", "touch", "toward", "towards",
        "tower", "track", "trade", "train", "transfer", "travel", "treasure", "treat", "trouble",
        "truth", "twelve", "twenty", "twice", "under", "understand", "underline", "until",
        "usual", "usually", "valley", "value", "various", "velvet", "version", "vessel",
        "village", "vintage", "voice", "volume", "waiting", "walked", "watch", "watched",
        "water", "weapon", "weather", "weight", "welcome", "whether", "which", "while",
        "whisper", "whispered", "white", "whole", "whose", "window", "winter", "wisdom",
        "within", "without", "woman", "women", "wonder", "wooden", "world", "would", "write",
        "writer", "writing", "written", "wrong", "wrote", "yellow", "yesterday", "young",
    ]
    for w in baseline_words:
        words.add(w.lower())

    sorted_words = sorted(words)
    with open(dict_path, "w", encoding="utf-8", newline="\n") as f:
        for w in sorted_words:
            f.write(w + "\n")

    if not os.path.exists(user_dict_path):
        with open(user_dict_path, "w", encoding="utf-8") as f:
            json.dump(["volmini", "volumenodex", "corvus"], f)

    print(f"[OK] Built compact dictionary: {len(sorted_words):,} words ({os.path.getsize(dict_path):,} bytes)")


if __name__ == "__main__":
    build_splash_logo()
    build_stripped_compendium()
    build_compact_dictionary()
