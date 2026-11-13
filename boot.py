"""ESP32-S3 MicroPython Boot Configuration for Volmini.

Runs automatically on power-on before `main.py`:
1. Sets ESP32-S3 CPU frequency to 240 MHz for crisp pagination and zero-lag typing.
2. Strictly turns OFF Wi-Fi (STA & AP) and Bluetooth Low Energy (BLE) radios.
3. Configures garbage collection thresholds.
"""

import gc

try:
    import machine
    machine.freq(240_000_000)
except Exception:
    pass

# Strictly disable Wi-Fi on boot
try:
    import network
    for _iface in (network.STA_IF, network.AP_IF):
        _wlan = network.WLAN(_iface)
        _wlan.active(False)
except Exception:
    pass

# Strictly disable BLE on boot (only enabled on-demand inside BLE Beam modal)
try:
    import bluetooth
    _ble = bluetooth.BLE()
    _ble.active(False)
except Exception:
    pass

gc.collect()
if hasattr(gc, "threshold"):
    try:
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
    except Exception:
        pass
