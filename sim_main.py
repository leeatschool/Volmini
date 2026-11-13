"""Desktop Simulator for Volmini (ESP32 Monochrome FrameBuffer Preview).

Renders the exact 1-bit MicroPython FrameBuffer pixel-for-pixel in a desktop window
 across any DIY display profile (`gdey075t7_800x480`, `ssd1680_400x300`,
`sharp_400x240`, `st7796_480x320`, `st7789_320x240`) with full keyboard and
pointer/touchpad simulation.

Usage:
    python sim_main.py
    python sim_main.py --display gdey075t7_800x480
    python sim_main.py --display gdey075t7_800x480 --screenshot preview_75.png
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from volmini.hal.base import KeyCode
from volmini.hal.displays import DISPLAY_PROFILES
from volmini.hal.hal_desktop import DesktopHAL
from volmini.ui.app import VolminiApp, ViewState


def save_framebuffer_png(hal: DesktopHAL, out_path: str, scale: int = 2) -> None:
    """Exports the current 1-bit FrameBuffer to a crisp PNG image using Pillow."""
    from PIL import Image
    w, h = hal.width, hal.height
    img = Image.new("RGB", (w * scale, h * scale), (18, 20, 26))
    pixels = img.load()
    for y in range(h):
        for x in range(w):
            bit = hal.fb.pixel(x, y)
            col = (244, 244, 240) if bit else (18, 20, 26)
            for sy in range(scale):
                for sx in range(scale):
                    pixels[x * scale + sx, y * scale + sy] = col
    img.save(out_path)


def run_gui_simulator(screenshot_path: str = None, display_profile: str = "sharp_400x240") -> int:
    hal = DesktopHAL(display_profile=display_profile)
    app_logic = VolminiApp(hal)

    if screenshot_path:
        # Headless screenshot verification mode
        app_logic.run_boot_sequence(interactive_wait=True)
        boot_path = screenshot_path.replace(".png", "_boot.png")
        win_scale = 1 if hal.width >= 800 else 2
        save_framebuffer_png(hal, boot_path, scale=win_scale)

        app_logic.view = ViewState.EDITOR
        # Show pointer hovering over the Dynamic Top Ribbon for preview
        hal.push_pointer(x=98, y=18, clicked=False)
        app_logic.tick()
        app_logic.relayout()
        app_logic.render()
        save_framebuffer_png(hal, screenshot_path, scale=win_scale)
        print(f"[OK] Saved simulator screenshots ({hal.width}x{hal.height}): {boot_path} & {screenshot_path}")
        return 0

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QImage, QPainter, QColor, QKeyEvent
    from PySide6.QtWidgets import QApplication, QWidget

    class SimulatorWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.scale = 1 if hal.width >= 800 else 2
            self.setWindowTitle(
                f"Volmini — ESP32 Simulator [{hal.display_profile.name}]"
            )
            self.setFixedSize(hal.width * self.scale, hal.height * self.scale)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMouseTracking(True)

            hal.on_present_callback = lambda _: self.update()

            # Show Boot Initiating Splash for 1.2s, then transition to Editor
            app_logic.run_boot_sequence(interactive_wait=True)
            QTimer.singleShot(1200, self._finish_boot_splash)

            self._tick_timer = QTimer(self)
            self._tick_timer.setInterval(30)
            self._tick_timer.timeout.connect(self._on_tick)
            self._tick_timer.start()

        def _finish_boot_splash(self):
            if app_logic.view == ViewState.BOOT_SPLASH:
                app_logic.view = ViewState.EDITOR
                app_logic.relayout()
                app_logic.render()

        def _on_tick(self):
            app_logic.tick()

        def paintEvent(self, event):
            w, h = hal.width, hal.height
            img = QImage(w, h, QImage.Format.Format_RGB32)
            fg = QColor(244, 244, 240).rgb()
            bg = QColor(20, 22, 28).rgb()
            for y in range(h):
                for x in range(w):
                    img.setPixel(x, y, fg if hal.fb.pixel(x, y) else bg)

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(self.rect(), img)
            painter.end()

        def mouseMoveEvent(self, event):
            pos = event.position()
            fx = int(pos.x() // self.scale)
            fy = int(pos.y() // self.scale)
            hal.push_pointer(fx, fy, clicked=False, pressed=bool(event.buttons() & Qt.MouseButton.LeftButton))

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position()
                fx = int(pos.x() // self.scale)
                fy = int(pos.y() // self.scale)
                hal.push_pointer(fx, fy, clicked=True, pressed=True)

        def wheelEvent(self, event):
            delta_y = event.angleDelta().y()
            if delta_y != 0:
                pos = event.position()
                fx = int(pos.x() // self.scale)
                fy = int(pos.y() // self.scale)
                hal.push_pointer(fx, fy, clicked=False, scroll_y=(-1 if delta_y > 0 else 1))

        def keyPressEvent(self, event: QKeyEvent):
            qt_key = event.key()
            mods = event.modifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

            key_map = {
                Qt.Key.Key_Return: KeyCode.ENTER,
                Qt.Key.Key_Enter: KeyCode.ENTER,
                Qt.Key.Key_Backspace: KeyCode.BACKSPACE,
                Qt.Key.Key_Delete: KeyCode.DELETE,
                Qt.Key.Key_Tab: KeyCode.TAB,
                Qt.Key.Key_Escape: KeyCode.ESC,
                Qt.Key.Key_Up: KeyCode.UP,
                Qt.Key.Key_Down: KeyCode.DOWN,
                Qt.Key.Key_Left: KeyCode.LEFT,
                Qt.Key.Key_Right: KeyCode.RIGHT,
                Qt.Key.Key_Home: KeyCode.HOME,
                Qt.Key.Key_End: KeyCode.END,
                Qt.Key.Key_F1: KeyCode.F1_HELP,
                Qt.Key.Key_F2: KeyCode.F2_OUTLINE,
                Qt.Key.Key_F3: KeyCode.F3_REFERENCE,
                Qt.Key.Key_F4: KeyCode.F4_REVIEW,
                Qt.Key.Key_F5: KeyCode.F5_CORVUS,
                Qt.Key.Key_F6: KeyCode.F6_BLE_BEAM,
                Qt.Key.Key_F7: KeyCode.F7_PAGE_SETUP,
                Qt.Key.Key_F8: KeyCode.F8_RIBBON,
            }

            if qt_key in key_map:
                hal.push_key(key_map[qt_key], "\n" if key_map[qt_key] == KeyCode.ENTER else "", ctrl=ctrl, shift=shift)
                return

            if ctrl:
                ctrl_map = {
                    Qt.Key.Key_N: KeyCode.CTRL_N,
                    Qt.Key.Key_O: KeyCode.CTRL_O,
                    Qt.Key.Key_S: KeyCode.CTRL_S,
                    Qt.Key.Key_E: KeyCode.CTRL_E,
                    Qt.Key.Key_B: KeyCode.CTRL_B,
                    Qt.Key.Key_I: KeyCode.CTRL_I,
                    Qt.Key.Key_U: KeyCode.CTRL_U,
                    Qt.Key.Key_T: KeyCode.CTRL_T,
                    Qt.Key.Key_Q: KeyCode.CTRL_Q,
                    Qt.Key.Key_L: KeyCode.CTRL_L,
                    Qt.Key.Key_K: KeyCode.CTRL_K,
                    Qt.Key.Key_R: KeyCode.CTRL_R,
                    Qt.Key.Key_P: KeyCode.CTRL_P,
                    Qt.Key.Key_Z: KeyCode.CTRL_Z,
                    Qt.Key.Key_Y: KeyCode.CTRL_Y,
                    Qt.Key.Key_M: KeyCode.CTRL_M,
                    Qt.Key.Key_0: KeyCode.CTRL_0,
                    Qt.Key.Key_1: KeyCode.CTRL_1,
                    Qt.Key.Key_2: KeyCode.CTRL_2,
                    Qt.Key.Key_3: KeyCode.CTRL_3,
                }
                if qt_key in ctrl_map:
                    hal.push_key(ctrl_map[qt_key], ctrl=True, shift=shift)
                    return

            txt = event.text()
            if txt and ord(txt[0]) >= 32:
                hal.push_key(txt[0], txt[0], ctrl=False, shift=shift)

    qapp = QApplication(sys.argv)
    win = SimulatorWindow()
    win.show()
    return qapp.exec()


if __name__ == "__main__":
    shot = None
    prof = "sharp_400x240"
    if "--display" in sys.argv:
        idx = sys.argv.index("--display")
        if idx + 1 < len(sys.argv):
            prof = sys.argv[idx + 1]
    if "--screenshot" in sys.argv:
        idx = sys.argv.index("--screenshot")
        if idx + 1 < len(sys.argv):
            shot = sys.argv[idx + 1]
    sys.exit(run_gui_simulator(shot, display_profile=prof))
