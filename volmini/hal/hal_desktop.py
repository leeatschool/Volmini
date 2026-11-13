"""Desktop Simulator & Headless Test HAL for Volmini.

Allows running the exact same monochrome FrameBuffer code on a desktop PC
for automated testing and interactive previewing across all DIY display profiles
(e.g., `gdey075t7_800x480`, `ssd1680_400x300`, `sharp_400x240`, `st7796_480x320`, `st7789_320x240`).
"""

import os
from volmini.hal.base import VolminiHAL, KeyEvent, PointerEvent
from volmini.hal.displays import DISPLAY_PROFILES, DisplayProfile
from volmini.compat import makedirs_safe


class DesktopHAL(VolminiHAL):
    """HAL implementation for desktop simulator and unit testing."""

    def __init__(
        self,
        width: int = 400,
        height: int = 240,
        storage_root: str = None,
        display_profile: str = None,
    ):
        prof = None
        if isinstance(display_profile, DisplayProfile):
            prof = display_profile
        elif isinstance(display_profile, str) and display_profile in DISPLAY_PROFILES:
            prof = DISPLAY_PROFILES[display_profile]

        super().__init__(width=width, height=height, display_profile=prof)
        if storage_root is None:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            storage_root = os.path.join(base, "documents")
        self.storage_root = storage_root
        self.sd_mounted = True
        makedirs_safe(self.storage_root)
        self._key_queue = []
        self.present_count = 0
        self.last_partial_region = None
        self.on_present_callback = None

    def push_key(self, key: str, char: str = "", ctrl: bool = False, shift: bool = False, alt: bool = False) -> None:
        self._key_queue.append(KeyEvent(key=key, char=char, ctrl=ctrl, shift=shift, alt=alt))

    def push_key_event(self, ev: KeyEvent) -> None:
        self._key_queue.append(ev)

    def push_pointer(
        self, x: int, y: int, clicked: bool = False, pressed: bool = False, scroll_y: int = 0
    ) -> None:
        self.push_pointer_event(
            PointerEvent(x=x, y=y, clicked=clicked, pressed=pressed, scroll_y=scroll_y)
        )

    def poll_key(self):
        if self._key_queue:
            return self._key_queue.pop(0)
        return None

    def present(self) -> None:
        self.present_count += 1
        self.last_partial_region = (0, 0, self.width, self.height)
        if self.on_present_callback is not None:
            self.on_present_callback(self)

    def present_region(self, x: int, y: int, w: int, h: int) -> None:
        self.present_count += 1
        self.last_partial_region = (x, y, w, h)
        if self.on_present_callback is not None:
            self.on_present_callback(self)
