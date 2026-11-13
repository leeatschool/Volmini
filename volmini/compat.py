"""MicroPython and CPython compatibility layer for Volmini.

Provides:
- Monotonic millisecond timing (ticks_ms, ticks_diff, sleep_ms)
- Memory telemetry and garbage collection helpers (gc_collect, mem_free_bytes)
- FrameBuffer implementation matching MicroPython's built-in `framebuf` module
  so identical rendering code runs on ESP32 hardware and desktop Python tests/simulator.
"""

import gc
import os
import sys
import time

IS_MICROPYTHON = getattr(sys, "implementation", None) and sys.implementation.name == "micropython"

# --- Timing Shims ---
if hasattr(time, "ticks_ms"):
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    sleep_ms = time.sleep_ms
else:
    def ticks_ms() -> int:
        return int(time.monotonic() * 1000)

    def ticks_diff(t1: int, t2: int) -> int:
        return t1 - t2

    def sleep_ms(ms: int) -> None:
        time.sleep(ms / 1000.0)


# --- Memory Shims ---
def gc_collect() -> None:
    gc.collect()


def mem_free_bytes() -> int:
    if hasattr(gc, "mem_free"):
        return gc.mem_free()
    # CPython simulated ESP32-S3 PSRAM free estimate
    return 4 * 1024 * 1024


def makedirs_safe(path: str) -> None:
    """Recursively creates directories on both MicroPython os.mkdir and CPython."""
    if not path:
        return
    norm = path.replace("\\", "/").rstrip("/")
    if not norm:
        return
    parts = norm.split("/")
    curr = ""
    for i, part in enumerate(parts):
        if i == 0 and (part.endswith(":") or part == ""):
            curr = part
            continue
        curr = f"{curr}/{part}" if curr else (f"/{part}" if norm.startswith("/") else part)
        try:
            os.stat(curr)
        except OSError:
            try:
                os.mkdir(curr)
            except OSError:
                pass


def path_exists(path: str) -> bool:
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def is_dir(path: str) -> bool:
    try:
        mode = os.stat(path)[0]
        return bool(mode & 0x4000)
    except OSError:
        return False


def file_size(path: str) -> int:
    try:
        return os.stat(path)[6]
    except OSError:
        return 0


# --- FrameBuffer Shims ---
try:
    import framebuf as _mp_framebuf
    MONO_HLSB = _mp_framebuf.MONO_HLSB
    MONO_VLSB = _mp_framebuf.MONO_VLSB
    RGB565 = _mp_framebuf.RGB565
    FrameBuffer = _mp_framebuf.FrameBuffer
except ImportError:
    MONO_HLSB = 0
    MONO_VLSB = 1
    RGB565 = 2

    # Built-in 8x8 ASCII bitmap font fallback for FrameBuffer.text()
    class FrameBuffer:
        """Pure-Python implementation of MicroPython's framebuf.FrameBuffer (MONO_HLSB & RGB565)."""

        def __init__(self, buffer: bytearray, width: int, height: int, fmt: int = MONO_HLSB, stride: int = -1):
            self.buffer = buffer
            self.width = int(width)
            self.height = int(height)
            self.format = fmt
            self.stride = self.width if stride < 0 else int(stride)
            self._row_bytes = (self.stride + 7) // 8 if fmt == MONO_HLSB else self.stride * 2

        def fill(self, c: int) -> None:
            if self.format == MONO_HLSB:
                val = 0xFF if c else 0x00
                for i in range(len(self.buffer)):
                    self.buffer[i] = val
            else:
                lo = c & 0xFF
                hi = (c >> 8) & 0xFF
                for i in range(0, len(self.buffer), 2):
                    self.buffer[i] = lo
                    self.buffer[i + 1] = hi

        def pixel(self, x: int, y: int, c: int = None):
            if not (0 <= x < self.width and 0 <= y < self.height):
                return 0
            if self.format == MONO_HLSB:
                byte_idx = y * self._row_bytes + (x >> 3)
                bit_mask = 0x80 >> (x & 7)
                if c is None:
                    return 1 if (self.buffer[byte_idx] & bit_mask) else 0
                if c:
                    self.buffer[byte_idx] |= bit_mask
                else:
                    self.buffer[byte_idx] &= ~bit_mask
            else:
                idx = (y * self.stride + x) * 2
                if c is None:
                    return self.buffer[idx] | (self.buffer[idx + 1] << 8)
                self.buffer[idx] = c & 0xFF
                self.buffer[idx + 1] = (c >> 8) & 0xFF

        def hline(self, x: int, y: int, w: int, c: int) -> None:
            if y < 0 or y >= self.height or w <= 0:
                return
            x0 = max(0, x)
            x1 = min(self.width, x + w)
            for px in range(x0, x1):
                self.pixel(px, y, c)

        def vline(self, x: int, y: int, h: int, c: int) -> None:
            if x < 0 or x >= self.width or h <= 0:
                return
            y0 = max(0, y)
            y1 = min(self.height, y + h)
            for py in range(y0, y1):
                self.pixel(x, py, c)

        def line(self, x0: int, y0: int, x1: int, y1: int, c: int) -> None:
            dx = abs(x1 - x0)
            sx = 1 if x0 < x1 else -1
            dy = -abs(y1 - y0)
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                self.pixel(x0, y0, c)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy

        def rect(self, x: int, y: int, w: int, h: int, c: int) -> None:
            if w <= 0 or h <= 0:
                return
            self.hline(x, y, w, c)
            self.hline(x, y + h - 1, w, c)
            self.vline(x, y, h, c)
            self.vline(x + w - 1, y, h, c)

        def fill_rect(self, x: int, y: int, w: int, h: int, c: int) -> None:
            if w <= 0 or h <= 0:
                return
            y0 = max(0, y)
            y1 = min(self.height, y + h)
            x0 = max(0, x)
            x1 = min(self.width, x + w)
            if x1 <= x0:
                return
            for py in range(y0, y1):
                for px in range(x0, x1):
                    self.pixel(px, py, c)

        def blit(self, fbuf: "FrameBuffer", x: int, y: int, key: int = -1, palette=None) -> None:
            for sy in range(fbuf.height):
                dy = y + sy
                if dy < 0 or dy >= self.height:
                    continue
                for sx in range(fbuf.width):
                    dx = x + sx
                    if dx < 0 or dx >= self.width:
                        continue
                    col = fbuf.pixel(sx, sy)
                    if col != key:
                        self.pixel(dx, dy, col)
