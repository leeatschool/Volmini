"""ESP32-S3 Hardware Abstraction Layer (MicroPython).

Supports:
- Multi-Display SPI Drivers configured via `hardware_config.json`:
  - Good Display GDEY075T7 7.5" 800x480 E-Paper (UC8179, full + 0.34s partial window refresh)
  - SSD1680 / UC8176 E-Paper modules (400x300, 296x128)
  - Sharp Memory LCD (400x240, 60Hz 1-bit)
  - ST7796 / ST7789 / ILI9341 SPI TFT LCDs (480x320, 320x240)
- SD Card mounting (/sd) with seamless fallback to internal Flash (/documents)
- I2C Keyboard (CardKB / TCA8418 / BBQ10) and UART/USB-CDC fallback
- I2C Pointer / Touchpad / Trackball / Capacitive Touch (Pimoroni Trackball, FT6236, GT911, Azoteq IQS5xx)
- Battery voltage ADC reading
- Strict RF lockdown on boot (Wi-Fi and BLE radios disabled by default)
"""

import os
from volmini.hal.base import VolminiHAL, KeyEvent, KeyCode, PointerEvent
from volmini.hal.displays import (
    DISPLAY_PROFILES, DisplayProfile, GDEY075T7Driver, SSD1680Driver,
    GenericSPIDisplayDriver, load_hardware_config
)
from volmini.hal.touchpad5 import Touchpad5ClickDriver
from volmini.hal.usb_hid_kb import USBHIDKeyboardDecoder
from volmini.compat import makedirs_safe


