"""Dual-Mode On-Demand Bluetooth Low Energy (BLE) Beam to Phone for Volmini.

Modes:
1. BLE UART (Nordic UART Service - NUS): Streams framed manuscript chunks (.md / .txt)
   to any BLE Serial / Web-Bluetooth phone app.
2. BLE HID Keyboard Auto-Type: Acts as a standard Bluetooth keyboard and types the
   manuscript directly into an open Notes/Docs app on iOS/Android with zero app install.

Security & Power Guarantee:
- Wi-Fi is never enabled.
- BLE radio (`bluetooth.BLE()`) stays strictly OFF (`active(False)`) during all normal
  operation and powers down immediately after beaming completes or is cancelled.
"""

from volmini.core.io_manager import _crc32
from volmini.compat import sleep_ms


# Standard USB/BLE HID Keyboard scan codes for ASCII 32..126
# Format: char -> (modifier_byte, hid_keycode) where 0x02 = Left Shift
_HID_ASCII_MAP = {
    "\n": (0x00, 0x28),
    "\t": (0x00, 0x2B),
    " ": (0x00, 0x2C),
    "-": (0x00, 0x2D), "_": (0x02, 0x2D),
    "=": (0x00, 0x2E), "+": (0x02, 0x2E),
    "[": (0x00, 0x2F), "{": (0x02, 0x2F),
    "]": (0x00, 0x30), "}": (0x02, 0x30),
    "\\": (0x00, 0x31), "|": (0x02, 0x31),
    ";": (0x00, 0x33), ":": (0x02, 0x33),
    "'": (0x00, 0x34), '"': (0x02, 0x34),
    "`": (0x00, 0x35), "~": (0x02, 0x35),
    ",": (0x00, 0x36), "<": (0x02, 0x36),
    ".": (0x00, 0x37), ">": (0x02, 0x37),
    "/": (0x00, 0x38), "?": (0x02, 0x38),
    "1": (0x00, 0x1E), "!": (0x02, 0x1E),
    "2": (0x00, 0x1F), "@": (0x02, 0x1F),
    "3": (0x00, 0x20), "#": (0x02, 0x20),
    "4": (0x00, 0x21), "$": (0x02, 0x21),
    "5": (0x00, 0x22), "%": (0x02, 0x22),
    "6": (0x00, 0x23), "^": (0x02, 0x23),
    "7": (0x00, 0x24), "&": (0x02, 0x24),
    "8": (0x00, 0x25), "*": (0x02, 0x25),
    "9": (0x00, 0x26), "(": (0x02, 0x26),
    "0": (0x00, 0x27), ")": (0x02, 0x27),
}
for _i in range(26):
    _ch_lo = chr(ord("a") + _i)
    _ch_hi = chr(ord("A") + _i)
    _HID_ASCII_MAP[_ch_lo] = (0x00, 0x04 + _i)
    _HID_ASCII_MAP[_ch_hi] = (0x02, 0x04 + _i)


class BLEBeamMode:
    NUS_UART = "nus_uart"
    HID_AUTOTYPE = "hid_autotype"


