"""Standard USB HID Boot Keyboard & UART/CH9350L Decoder for Volmini.

Enables any standard off-the-shelf 60% / 65% / Full-Size USB Keyboard to work with
Volmini via:
1. Standard 8-byte USB HID Boot Keyboard Reports (`[mod, 0x00, k1, k2, k3, k4, k5, k6]`)
   - Works with native USB Host or low-cost UART USB-Host bridge chips (e.g. CH9350L / CH559)
2. CH9350L framed UART packets (`0x57 0xAB ...`)
3. UART / Serial ASCII + ANSI VT100 escape sequences (`\\x1b[A`..`\\x1b[D` arrows, `\\x1bOP`.. F-keys)
4. 60% Keyboard Friendly Shortcuts:
   - Maps `Alt+1..8` (and `Ctrl+1..3`) so 60% keyboards without dedicated F1..F8 keys
     can trigger all Volmini studio overlays effortlessly.
"""

from volmini.hal.base import KeyCode, KeyEvent

# USB HID Modifier bitmasks (Byte 0 of 8-byte Boot Keyboard Report)
MOD_LCTRL = 0x01
MOD_LSHIFT = 0x02
MOD_LALT = 0x04
MOD_LGUI = 0x08
MOD_RCTRL = 0x10
MOD_RSHIFT = 0x20
MOD_RALT = 0x40
MOD_RGUI = 0x80

# USB HID Usage IDs (Keyboard/Keypad Page 0x07) -> (unshifted_char, shifted_char)
_HID_ASCII_MAP = {
    0x04: ("a", "A"), 0x05: ("b", "B"), 0x06: ("c", "C"), 0x07: ("d", "D"),
    0x08: ("e", "E"), 0x09: ("f", "F"), 0x0A: ("g", "G"), 0x0B: ("h", "H"),
    0x0C: ("i", "I"), 0x0D: ("j", "J"), 0x0E: ("k", "K"), 0x0F: ("l", "L"),
    0x10: ("m", "M"), 0x11: ("n", "N"), 0x12: ("o", "O"), 0x13: ("p", "P"),
    0x14: ("q", "Q"), 0x15: ("r", "R"), 0x16: ("s", "S"), 0x17: ("t", "T"),
    0x18: ("u", "U"), 0x19: ("v", "V"), 0x1A: ("w", "W"), 0x1B: ("x", "X"),
    0x1C: ("y", "Y"), 0x1D: ("z", "Z"),
    0x1E: ("1", "!"), 0x1F: ("2", "@"), 0x20: ("3", "#"), 0x21: ("4", "$"),
    0x22: ("5", "%"), 0x23: ("6", "^"), 0x24: ("7", "&"), 0x25: ("8", "*"),
    0x26: ("9", "("), 0x27: ("0", ")"),
    0x2C: (" ", " "),
    0x2D: ("-", "_"), 0x2E: ("=", "+"),
    0x2F: ("[", "{"), 0x30: ("]", "}"), 0x31: ("\\", "|"),
    0x33: (";", ":"), 0x34: ("'", '"'), 0x35: ("`", "~"),
    0x36: (",", "<"), 0x37: (".", ">"), 0x38: ("/", "?"),
}

_HID_SPECIAL_KEYS = {
    0x28: (KeyCode.ENTER, "\n"),
    0x29: (KeyCode.ESC, ""),
    0x2A: (KeyCode.BACKSPACE, ""),
    0x2B: (KeyCode.TAB, "\t"),
    0x4C: (KeyCode.DELETE, ""),
    0x4A: (KeyCode.HOME, ""),
    0x4D: (KeyCode.END, ""),
    0x4B: (KeyCode.PAGE_UP, ""),
    0x4E: (KeyCode.PAGE_DOWN, ""),
    0x4F: (KeyCode.RIGHT, ""),
    0x50: (KeyCode.LEFT, ""),
    0x51: (KeyCode.DOWN, ""),
    0x52: (KeyCode.UP, ""),
    0x3A: (KeyCode.F1_HELP, ""),
    0x3B: (KeyCode.F2_OUTLINE, ""),
    0x3C: (KeyCode.F3_REFERENCE, ""),
    0x3D: (KeyCode.F4_REVIEW, ""),
    0x3E: (KeyCode.F5_CORVUS, ""),
    0x3F: (KeyCode.F6_BLE_BEAM, ""),
    0x40: (KeyCode.F7_PAGE_SETUP, ""),
    0x41: (KeyCode.F8_RIBBON, ""),
}

