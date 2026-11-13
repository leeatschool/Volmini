"""MikroElektronika (MIKROE) Touchpad 5 Click Driver (Azoteq IQS550) for Volmini.

Hardware Overview:
- Board: MIKROE Touchpad 5 Click (29 x 23 mm capacitive trackpad matrix)
- Controller IC: Azoteq IQS550 (Projected Capacitive Trackpad Controller)
- Default 7-bit I2C Address: 0x74
- Control Pins:
  - INT (RDY): Active-HIGH ready indicator signaling an open I2C communication window
  - RST (NRST): Active-LOW hardware reset pin
- Register Map (16-bit big-endian register addresses, read in a single 9-byte burst from 0x000D):
  - 0x000D : GestureEvents0 (Bit 0 = SINGLE_TAP, Bit 1 = PRESS_AND_HOLD, Bits 2..5 = SWIPE)
  - 0x000E : GestureEvents1 (Bit 0 = TWO_FINGER_TAP, Bit 1 = SCROLL, Bit 2 = ZOOM)
  - 0x000F : SystemInfo0
  - 0x0010 : SystemInfo1
  - 0x0011 : NoOfFingers (0, 1, 2...)
  - 0x0012..0x0013 : Relative X (signed 16-bit big-endian)
  - 0x0014..0x0015 : Relative Y (signed 16-bit big-endian)
  - 0xEEEE : End Communication Window command (write 1 byte to close window & resume scan)
"""

from volmini.compat import sleep_ms
from volmini.hal.base import PointerEvent


class Touchpad5ClickDriver:
    """I2C driver for the MIKROE Touchpad 5 Click (Azoteq IQS550) trackpad."""

    I2C_ADDR = 0x74
    REG_GESTURE_EVENTS_0 = 0x000D
    REG_END_COMM_WINDOW = 0xEEEE

    # GestureEvents0 (0x000D) bit masks
    SINGLE_TAP = 0x01
    PRESS_AND_HOLD = 0x02
    SWIPE_X_NEG = 0x04
    SWIPE_X_POS = 0x08
    SWIPE_Y_POS = 0x10
    SWIPE_Y_NEG = 0x20

    # GestureEvents1 (0x000E) bit masks
    TWO_FINGER_TAP = 0x01
    TWO_FINGER_SCROLL = 0x02

    def __init__(
        self,
        i2c,
        addr: int = I2C_ADDR,
        rdy_pin=None,
        rst_pin=None,
        sensitivity: int = 1,
        invert_x: bool = False,
        invert_y: bool = False,
    ):
        self.i2c = i2c
        self.addr = int(addr)
        self.rdy_pin = rdy_pin
        self.rst_pin = rst_pin
        self.sensitivity = max(1, int(sensitivity))
        self.invert_x = bool(invert_x)
        self.invert_y = bool(invert_y)
        self._scroll_accum = 0

    def reset(self) -> None:
        """Pulses NRST low to hardware-reset the Touchpad 5 Click."""
        if self.rst_pin is None:
            return
        self.rst_pin.value(0)
        sleep_ms(5)
        self.rst_pin.value(1)
        sleep_ms(15)

    def is_ready(self) -> bool:
        """Returns True when the Touchpad 5 Click INT (RDY) pin is HIGH."""
        if self.rdy_pin is None:
            return True
        try:
            return bool(self.rdy_pin.value() == 1)
        except Exception:
            return False

    @staticmethod
    def _to_int16_be(hi: int, lo: int) -> int:
        val = ((hi & 0xFF) << 8) | (lo & 0xFF)
        if val & 0x8000:
            val -= 0x10000
        return val

    def _read_burst_9(self):
        """Reads 9 bytes starting at 16-bit register 0x000D and closes the communication window."""
        if self.i2c is None:
            return None
        # Write 16-bit register address 0x000D
        self.i2c.writeto(self.addr, bytes([0x00, 0x0D]))
        data = self.i2c.readfrom(self.addr, 9)
        # Close communication window (0xEEEE + 1 dummy byte) so IQS550 resumes sensing
        self.i2c.writeto(self.addr, bytes([0xEE, 0xEE, 0x00]))
        return data

    def poll(self, curr_x: int, curr_y: int, screen_w: int, screen_h: int):
        """Polls the Touchpad 5 Click and returns `(new_x, new_y, PointerEvent)` or `None`."""
        if not self.is_ready():
            return None

        try:
            raw = self._read_burst_9()
        except Exception:
            return None

        if not raw or len(raw) < 9:
            return None

        gest0 = raw[0]
        gest1 = raw[1]
        fingers = raw[4]
        rel_x = self._to_int16_be(raw[5], raw[6])
        rel_y = self._to_int16_be(raw[7], raw[8])

        if self.invert_x:
            rel_x = -rel_x
        if self.invert_y:
            rel_y = -rel_y

        clicked = bool(gest0 & self.SINGLE_TAP)
        pressed = bool((gest0 & self.PRESS_AND_HOLD) or fingers >= 1)
        scroll_y = 0

        # Two-finger scroll or vertical swipe maps cleanly to page/list scrolling
        if (gest1 & self.TWO_FINGER_SCROLL) or fingers == 2:
            self._scroll_accum += rel_y
            if abs(self._scroll_accum) >= 8:
                scroll_y = 1 if self._scroll_accum > 0 else -1
                self._scroll_accum = 0
            rel_x = 0
            rel_y = 0
        elif gest0 & self.SWIPE_Y_NEG:
            scroll_y = 1
        elif gest0 & self.SWIPE_Y_POS:
            scroll_y = -1
        else:
            self._scroll_accum = 0

        dx = rel_x * self.sensitivity
        dy = rel_y * self.sensitivity

        if dx == 0 and dy == 0 and not clicked and scroll_y == 0:
            return None

        nx = max(0, min(screen_w - 1, curr_x + dx))
        ny = max(0, min(screen_h - 1, curr_y + dy))
        ev = PointerEvent(x=nx, y=ny, clicked=clicked, pressed=pressed, scroll_y=scroll_y)
        return (nx, ny, ev)
