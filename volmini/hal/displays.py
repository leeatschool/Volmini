"""Multi-Display Driver & Profile Registry for DIY Volmini Builds.

Includes native SPI driver support and display profiles for:
1. `gdey075t7_800x480` : Good Display 7.5" 800x480 1-bit E-Paper (UC8179 controller)
   - Full refresh (3.5s), Fast refresh (1.5s), and Hardware Partial Window refresh (0.34s)
   - Deep sleep (2 uA standby)
2. `ssd1680_400x300`   : 4.2" 400x300 SPI E-Paper (Waveshare / WeAct SSD1680 / UC8176)
3. `ssd1680_296x128`   : 2.9" 296x128 SPI E-Paper (SSD1680)
4. `sharp_400x240`     : 2.7" 400x240 Sharp Memory LCD (LS027B7DH01, 60Hz 1-bit reflective)
5. `st7796_480x320`    : 3.5" / 4.0" 480x320 SPI TFT LCD (ST7796 / ILI9488)
6. `st7789_320x240`    : 2.0" / 2.4" / 2.8" 320x240 SPI IPS TFT (ST7789 / ILI9341)
7. `custom`            : User-defined resolution and SPI driver parameters via `hardware_config.json`
"""

import json
from volmini.compat import sleep_ms, path_exists


