"""Corvus the Raven — 1-bit Pixel Companion, Insight Engine, and Sprint/Break Timer for Volmini.

Stripped-down port of volumenodex.pet (Corvus only) featuring:
- 16x16 1-bit pixel-art Raven sprite (Idle/Writing & Sleeping frames)
- Mood states (IDLE, WRITING, ALERT, CELEBRATING, SLEEPING, NUDGING)
- Word-count milestone celebration
- Real-time active-sentence duplicate-word alert
- Creative Fiction & General Non-Fiction writing spark prompts
- Configurable writing sprint & wellness break timer
"""

import re
from volmini.compat import ticks_ms, ticks_diff
from volmini.core.document_model import DocumentMode


# 16x16 1-bit pixel art sprites for Corvus the Raven (2 bytes per row = 32 bytes total)
CORVUS_SPRITE_AWAKE = bytes([
    0x03, 0xC0,  # ......####......
    0x07, 0xE0,  # .....######.....
    0x0F, 0xF8,  # ....#########...
    0x1D, 0xFC,  # ...###.#######..
    0x0F, 0xFE,  # ....###########.
    0x07, 0xC0,  # .....#####......
    0x0F, 0xE0,  # ....#######.....
    0x1F, 0xF0,  # ...#########....
    0x3F, 0xF8,  # ..###########...
    0x3F, 0xF8,  # ..###########...
    0x1F, 0xF0,  # ...#########....
    0x0F, 0xE0,  # ....#######.....
    0x07, 0xC0,  # .....#####......
    0x02, 0x40,  # ......#..#......
    0x02, 0x40,  # ......#..#......
    0x07, 0xE0,  # .....######.....
])

CORVUS_SPRITE_SLEEP = bytes([
    0x00, 0x00,
    0x00, 0x38,  # ..........###... (Z)
    0x00, 0x10,  # ...........#....
    0x03, 0xB8,  # ......###.###...
    0x07, 0xC0,  # .....#####......
    0x0F, 0xE0,  # ....#######.....
    0x0F, 0xE0,  # ....#######.....
    0x1F, 0xF0,  # ...#########....
    0x3F, 0xF8,  # ..###########...
    0x3F, 0xF8,  # ..###########...
    0x1F, 0xF0,  # ...#########....
    0x0F, 0xE0,  # ....#######.....
    0x07, 0xC0,  # .....#####......
    0x02, 0x40,
    0x07, 0xE0,
    0x00, 0x00,
])


class PetMood:
    IDLE = "idle"
    WRITING = "writing"
    ALERT = "alert"
    CELEBRATING = "celebrating"
    SLEEPING = "sleeping"
    NUDGING = "nudging"


IGNORED_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "were", "are", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "i", "you",
    "he", "she", "it", "we", "they", "my", "your", "his", "her", "its",
    "our", "their", "this", "that", "these", "those", "me", "him", "them",
    "us", "so", "if", "up", "out", "no", "not", "too", "into", "over",
}


