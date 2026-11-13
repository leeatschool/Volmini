"""Base Hardware Abstraction Layer (HAL) definitions for Volmini."""

from volmini.compat import FrameBuffer, MONO_HLSB
from volmini.hal.displays import DISPLAY_PROFILES, DisplayProfile


class KeyCode:
    """Normalized key codes across physical ESP32 keyboards and desktop simulator."""
    NONE = ""
    ENTER = "\n"
    BACKSPACE = "\x08"
    DELETE = "\x7f"
    TAB = "\t"
    ESC = "\x1b"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    PAGE_UP = "PGUP"
    PAGE_DOWN = "PGDN"
    HOME = "HOME"
    END = "END"

    # Control / Function chords
    CTRL_N = "CTRL+N"          # New Document
    CTRL_O = "CTRL+O"          # Open / File Browser
    CTRL_S = "CTRL+S"          # Save Now
    CTRL_E = "CTRL+E"          # Export (.docx / .txt / .md)
    CTRL_B = "CTRL+B"          # Toggle Bold
    CTRL_I = "CTRL+I"          # Toggle Italic
    CTRL_U = "CTRL+U"          # Toggle Underline
    CTRL_1 = "CTRL+1"          # Heading 1
    CTRL_2 = "CTRL+2"          # Heading 2
    CTRL_3 = "CTRL+3"          # Heading 3
    CTRL_0 = "CTRL+0"          # Normal Paragraph
    CTRL_T = "CTRL+T"          # Title Style
    CTRL_Q = "CTRL+Q"          # Blockquote Style
    CTRL_L = "CTRL+L"          # Align Left
    CTRL_K = "CTRL+K"          # Align Center
    CTRL_R = "CTRL+R"          # Align Right
    CTRL_P = "CTRL+P"          # Insert Page Break / Page Setup
    CTRL_Z = "CTRL+Z"          # Undo
    CTRL_Y = "CTRL+Y"          # Redo
    CTRL_F = "CTRL+F"          # Find in Manuscript
    CTRL_M = "CTRL+M"          # Switch Authoring Mode (Creative Fiction / Non-Fiction)

    # Overlay views (F1 - F8 or Alt/Fn chords)
    F1_HELP = "F1"             # Quick Help & Shortcuts
    F2_OUTLINE = "F2"          # Chapter Outline Navigator
    F3_REFERENCE = "F3"        # Stripped Writer's Reference Compendium
    F4_REVIEW = "F4"           # Revision Lenses & Spell Check Inspector
    F5_CORVUS = "F5"           # Corvus the Raven & Sprint/Break Timer
    F6_BLE_BEAM = "F6"         # On-Demand BLE Beam to Phone
    F7_PAGE_SETUP = "F7"       # Paper Size, Margins & Header/Footer Setup
    F8_RIBBON = "F8"           # Show/Hide Dynamic Formatting Top Ribbon


class KeyEvent:
    """Single keyboard input event."""

    def __init__(self, key: str, char: str = "", ctrl: bool = False, shift: bool = False, alt: bool = False):
        self.key = key
        self.char = char
        self.ctrl = ctrl
        self.shift = shift
        self.alt = alt

    def __repr__(self) -> str:
        return f"KeyEvent(key={self.key!r}, char={self.char!r}, ctrl={self.ctrl}, shift={self.shift})"


class PointerEvent:
    """Touchpad / Trackball / Capacitive Touch / Mouse pointer input event."""

    def __init__(
        self,
        x: int,
        y: int,
        clicked: bool = False,
        pressed: bool = False,
        scroll_y: int = 0,
    ):
        self.x = int(x)
        self.y = int(y)
        self.clicked = bool(clicked)
        self.pressed = bool(pressed)
        self.scroll_y = int(scroll_y)

    def __repr__(self) -> str:
        return (
            f"PointerEvent(x={self.x}, y={self.y}, "
            f"clicked={self.clicked}, pressed={self.pressed}, scroll_y={self.scroll_y})"
        )


class VolminiHAL:
    """Abstract base HAL for ESP32-S3 and Desktop Simulator."""

    def __init__(
        self,
        width: int = 400,
        height: int = 240,
        invert_colors: bool = False,
        display_profile: DisplayProfile = None,
    ):
        if display_profile is not None:
            self.display_profile = display_profile
            width = display_profile.width
            height = display_profile.height
        else:
            self.display_profile = DisplayProfile(
                profile_id=f"custom_{width}x{height}",
                name=f"Display ({width}x{height})",
                width=width,
                height=height,
                tech="memory_lcd",
                controller="generic",
                font_scale=1,
            )

        self.width = int(width)
        self.height = int(height)
        self.invert_colors = bool(invert_colors)
        self._row_bytes = (self.width + 7) // 8
        self.buffer = bytearray(self._row_bytes * self.height)
        self.fb = FrameBuffer(self.buffer, self.width, self.height, MONO_HLSB)
        self.storage_root = "."
        self.sd_mounted = False

        # Pointer / Touchpad state
        self.pointer_x = self.width // 2
        self.pointer_y = self.height // 2
        self.pointer_visible = False
        self._pointer_queue = []

    def clear(self, color: int = 0) -> None:
        self.fb.fill(color)

    def present(self) -> None:
        """Flushes the full framebuffer to the physical display or simulator window."""
        pass

    def present_region(self, x: int, y: int, w: int, h: int) -> None:
        """Flushes a rectangular dirty window (e.g. 0.34s partial update on GDEY075T7 e-Paper)."""
        self.present()

    def poll_key(self):
        """Non-blocking poll returning a KeyEvent or None."""
        return None

    def push_pointer_event(self, ev: PointerEvent) -> None:
        self.pointer_x = max(0, min(self.width - 1, ev.x))
        self.pointer_y = max(0, min(self.height - 1, ev.y))
        self.pointer_visible = True
        self._pointer_queue.append(
            PointerEvent(
                x=self.pointer_x,
                y=self.pointer_y,
                clicked=ev.clicked,
                pressed=ev.pressed,
                scroll_y=ev.scroll_y,
            )
        )

    def poll_pointer(self):
        """Non-blocking poll returning a PointerEvent or None."""
        if self._pointer_queue:
            return self._pointer_queue.pop(0)
        return None

    def battery_percent(self) -> int:
        """Returns battery percentage (0-100)."""
        return 100