# 60% Keyboard Alt+Number -> Function Key mapping (when physical F1..F8 row is absent)
_ALT_NUM_TO_FKEY = {
    "1": KeyCode.F1_HELP,
    "2": KeyCode.F2_OUTLINE,
    "3": KeyCode.F3_REFERENCE,
    "4": KeyCode.F4_REVIEW,
    "5": KeyCode.F5_CORVUS,
    "6": KeyCode.F6_BLE_BEAM,
    "7": KeyCode.F7_PAGE_SETUP,
    "8": KeyCode.F8_RIBBON,
}

# 60% Keyboard Alt+I/J/K/L -> Arrow Key navigation fallback (for 60% boards without arrow cluster)
_ALT_IJKL_TO_ARROW = {
    "I": KeyCode.UP,
    "K": KeyCode.DOWN,
    "J": KeyCode.LEFT,
    "L": KeyCode.RIGHT,
}


class USBHIDKeyboardDecoder:
    """Stateful decoder for 8-byte USB HID Boot Keyboard reports, CH9350L frames, and ANSI UART streams."""

    def __init__(self):
        self._prev_hid_keys = set()

    def decode_hid_report(self, report: bytes) -> list:
        """Decodes standard 8-byte USB HID reports or one/more 11-byte CH9350L UART frames (`0x57 0xAB 0x01 ...`)."""
        if not report:
            return []

        # If buffer starts with CH9350L preamble (0x57 0xAB), scan all frames in the UART burst
        if len(report) >= 11 and report[0] == 0x57 and report[1] == 0xAB:
            all_events = []
            idx = 0
            n = len(report)
            while idx + 11 <= n:
                if report[idx] == 0x57 and report[idx + 1] == 0xAB:
                    cmd = report[idx + 2]
                    # 0x01 (or 0x82/0x83 in State 1) = Keyboard report
                    if cmd in (0x01, 0x81, 0x82, 0x83):
                        all_events.extend(self._decode_single_8byte_hid(report[idx + 3 : idx + 11]))
                    idx += 11
                else:
                    idx += 1
            return all_events

        if len(report) < 8:
            return []
        return self._decode_single_8byte_hid(report[:8])

    def _decode_single_8byte_hid(self, report8: bytes) -> list:
        mod = report8[0]
        ctrl = bool(mod & (MOD_LCTRL | MOD_RCTRL))
        shift = bool(mod & (MOD_LSHIFT | MOD_RSHIFT))
        alt = bool(mod & (MOD_LALT | MOD_RALT))

        curr_keys = set()
        events = []

        for idx in range(2, 8):
            usage = report8[idx]
            if usage <= 0x03:  # 0x00 = No key, 0x01..0x03 = Rollover/Error
                continue
            curr_keys.add(usage)
            if usage not in self._prev_hid_keys:
                ev = self._usage_to_event(usage, ctrl=ctrl, shift=shift, alt=alt)
                if ev is not None:
                    events.append(ev)

        self._prev_hid_keys = curr_keys
        return events

    def _usage_to_event(self, usage: int, ctrl: bool, shift: bool, alt: bool) -> KeyEvent:
        if usage in _HID_SPECIAL_KEYS:
            k_code, k_char = _HID_SPECIAL_KEYS[usage]
            return KeyEvent(key=k_code, char=k_char, ctrl=ctrl, shift=shift, alt=alt)

        if usage in _HID_ASCII_MAP:
            unshifted, shifted = _HID_ASCII_MAP[usage]
            ch = shifted if shift else unshifted
            upper = unshifted.upper()

            # 60% Keyboard ergonomics: Alt+1..8 -> F1..F8, Alt+I/J/K/L -> Up/Left/Down/Right
            if alt and not ctrl:
                if unshifted in _ALT_NUM_TO_FKEY:
                    return KeyEvent(key=_ALT_NUM_TO_FKEY[unshifted], alt=True)
                if upper in _ALT_IJKL_TO_ARROW:
                    return KeyEvent(key=_ALT_IJKL_TO_ARROW[upper], alt=True)

            # Ctrl chords (Ctrl+A..Z, Ctrl+0..3)
            if ctrl:
                return KeyEvent(key=f"CTRL+{upper}", ctrl=True, shift=shift, alt=alt)

            return KeyEvent(key=ch, char=ch, ctrl=False, shift=shift, alt=alt)

        return None

    @staticmethod
    def decode_ansi_stream(buf: bytes) -> list:
        """Decodes UART / USB-CDC ASCII & ANSI escape sequences (arrows, F1..F8, Ctrl chords)."""
        events = []
        i = 0
        n = len(buf)
        while i < n:
            b = buf[i]
            # ANSI Escape sequence (\x1b[... or \x1bO...)
            if b == 0x1B:
                if i + 2 < n and buf[i + 1] == ord("["):
                    c2 = chr(buf[i + 2])
                    if c2 == "A":
                        events.append(KeyEvent(KeyCode.UP))
                        i += 3
                        continue
                    if c2 == "B":
                        events.append(KeyEvent(KeyCode.DOWN))
                        i += 3
                        continue
                    if c2 == "C":
                        events.append(KeyEvent(KeyCode.RIGHT))
                        i += 3
                        continue
                    if c2 == "D":
                        events.append(KeyEvent(KeyCode.LEFT))
                        i += 3
                        continue
                    if c2 == "H":
                        events.append(KeyEvent(KeyCode.HOME))
                        i += 3
                        continue
                    if c2 == "F":
                        events.append(KeyEvent(KeyCode.END))
                        i += 3
                        continue
                elif i + 2 < n and buf[i + 1] == ord("O"):
                    c2 = chr(buf[i + 2])
                    f_map = {
                        "P": KeyCode.F1_HELP,
                        "Q": KeyCode.F2_OUTLINE,
                        "R": KeyCode.F3_REFERENCE,
                        "S": KeyCode.F4_REVIEW,
                    }
                    if c2 in f_map:
                        events.append(KeyEvent(f_map[c2]))
                        i += 3
                        continue
                # Alt+1..8 sent as ESC + '1'..'8' on serial terminals
                elif i + 1 < n and chr(buf[i + 1]) in _ALT_NUM_TO_FKEY:
                    events.append(KeyEvent(_ALT_NUM_TO_FKEY[chr(buf[i + 1])], alt=True))
                    i += 2
                    continue
                events.append(KeyEvent(KeyCode.ESC))
                i += 1
                continue

            if b in (0x0D, 0x0A):
                events.append(KeyEvent(KeyCode.ENTER, "\n"))
            elif b in (0x08, 0x7F):
                events.append(KeyEvent(KeyCode.BACKSPACE))
            elif b == 0x09:
                events.append(KeyEvent(KeyCode.TAB, "\t"))
            elif 1 <= b <= 26:
                letter = chr(ord("A") + b - 1)
                events.append(KeyEvent(f"CTRL+{letter}", ctrl=True))
            elif 32 <= b <= 126:
                ch = chr(b)
                events.append(KeyEvent(ch, ch))
            i += 1
        return events