class CorvusCompanion:
    """Corvus the Literary Raven companion & sprint timer."""

    NAME = "Corvus"
    TITLE = "The Literary Raven"

    IDLE_QUOTES = [
        "The shadows dance across the parchment. What twist lurks next?",
        "Ink is thicker than sea water. Press on, wordsmith.",
        "Silence is the inkwell of the brooding mind.",
        "A well-placed secret weighs more than a thousand idle words.",
    ]

    MILESTONE_QUOTES = [
        "Marvelous. Another milestone claimed from the void of the blank page.",
        "A grim victory over silence! Your manuscript grows ever more potent.",
        "Nevermore shall this word count be questioned. Outstanding craft.",
    ]

    BREAK_QUOTES = [
        "Even ravens must fold their wings. Quench your thirst and stretch.",
        "Your eyes require respite from the lantern light. Breathe and return renewed.",
    ]

    FICTION_PROMPTS = [
        "Introduce an unexpected sound from behind a locked door.",
        "Have a character reveal a truth by telling a convincing half-lie.",
        "Describe the temperature of the room and how it betrays nervousness.",
        "What did someone in this scene steal: an object, a glance, or a memory?",
        "Contrast what a character says aloud with what their hands are doing.",
    ]

    NONFICTION_PROMPTS = [
        "Is your core thesis stated clearly before the end of this section?",
        "Consider introducing a concrete counterargument to fortify this claim.",
        "Ensure each major section opens with clear topical signposting.",
        "Could a concrete historical or empirical example sharpen this point?",
        "Check transitions: does this paragraph flow logically from the last?",
    ]

    MILESTONES = (100, 250, 500, 1000, 1500, 2000, 3000, 5000, 10000)

    def __init__(self):
        self.mood = PetMood.IDLE
        self.document_mode = DocumentMode.CREATIVE_FICTION
        self.last_message = self.IDLE_QUOTES[0]
        self.achieved_milestones = set()
        self.last_warned_word = None
        self._prompt_idx = 0
        self._quote_idx = 0

        # Timers (millisecond ticks)
        self.last_activity_ms = ticks_ms()
        self.idle_sleep_timeout_ms = 45_000  # 45s of silence -> SLEEPING

        # Sprint / Wellness Break Timer
        self.sprint_active = False
        self.sprint_duration_minutes = 25
        self.sprint_start_ms = 0
        self.sprint_start_words = 0
        self.current_words = 0

    @property
    def sprite(self) -> bytes:
        if self.mood == PetMood.SLEEPING:
            return CORVUS_SPRITE_SLEEP
        return CORVUS_SPRITE_AWAKE

    def set_document_mode(self, mode: str) -> None:
        self.document_mode = mode
        if mode == DocumentMode.NON_FICTION:
            self.last_message = "Non-Fiction Mode: Monitoring argument clarity and expository flow."
        else:
            self.last_message = "Creative Fiction Mode: Crafting vivid prose and narrative tension."
        self.mood = PetMood.IDLE

    def start_sprint(self, duration_minutes: int = 25, current_word_count: int = 0) -> None:
        self.sprint_duration_minutes = max(1, int(duration_minutes))
        self.sprint_active = True
        self.sprint_start_ms = ticks_ms()
        self.sprint_start_words = current_word_count
        self.current_words = current_word_count
        self.mood = PetMood.WRITING
        self.last_message = f"Sprint started ({self.sprint_duration_minutes}m)! Write without hesitation."

    def stop_sprint(self) -> None:
        self.sprint_active = False
        delta = max(0, self.current_words - self.sprint_start_words)
        self.mood = PetMood.IDLE
        self.last_message = f"Sprint ended (+{delta} words drafted)."

    def sprint_remaining_seconds(self, now_ms: int = None) -> int:
        if not self.sprint_active:
            return 0
        if now_ms is None:
            now_ms = ticks_ms()
        elapsed_s = ticks_diff(now_ms, self.sprint_start_ms) // 1000
        total_s = self.sprint_duration_minutes * 60
        rem = total_s - elapsed_s
        return max(0, rem)

    def tick(self, now_ms: int = None) -> None:
        """Periodic timer check for idle sleep and sprint completion."""
        if now_ms is None:
            now_ms = ticks_ms()

        if self.sprint_active and self.sprint_remaining_seconds(now_ms) == 0:
            self.sprint_active = False
            delta = max(0, self.current_words - self.sprint_start_words)
            self.mood = PetMood.NUDGING
            q = self.BREAK_QUOTES[self._quote_idx % len(self.BREAK_QUOTES)]
            self._quote_idx += 1
            self.last_message = f"Sprint Complete (+{delta}w)! {q}"
            return

        if self.mood != PetMood.SLEEPING and ticks_diff(now_ms, self.last_activity_ms) >= self.idle_sleep_timeout_ms:
            self.mood = PetMood.SLEEPING
            self.last_message = "*Corvus folds his wings in silent slumber...*"

    def on_keystroke(self, para_text: str, total_words: int, now_ms: int = None) -> None:
        if now_ms is None:
            now_ms = ticks_ms()
        self.last_activity_ms = now_ms
        self.current_words = total_words
        if self.mood in (PetMood.SLEEPING, PetMood.IDLE):
            self.mood = PetMood.WRITING

        # 1. Check word count milestones
        for m in self.MILESTONES:
            if total_words >= m and m not in self.achieved_milestones and (m <= total_words < m + 15):
                self.achieved_milestones.add(m)
                self.mood = PetMood.CELEBRATING
                cheer = self.MILESTONE_QUOTES[self._quote_idx % len(self.MILESTONE_QUOTES)]
                self._quote_idx += 1
                self.last_message = f"{m} Words Reached! {cheer}"
                return

        # 2. Check active sentence for duplicate words (4+ letters)
        if para_text:
            parts = [p.strip() for p in re.split(r"[.!?\n]+", para_text) if p.strip()]
            active_sent = parts[-1].lower() if parts else ""
            if active_sent:
                counts = {}
                for w in active_sent.split():
                    w_clean = "".join(ch for ch in w if ch.isalpha())
                    if len(w_clean) >= 4 and w_clean not in IGNORED_STOPWORDS:
                        counts[w_clean] = counts.get(w_clean, 0) + 1
                        if counts[w_clean] >= 2 and w_clean != self.last_warned_word:
                            self.last_warned_word = w_clean
                            self.mood = PetMood.ALERT
                            self.last_message = (
                                f"You used '{w_clean}' twice in this sentence. Consider a fresher word."
                            )
                            return

    def trigger_spark(self) -> str:
        """Generates a mode-specific writing prompt."""
        self.mood = PetMood.ALERT
        if self.document_mode == DocumentMode.NON_FICTION:
            pool = self.NONFICTION_PROMPTS
        else:
            pool = self.FICTION_PROMPTS
        prompt = pool[self._prompt_idx % len(pool)]
        self._prompt_idx += 1
        self.last_message = f"Spark: {prompt}"
        return self.last_message