class BLEBeamEngine:
    """Manages on-demand BLE UART file streaming and BLE HID Auto-Type beaming."""

    CHUNK_SIZE = 180  # Safe BLE GATT notification chunk size

    def __init__(self, device_name: str = "Volmini-Codex"):
        self.device_name = device_name
        self.radio_active = False
        self.connected = False
        self.mode = BLEBeamMode.NUS_UART
        self.status_message = "BLE Radio OFF (Secure Standby)"
        self.progress_pct = 0
        self._ble = None
        self._conn_handle = None
        self._tx_handle = None
        self._transmitted_packets = []  # Recorded in simulator/test mode

    def start_advertising(self, mode: str = BLEBeamMode.NUS_UART) -> bool:
        """Powers on the BLE peripheral only when explicitly requested by the user."""
        self.mode = mode
        self.progress_pct = 0
        self._transmitted_packets.clear()

        try:
            import bluetooth
            self._ble = bluetooth.BLE()
            self._ble.active(True)
            self.radio_active = True

            if mode == BLEBeamMode.NUS_UART:
                nus_uuid = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
                rx_uuid = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
                tx_uuid = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
                nus_service = (
                    nus_uuid,
                    (
                        (tx_uuid, bluetooth.FLAG_NOTIFY),
                        (rx_uuid, bluetooth.FLAG_WRITE),
                    ),
                )
                ((self._tx_handle, _),) = self._ble.gatts_register_services((nus_service,))
            else:
                hid_uuid = bluetooth.UUID(0x1812)
                rep_uuid = bluetooth.UUID(0x2A4D)
                hid_service = (
                    hid_uuid,
                    ((rep_uuid, bluetooth.FLAG_NOTIFY | bluetooth.FLAG_READ),),
                )
                ((self._tx_handle,),) = self._ble.gatts_register_services((hid_service,))

            self._ble.irq(self._ble_irq)
            adv_payload = self._build_adv_payload(self.device_name)
            self._ble.gap_advertise(100_000, adv_data=adv_payload)
            self.status_message = f"Advertising as '{self.device_name}' ({mode})..."
            return True
        except ImportError:
            # Desktop Simulator / CPython fallback
            self.radio_active = True
            self.connected = True
            self.status_message = f"[Sim] Ready to beam as '{self.device_name}' ({mode})"
            return True
        except Exception as e:
            self.stop_radio()
            self.status_message = f"BLE Init Error: {e}"
            return False

    def _ble_irq(self, event, data) -> None:
        # _IRQ_CENTRAL_CONNECT = 1, _IRQ_CENTRAL_DISCONNECT = 2
        if event == 1:
            self._conn_handle = data[0]
            self.connected = True
            self.status_message = "Phone Connected! Press ENTER to Beam."
        elif event == 2:
            self._conn_handle = None
            self.connected = False
            self.status_message = "Phone Disconnected."

    @staticmethod
    def _build_adv_payload(name: str) -> bytes:
        name_bytes = name.encode("utf-8")[:18]
        # Flags (LE General Discoverable + BR/EDR Not Supported) + Complete Local Name
        return bytes([2, 0x01, 0x06, len(name_bytes) + 1, 0x09]) + name_bytes

    @classmethod
    def build_nus_frames(cls, filename: str, content: str) -> list:
        """Slices document content into framed BLE UART packets with CRC32 integrity verification."""
        raw = content.encode("utf-8")
        crc = _crc32(raw)
        header = f"---VOLMINI:BEGIN:{filename}:{len(raw)}:{crc:08x}---\n".encode("utf-8")
        footer = f"\n---VOLMINI:END:{crc:08x}---\n".encode("utf-8")

        frames = [header]
        for i in range(0, len(raw), cls.CHUNK_SIZE):
            frames.append(raw[i:i + cls.CHUNK_SIZE])
        frames.append(footer)
        return frames

    @staticmethod
    def ascii_to_hid_reports(content: str) -> list:
        """Converts text into 8-byte standard BLE HID keyboard press/release report pairs."""
        reports = []
        for ch in content:
            mod, keycode = _HID_ASCII_MAP.get(ch, (0x00, 0x00))
            if keycode == 0x00 and ch != "\r":
                # Replace unsupported unicode glyph with '?' or '-'
                mod, keycode = _HID_ASCII_MAP["-"]
            if keycode != 0x00:
                # 8-byte boot keyboard report: [modifier, reserved, key1, 0, 0, 0, 0, 0]
                reports.append(bytes([mod, 0x00, keycode, 0, 0, 0, 0, 0]))
                reports.append(bytes([0x00, 0x00, 0x00, 0, 0, 0, 0, 0]))  # key release
        return reports

    def beam_document(self, filename: str, content: str, step_callback=None) -> bool:
        """Streams the manuscript using the active BLE mode, then immediately powers off BLE."""
        if not self.radio_active:
            self.start_advertising(self.mode)

        try:
            if self.mode == BLEBeamMode.NUS_UART:
                frames = self.build_nus_frames(filename, content)
                total = max(1, len(frames))
                for idx, frame in enumerate(frames):
                    self._send_gatt_notify(frame)
                    self.progress_pct = int(((idx + 1) * 100) // total)
                    self.status_message = f"Beaming UART chunk {idx + 1}/{total} ({self.progress_pct}%)..."
                    if step_callback:
                        step_callback(self.progress_pct, self.status_message)
                    if self._ble is not None:
                        sleep_ms(12)
            else:
                reports = self.ascii_to_hid_reports(content)
                total = max(1, len(reports))
                for idx, rep in enumerate(reports):
                    self._send_gatt_notify(rep)
                    if (idx & 7) == 0 or idx == total - 1:
                        self.progress_pct = int(((idx + 1) * 100) // total)
                        self.status_message = f"Auto-typing HID {self.progress_pct}%..."
                        if step_callback:
                            step_callback(self.progress_pct, self.status_message)
                    if self._ble is not None:
                        sleep_ms(8)

            self.progress_pct = 100
            self.stop_radio()
            self.status_message = "Beam complete! BLE Radio turned OFF."
            return True
        except Exception as e:
            self.stop_radio()
            self.status_message = f"Beam failed ({e}). BLE Radio OFF."
            return False

    def _send_gatt_notify(self, payload: bytes) -> None:
        self._transmitted_packets.append(payload)
        if self._ble is not None and self._conn_handle is not None and self._tx_handle is not None:
            self._ble.gatts_notify(self._conn_handle, self._tx_handle, payload)

    def stop_radio(self) -> None:
        """Immediately shuts down BLE advertising and powers off the Bluetooth peripheral."""
        if self._ble is not None:
            try:
                self._ble.gap_advertise(None)
            except Exception:
                pass
            try:
                self._ble.active(False)
            except Exception:
                pass
        self._ble = None
        self._conn_handle = None
        self._tx_handle = None
        self.connected = False
        self.radio_active = False
        self.status_message = "BLE Radio OFF (Secure Standby)"