class ESP32HAL(VolminiHAL):
    """Hardware driver layer for ESP32-S3 running standalone MicroPython."""

    def __init__(
        self,
        width: int = None,
        height: int = None,
        display_profile: str = None,
        config_path: str = "hardware_config.json",
    ):
        self.hw_config = load_hardware_config(config_path)
        prof_id = display_profile or self.hw_config.get("display_profile", "gdey075t7_800x480")

        if prof_id in DISPLAY_PROFILES:
            prof = DISPLAY_PROFILES[prof_id]
        else:
            cw = width or int(self.hw_config.get("custom_width", 400))
            ch = height or int(self.hw_config.get("custom_height", 240))
            prof = DisplayProfile(
                profile_id="custom",
                name=f"Custom DIY Display ({cw}x{ch})",
                width=cw,
                height=ch,
                tech="memory_lcd",
                controller="generic",
                font_scale=int(self.hw_config.get("font_scale", 1)),
            )

        if width is not None and height is not None:
            prof = DisplayProfile(
                profile_id=prof.profile_id,
                name=prof.name,
                width=width,
                height=height,
                tech=prof.tech,
                controller=prof.controller,
                font_scale=prof.font_scale,
                partial_refresh_ms=prof.partial_refresh_ms,
                full_refresh_every=prof.full_refresh_every,
            )

        super().__init__(display_profile=prof)
        self._spi = None
        self._cs = None
        self._dc = None
        self._rst = None
        self._busy = None
        self._bl = None
        self._i2c = None
        self._display_driver = None
        self._touchpad5 = None
        self._uart_kb = None
        self._hid_decoder = USBHIDKeyboardDecoder()
        self._kb_addr = int(self.hw_config.get("i2c", {}).get("keyboard_addr", 0x5F))
        self._pointer_cfg = self.hw_config.get("pointer", {})
        self._prev_pointer_btn = False
        self._bat_adc = None
        self._key_queue = []

        self._lockdown_radios()
        self._init_storage()
        self._init_peripherals()

    def _lockdown_radios(self) -> None:
        """Strictly disables Wi-Fi and BLE on boot for security and battery life."""
        try:
            import network
            for iface_id in (network.STA_IF, network.AP_IF):
                wlan = network.WLAN(iface_id)
                wlan.active(False)
        except Exception:
            pass
        try:
            import bluetooth
            ble = bluetooth.BLE()
            ble.active(False)
        except Exception:
            pass

    def _init_storage(self) -> None:
        """Attempts to mount SPI MicroSD card at /sd; falls back to /documents on internal flash."""
        self.sd_mounted = False
        sd_cfg = self.hw_config.get("sdcard", {})
        if sd_cfg.get("enabled", True):
            try:
                import machine
                from machine import Pin
                sd = machine.SDCard(
                    slot=int(sd_cfg.get("slot", 2)),
                    sck=Pin(int(sd_cfg.get("sck_pin", 15))),
                    mosi=Pin(int(sd_cfg.get("mosi_pin", 16))),
                    miso=Pin(int(sd_cfg.get("miso_pin", 7))),
                    cs=Pin(int(sd_cfg.get("cs_pin", 5))),
                )
                os.mount(sd, "/sd")
                self.sd_mounted = True
                self.storage_root = "/sd/volmini"
            except Exception:
                self.storage_root = "/documents"
        else:
            self.storage_root = "/documents"
        makedirs_safe(self.storage_root)

    def _init_peripherals(self) -> None:
        spi_cfg = self.hw_config.get("spi", {})
        i2c_cfg = self.hw_config.get("i2c", {})
        bat_pin = int(self.hw_config.get("battery_adc_pin", 4))

        try:
            from machine import Pin, SPI, I2C, ADC
            self._cs = Pin(int(spi_cfg.get("cs_pin", 10)), Pin.OUT, value=1)
            self._dc = Pin(int(spi_cfg.get("dc_pin", 9)), Pin.OUT, value=0)
            self._rst = Pin(int(spi_cfg.get("rst_pin", 8)), Pin.OUT, value=1)
            busy_pin_no = int(spi_cfg.get("busy_pin", 13))
            if busy_pin_no >= 0:
                self._busy = Pin(busy_pin_no, Pin.IN)
            bl_pin_no = int(spi_cfg.get("bl_pin", -1))
            if bl_pin_no >= 0:
                self._bl = Pin(bl_pin_no, Pin.OUT, value=1)

            self._spi = SPI(
                int(spi_cfg.get("id", 1)),
                baudrate=int(spi_cfg.get("baudrate", 10_000_000)),
                polarity=0,
                phase=0,
                sck=Pin(int(spi_cfg.get("sck_pin", 12))),
                mosi=Pin(int(spi_cfg.get("mosi_pin", 11))),
            )
            self._i2c = I2C(
                int(i2c_cfg.get("id", 0)),
                scl=Pin(int(i2c_cfg.get("scl_pin", 2))),
                sda=Pin(int(i2c_cfg.get("sda_pin", 1))),
                freq=int(i2c_cfg.get("freq", 400_000)),
            )
            if bat_pin >= 0:
                self._bat_adc = ADC(Pin(bat_pin))
                if hasattr(self._bat_adc, "atten"):
                    self._bat_adc.atten(ADC.ATTN_11DB)
        except Exception:
            # Graceful fallback when running in environments without physical pins attached
            pass

        # Bind appropriate display controller driver
        ctrl = self.display_profile.controller.upper()
        if ctrl == "UC8179":
            self._display_driver = GDEY075T7Driver(
                self._spi, self._cs, self._dc, self._rst, self._busy
            )
        elif ctrl in ("SSD1680", "UC8176"):
            self._display_driver = SSD1680Driver(
                self.width, self.height, self._spi, self._cs, self._dc, self._rst, self._busy
            )
        else:
            self._display_driver = GenericSPIDisplayDriver(
                self.width, self.height, self._spi, self._cs, self._dc, self._rst
            )

        # Initialize MIKROE Touchpad 5 Click (Azoteq IQS550 @ 0x74) driver
        tp_rdy_pin = None
        tp_rst_pin = None
        try:
            from machine import Pin
            rdy_no = int(self._pointer_cfg.get("rdy_pin", 14))
            rst_no = int(self._pointer_cfg.get("rst_pin", -1))
            if rdy_no >= 0:
                tp_rdy_pin = Pin(rdy_no, Pin.IN)
            if rst_no >= 0:
                tp_rst_pin = Pin(rst_no, Pin.OUT, value=1)
        except Exception:
            pass

        self._touchpad5 = Touchpad5ClickDriver(
            i2c=self._i2c,
            addr=int(self._pointer_cfg.get("touchpad5_addr", 0x74)),
            rdy_pin=tp_rdy_pin,
            rst_pin=tp_rst_pin,
            sensitivity=int(self._pointer_cfg.get("sensitivity", 1)),
            invert_x=bool(self._pointer_cfg.get("invert_x", False)),
            invert_y=bool(self._pointer_cfg.get("invert_y", False)),
        )

        # Optional UART USB-Host Bridge (CH9350L / CH559 / QMK UART 60% Keyboard)
        kb_cfg = self.hw_config.get("keyboard", {})
        try:
            from machine import UART, Pin
            uart_rx = int(kb_cfg.get("uart_rx_pin", 18))
            uart_tx = int(kb_cfg.get("uart_tx_pin", 17))
            if uart_rx >= 0:
                self._uart_kb = UART(
                    int(kb_cfg.get("uart_id", 1)),
                    baudrate=int(kb_cfg.get("uart_baudrate", 115200)),
                    rx=Pin(uart_rx),
                    tx=Pin(uart_tx) if uart_tx >= 0 else None,
                )
        except Exception:
            pass

    def push_key_event(self, event: KeyEvent) -> None:
        self._key_queue.append(event)

    def poll_key(self):
        if self._key_queue:
            return self._key_queue.pop(0)

        # 1. Poll UART USB-Host Keyboard Bridge (CH9350L 8-byte HID or ANSI UART 60% keyboard)
        if self._uart_kb is not None:
            try:
                if self._uart_kb.any():
                    raw = self._uart_kb.read()
                    if raw:
                        kb_mode = self.hw_config.get("keyboard", {}).get("mode", "auto")
                        if kb_mode == "usb_hid_bridge" or (
                            kb_mode == "auto" and (
                                (len(raw) >= 11 and raw[0] == 0x57 and raw[1] == 0xAB)
                                or (len(raw) == 8 and raw[1] == 0x00)
                            )
                        ):
                            evs = self._hid_decoder.decode_hid_report(raw)
                        else:
                            evs = self._hid_decoder.decode_ansi_stream(raw)
                        if evs:
                            self._key_queue.extend(evs[1:])
                            return evs[0]
            except Exception:
                pass

        # 2. Poll I2C keyboard if attached
        if self._i2c is not None:
            try:
                data = self._i2c.readfrom(self._kb_addr, 1)
                if data and data[0] != 0:
                    return self._decode_raw_byte(data[0])
            except Exception:
                pass
        return None

    def poll_pointer(self):
        queued = super().poll_pointer()
        if queued is not None:
            return queued

        if self._i2c is None or not self._pointer_cfg.get("enabled", True):
            return None

        drv = self._pointer_cfg.get("driver", "auto")
        sens = max(1, int(self._pointer_cfg.get("sensitivity", 2)))

        # 1. MIKROE Touchpad 5 Click (Azoteq IQS550 @ 0x74)
        if drv in ("auto", "touchpad5_click", "iqs550") and self._touchpad5 is not None:
            res = self._touchpad5.poll(self.pointer_x, self.pointer_y, self.width, self.height)
            if res is not None:
                self.pointer_x, self.pointer_y, ev = res
                self.pointer_visible = True
                return ev

        # 2. Pimoroni I2C Trackball (0x0A: 5 bytes [left, right, up, down, switch])
        if drv in ("auto", "trackball_pimoroni"):
            try:
                tb_addr = int(self._pointer_cfg.get("i2c_addr", 0x0A))
                raw = self._i2c.readfrom_mem(tb_addr, 0x04, 5)
                if raw and len(raw) == 5:
                    left, right, up, down, sw = raw[0], raw[1], raw[2], raw[3], bool(raw[4] & 0x80)
                    dx = (right - left) * sens
                    dy = (down - up) * sens
                    clicked = sw and not self._prev_pointer_btn
                    self._prev_pointer_btn = sw
                    if dx != 0 or dy != 0 or clicked:
                        self.pointer_x = max(0, min(self.width - 1, self.pointer_x + dx))
                        self.pointer_y = max(0, min(self.height - 1, self.pointer_y + dy))
                        self.pointer_visible = True
                        return PointerEvent(self.pointer_x, self.pointer_y, clicked=clicked, pressed=sw)
            except Exception:
                pass

        # 2. FT6236 / FT6336 Capacitive Touch Panel (0x38)
        if drv in ("auto", "ft6236_touch"):
            try:
                td_stat = self._i2c.readfrom_mem(0x38, 0x02, 5)
                touches = td_stat[0] & 0x0F
                if touches > 0:
                    tx = ((td_stat[1] & 0x0F) << 8) | td_stat[2]
                    ty = ((td_stat[3] & 0x0F) << 8) | td_stat[4]
                    clicked = not self._prev_pointer_btn
                    self._prev_pointer_btn = True
                    self.pointer_x = max(0, min(self.width - 1, tx))
                    self.pointer_y = max(0, min(self.height - 1, ty))
                    self.pointer_visible = True
                    return PointerEvent(self.pointer_x, self.pointer_y, clicked=clicked, pressed=True)
                else:
                    self._prev_pointer_btn = False
            except Exception:
                pass

        return None

    def _decode_raw_byte(self, b: int) -> KeyEvent:
        """Maps raw I2C keyboard / CardKB scan codes to normalized KeyEvents."""
        if b == 0x0D or b == 0x0A:
            return KeyEvent(KeyCode.ENTER, "\n")
        if b == 0x08:
            return KeyEvent(KeyCode.BACKSPACE)
        if b == 0x1B:
            return KeyEvent(KeyCode.ESC)
        if b == 0x09:
            return KeyEvent(KeyCode.TAB, "\t")
        if b == 0xB5:
            return KeyEvent(KeyCode.UP)
        if b == 0xB6:
            return KeyEvent(KeyCode.DOWN)
        if b == 0xB4:
            return KeyEvent(KeyCode.LEFT)
        if b == 0xB7:
            return KeyEvent(KeyCode.RIGHT)
        # Function keys (0x81 - 0x88 on CardKB Fn+1..8)
        fn_map = {
            0x81: KeyCode.F1_HELP,
            0x82: KeyCode.F2_OUTLINE,
            0x83: KeyCode.F3_REFERENCE,
            0x84: KeyCode.F4_REVIEW,
            0x85: KeyCode.F5_CORVUS,
            0x86: KeyCode.F6_BLE_BEAM,
            0x87: KeyCode.F7_PAGE_SETUP,
            0x88: KeyCode.F8_RIBBON,
        }
        if b in fn_map:
            return KeyEvent(fn_map[b])
        if 1 <= b <= 26:
            letter = chr(ord("A") + b - 1)
            return KeyEvent(f"CTRL+{letter}", ctrl=True)
        if 32 <= b <= 126:
            ch = chr(b)
            return KeyEvent(ch, ch)
        return KeyEvent(KeyCode.NONE)

    def present(self) -> None:
        """Flushes the framebuffer to the configured display controller."""
        if self._display_driver is None:
            return
        max_partials = self.display_profile.full_refresh_every
        if (
            self.display_profile.is_epaper
            and hasattr(self._display_driver, "partial_count")
            and max_partials > 0
            and 0 < self._display_driver.partial_count < max_partials
        ):
            self._display_driver.refresh_partial_window(
                self.buffer, 0, 0, self.width, self.height
            )
        else:
            self._display_driver.refresh_full(self.buffer)

    def present_region(self, x: int, y: int, w: int, h: int) -> None:
        """Flushes a rectangular window using 0.34s hardware partial refresh on E-Paper."""
        if self._display_driver is None:
            return
        self._display_driver.refresh_partial_window(self.buffer, x, y, w, h)

    def battery_percent(self) -> int:
        if self._bat_adc is None:
            return 100
        try:
            uv = self._bat_adc.read_uv()
            v_bat = (uv / 1_000_000.0) * 2.0
            pct = int(round((v_bat - 3.3) / (4.2 - 3.3) * 100))
            return max(0, min(100, pct))
        except Exception:
            return 100
