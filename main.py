"""Main ESP32 MicroPython Entry Point for Volmini.

Initializes the Hardware Abstraction Layer (ESP32HAL on hardware, DesktopHAL on PC),
displays the Initiating Boot Splash Screen (`V|`), restores the last manuscript session,
and enters the low-power event loop.
"""

from volmini.compat import IS_MICROPYTHON, sleep_ms
from volmini.ui.app import VolminiApp


def main():
    if IS_MICROPYTHON:
        from volmini.hal.hal_esp32 import ESP32HAL
        hal = ESP32HAL(width=400, height=240)
    else:
        from volmini.hal.hal_desktop import DesktopHAL
        hal = DesktopHAL(width=400, height=240)

    app = VolminiApp(hal)
    app.run_boot_sequence(interactive_wait=False)

    if IS_MICROPYTHON:
        while True:
            app.tick()
            sleep_ms(15)


if __name__ == "__main__":
    main()
