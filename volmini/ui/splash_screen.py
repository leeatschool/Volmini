"""Initiating Boot Splash Screen for Volmini when the ESP32 is powered on.

Ported from Volumenodex's dark slate splash screen (`main.py`), adapted to 1-bit
monochrome with the `V|` emblem, live hardware/index initialization status bar,
and Instant Session Resume prompt.
"""

from volmini.ui.font5x8 import draw_text, draw_bitmap_1bit
from volmini.ui.splash_logo import LOGO_BITMAP, LOGO_WIDTH, LOGO_HEIGHT


class BootSplashRenderer:
    """Renders the power-on initiating screen onto a FrameBuffer."""

    @staticmethod
    def render(
        fb,
        status_text: str = "Initializing workspace...",
        progress_pct: int = 25,
        resume_filename: str = "",
    ) -> None:
        w = fb.width
        h = fb.height
        fb.fill(0)  # Dark background (0 = black, 1 = white ink on splash)

        # Outer double border frame matching Volumenodex splash card
        fb.rect(4, 4, w - 8, h - 8, 1)
        fb.rect(7, 7, w - 14, h - 14, 1)

        # Corner ornamental ticks
        fb.fill_rect(7, 7, 5, 5, 1)
        fb.fill_rect(w - 12, 7, 5, 5, 1)
        fb.fill_rect(7, h - 12, 5, 5, 1)
        fb.fill_rect(w - 12, h - 12, 5, 5, 1)

        # V| Emblem Bitmap (48x48) on left side of splash card
        logo_x = 26
        logo_y = max(24, (h // 2) - 44)
        fb.rect(logo_x - 3, logo_y - 3, LOGO_WIDTH + 6, LOGO_HEIGHT + 6, 1)
        draw_bitmap_1bit(fb, LOGO_BITMAP, LOGO_WIDTH, LOGO_HEIGHT, logo_x, logo_y, color=1)

        # Brand Title & Subtitle
        title_x = logo_x + LOGO_WIDTH + 18
        draw_text(fb, "VOLMINI", title_x, logo_y + 4, color=1, bold=True, scale_y=2)
        draw_text(fb, "Word Processing Studio  *  ESP32", title_x, logo_y + 26, color=1)
        draw_text(fb, "RF Radios: OFF  |  Print Engine: Ready", title_x, logo_y + 39, color=1, italic=True)

        # Horizontal divider
        div_y = logo_y + LOGO_HEIGHT + 16
        fb.hline(20, div_y, w - 40, 1)

        # Initialization status message
        status_y = div_y + 12
        draw_text(fb, status_text, 24, status_y, color=1, max_width=w - 48)

        # Progress bar
        bar_x = 24
        bar_y = status_y + 14
        bar_w = w - 48
        bar_h = 10
        fb.rect(bar_x, bar_y, bar_w, bar_h, 1)
        fill_w = int(((bar_w - 4) * max(0, min(100, progress_pct))) // 100)
        if fill_w > 0:
            fb.fill_rect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4, 1)

        # Bottom session resume / launcher hint
        hint_y = h - 24
        if resume_filename:
            short_res = resume_filename.replace("\\", "/").split("/")[-1]
            hint = f"Resume: {short_res}  [SPACE: Launcher]"
        else:
            hint = "[ENTER: Start Writing]   [SPACE: Document Launcher]"
        draw_text(fb, hint, 24, hint_y, color=1, max_width=w - 48)