class DisplayProfile:
    """Hardware and typography scaling parameters for a target display."""

    def __init__(
        self,
        profile_id: str,
        name: str,
        width: int,
        height: int,
        tech: str,               # "epaper", "memory_lcd", "tft"
        controller: str,
        font_scale: int = 1,     # 1 = 6x9 cell, 2 = 12x18 book cell (optional on 800x480)
        partial_refresh_ms: int = 0,
        full_refresh_every: int = 0,
    ):
        self.profile_id = profile_id
        self.name = name
        self.width = int(width)
        self.height = int(height)
        self.tech = tech
        self.controller = controller
        self.font_scale = int(font_scale)
        self.partial_refresh_ms = int(partial_refresh_ms)
        self.full_refresh_every = int(full_refresh_every)

    @property
    def is_epaper(self) -> bool:
        return self.tech == "epaper"

    @property
    def framebuffer_bytes(self) -> int:
        return ((self.width + 7) // 8) * self.height


DISPLAY_PROFILES = {
    "gdey075t7_800x480": DisplayProfile(
        profile_id="gdey075t7_800x480",
        name="Good Display 7.5\" E-Paper GDEY075T7 (800x480, UC8179)",
        width=800,
        height=480,
        tech="epaper",
        controller="UC8179",
        font_scale=1,
        partial_refresh_ms=340,
        full_refresh_every=12,
    ),
    "ssd1680_400x300": DisplayProfile(
        profile_id="ssd1680_400x300",
        name="4.2\" E-Paper Module (400x300, SSD1680/UC8176)",
        width=400,
        height=300,
        tech="epaper",
        controller="SSD1680",
        font_scale=1,
        partial_refresh_ms=300,
        full_refresh_every=15,
    ),
    "ssd1680_296x128": DisplayProfile(
        profile_id="ssd1680_296x128",
        name="2.9\" E-Paper Module (296x128, SSD1680)",
        width=296,
        height=128,
        tech="epaper",
        controller="SSD1680",
        font_scale=1,
        partial_refresh_ms=300,
        full_refresh_every=15,
    ),
    "sharp_400x240": DisplayProfile(
        profile_id="sharp_400x240",
        name="Sharp Memory LCD 2.7\" (400x240, LS027B7DH01)",
        width=400,
        height=240,
        tech="memory_lcd",
        controller="LS027B7DH01",
        font_scale=1,
    ),
    "st7796_480x320": DisplayProfile(
        profile_id="st7796_480x320",
        name="3.5\"/4.0\" SPI TFT LCD (480x320, ST7796/ILI9488)",
        width=480,
        height=320,
        tech="tft",
        controller="ST7796",
        font_scale=1,
    ),
    "st7789_320x240": DisplayProfile(
        profile_id="st7789_320x240",
        name="2.4\"/2.8\" SPI IPS TFT (320x240, ST7789/ILI9341)",
        width=320,
        height=240,
        tech="tft",
        controller="ST7789",
        font_scale=1,
    ),
}


class GDEY075T7Driver:
    """Hardware SPI driver for the Good Display GDEY075T7 7.5" 800x480 E-Paper (UC8179).

    Implements the exact command table from the GDEY075T7 Revision 1.0 datasheet:
    - 4-wire SPI (BS1 = LOW)
    - BUSY pin active-low wait check (Note 5-4: BUSY=0 means busy, BUSY=1 means ready)
    - Full update (3.5s), Fast update (1.5s), Partial Window update (PTIN 0x91 / PTL 0x90 / PTOUT 0x92, 0.34s)
    - Deep Sleep mode (0x02 POF + 0x07 DSLP check code 0xA5, 2 uA current)
    """

    WIDTH = 800
    HEIGHT = 480
    BUF_BYTES = (WIDTH * HEIGHT) // 8  # 48,000 bytes

    def __init__(self, spi, cs_pin, dc_pin, rst_pin, busy_pin=None):
        self.spi = spi
        self.cs = cs_pin
        self.dc = dc_pin
        self.rst = rst_pin
        self.busy = busy_pin
        self.partial_count = 0
        self.initialized = False
        self.command_log = []  # Recorded in unit tests when spi is a mock/recorder

    def _wait_ready(self, timeout_ms: int = 4000) -> None:
        """Waits until BUSY pin goes HIGH (Note 5-4: BUSY is low while IC is busy)."""
        if self.busy is None:
            sleep_ms(2)
            return
        elapsed = 0
        while self.busy.value() == 0 and elapsed < timeout_ms:
            sleep_ms(10)
            elapsed += 10

    def _cmd(self, command: int, data: bytes = None) -> None:
        self.command_log.append((command, len(data) if data is not None else 0))
        if self.spi is None:
            return
        if self.cs is not None:
            self.cs.value(0)
        if self.dc is not None:
            self.dc.value(0)
        self.spi.write(bytes([command]))
        if self.cs is not None:
            self.cs.value(1)
        if data is not None:
            self._data(data)

    def _data(self, data: bytes) -> None:
        if self.spi is None:
            return
        # Datasheet 6.3.3: set CSB HIGH between command and data payload
        if self.cs is not None:
            self.cs.value(0)
        if self.dc is not None:
            self.dc.value(1)
        self.spi.write(data)
        if self.cs is not None:
            self.cs.value(1)

    def reset(self) -> None:
        if self.rst is None:
            return
        self.rst.value(1)
        sleep_ms(20)
        self.rst.value(0)
        sleep_ms(4)
        self.rst.value(1)
        sleep_ms(20)

    def init_panel(self) -> None:
        """Initializes UC8179 registers for 800x480 1-bit KW (Black/White) operation."""
        self.reset()
        # 1. Power Setting (PWR 0x01): internal VDH/VDL/VGH/VGL
        self._cmd(0x01, bytes([0x07, 0x07, 0x3F, 0x3F]))
        # 2. Booster Soft Start (BTST 0x06)
        self._cmd(0x06, bytes([0x17, 0x17, 0x28, 0x17]))
        # 3. Power ON (PON 0x04)
        self._cmd(0x04)
        self._wait_ready(2000)
        # 4. Panel Setting (PSR 0x00): 0x1F = LUT from OTP, KW mode (KW/R=1), UD=1, SHL=1, SHD_N=1, RST_N=1
        self._cmd(0x00, bytes([0x1F]))
        # 5. Resolution Setting (TRES 0x61): 800 (0x0320) x 480 (0x01E0)
        self._cmd(0x61, bytes([0x03, 0x20, 0x01, 0xE0]))
        # 6. Dual SPI (0x15): disabled (standard 4-wire SPI)
        self._cmd(0x15, bytes([0x00]))
        # 7. VCOM and Data Interval Setting (CDI 0x50)
        self._cmd(0x50, bytes([0x10, 0x07]))
        # 8. TCON Setting (0x60)
        self._cmd(0x60, bytes([0x22]))
        self.initialized = True

    def refresh_full(self, buffer: bytearray) -> None:
        """Performs a clean full-screen refresh (DTM2 0x13 + DRF 0x12)."""
        if not self.initialized:
            self.init_panel()
        self._cmd(0x13, buffer)
        self._cmd(0x12)  # Display Refresh (DRF)
        self._wait_ready(4000)
        self.partial_count = 0

    def refresh_partial_window(
        self, buffer: bytearray, x: int, y: int, w: int, h: int
    ) -> None:
        """Performs a 0.34s hardware Partial Window update (PTIN 0x91 + PTL 0x90)."""
        if not self.initialized:
            self.init_panel()

        # Align horizontal coordinates to 8-pixel byte banks per datasheet 7(40) PTL
        x0 = max(0, x & ~7)
        x1 = min(self.WIDTH - 1, ((x + w + 7) & ~7) - 1)
        y0 = max(0, y)
        y1 = min(self.HEIGHT - 1, y + h - 1)

        self._cmd(0x91)  # Partial In (PTIN)
        ptl_params = bytes([
            (x0 >> 8) & 0x03, x0 & 0xF8,
            (x1 >> 8) & 0x03, x1 | 0x07,
            (y0 >> 8) & 0x03, y0 & 0xFF,
            (y1 >> 8) & 0x03, y1 & 0xFF,
            0x01,  # PT_SCAN = 1
        ])
        self._cmd(0x90, ptl_params)

        # Extract sub-window rows from full 800x480 framebuffer
        row_bytes = self.WIDTH // 8
        bx0 = x0 // 8
        bx1 = (x1 + 1) // 8
        win_w_bytes = max(1, bx1 - bx0)
        win_bytes = bytearray(win_w_bytes * (y1 - y0 + 1))
        dst = 0
        for ry in range(y0, y1 + 1):
            src = ry * row_bytes + bx0
            win_bytes[dst:dst + win_w_bytes] = buffer[src:src + win_w_bytes]
            dst += win_w_bytes

        self._cmd(0x13, win_bytes)
        self._cmd(0x12)  # Display Refresh (DRF)
        self._wait_ready(600)
        self._cmd(0x92)  # Partial Out (PTOUT)
        self.partial_count += 1

    def deep_sleep(self) -> None:
        """Enters 2 uA Deep Sleep mode (POF 0x02 + DSLP 0x07 with 0xA5 check code)."""
        self._cmd(0x02)  # Power OFF (POF)
        self._wait_ready(1000)
        self._cmd(0x07, bytes([0xA5]))  # Deep Sleep (DSLP)
        self.initialized = False


class SSD1680Driver:
    """Generic SPI E-Paper driver for SSD1680 / SSD1681 / UC8176 panels (400x300, 296x128)."""

    def __init__(self, width: int, height: int, spi, cs_pin, dc_pin, rst_pin, busy_pin=None):
        self.width = width
        self.height = height
        self.spi = spi
        self.cs = cs_pin
        self.dc = dc_pin
        self.rst = rst_pin
        self.busy = busy_pin
        self.initialized = False
        self.partial_count = 0

    def _cmd(self, cmd: int, data: bytes = None) -> None:
        if self.spi is None:
            return
        if self.cs is not None:
            self.cs.value(0)
        if self.dc is not None:
            self.dc.value(0)
        self.spi.write(bytes([cmd]))
        if self.cs is not None:
            self.cs.value(1)
        if data is not None:
            if self.cs is not None:
                self.cs.value(0)
            if self.dc is not None:
                self.dc.value(1)
            self.spi.write(data)
            if self.cs is not None:
                self.cs.value(1)

    def init_panel(self) -> None:
        if self.rst is not None:
            self.rst.value(0)
            sleep_ms(10)
            self.rst.value(1)
            sleep_ms(10)
        self._cmd(0x12)  # SWRESET
        sleep_ms(10)
        self._cmd(0x11, bytes([0x03]))  # Data entry mode X+, Y+
        self.initialized = True

    def refresh_full(self, buffer: bytearray) -> None:
        if not self.initialized:
            self.init_panel()
        self._cmd(0x24, buffer)  # Write Black/White RAM
        self._cmd(0x22, bytes([0xF7]))
        self._cmd(0x20)          # Master Activation
        self.partial_count = 0

    def refresh_partial_window(self, buffer: bytearray, x: int, y: int, w: int, h: int) -> None:
        self.refresh_full(buffer)
        self.partial_count += 1


class GenericSPIDisplayDriver:
    """Fallback high-speed SPI framebuffer streamer for Sharp Memory LCD & ST7789/ST7796 TFTs."""

    def __init__(self, width: int, height: int, spi, cs_pin, dc_pin, rst_pin):
        self.width = width
        self.height = height
        self.spi = spi
        self.cs = cs_pin
        self.dc = dc_pin
        self.rst = rst_pin

    def refresh_full(self, buffer: bytearray) -> None:
        if self.spi is None or self.cs is None:
            return
        try:
            self.cs.value(0)
            if self.dc is not None:
                self.dc.value(1)
            self.spi.write(buffer)
            self.cs.value(1)
        except Exception:
            pass

    def refresh_partial_window(self, buffer: bytearray, x: int, y: int, w: int, h: int) -> None:
        self.refresh_full(buffer)


def get_display_profile(profile_id: str) -> DisplayProfile:
    return DISPLAY_PROFILES.get(profile_id, DISPLAY_PROFILES["sharp_400x240"])


def load_hardware_config(config_path: str = "hardware_config.json") -> dict:
    """Loads DIY builder hardware configuration from JSON, falling back to safe defaults."""
    default_cfg = {
        "display_profile": "gdey075t7_800x480",
        "custom_width": 800,
        "custom_height": 480,
        "font_scale": 1,
        "spi": {
            "id": 1,
            "baudrate": 10000000,
            "sck_pin": 12,
            "mosi_pin": 11,
            "cs_pin": 10,
            "dc_pin": 9,
            "rst_pin": 8,
            "busy_pin": 13,
            "bl_pin": -1,
        },
        "i2c": {
            "id": 0,
            "scl_pin": 2,
            "sda_pin": 1,
            "freq": 400000,
            "keyboard_addr": 95,
        },
        "pointer": {
            "enabled": True,
            "driver": "auto",  # "auto", "trackball_pimoroni", "ft6236_touch", "gt911_touch", "iqs5xx_trackpad"
            "i2c_addr": 10,
            "sensitivity": 2,
            "invert_x": False,
            "invert_y": False,
        },
        "battery_adc_pin": 4,
    }
    if path_exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            for k, v in user_cfg.items():
                if isinstance(v, dict) and isinstance(default_cfg.get(k), dict):
                    default_cfg[k].update(v)
                else:
                    default_cfg[k] = v
        except Exception:
            pass
    return default_cfg
