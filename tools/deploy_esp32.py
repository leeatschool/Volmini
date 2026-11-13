"""ESP32 Deployment Helper for Volmini.

Uploads `boot.py`, `main.py`, `volmini/`, and `data/` to an attached ESP32-S3
running MicroPython using `mpremote`.

Usage:
    python tools/deploy_esp32.py [PORT]
"""

import subprocess
import sys


def deploy(port: str = None) -> int:
    base_cmd = [sys.executable, "-m", "mpremote"]
    if port:
        base_cmd.extend(["connect", port])

    commands = [
        base_cmd + ["fs", "cp", "boot.py", ":boot.py"],
        base_cmd + ["fs", "cp", "main.py", ":main.py"],
        base_cmd + ["fs", "cp", "hardware_config.json", ":hardware_config.json"],
        base_cmd + ["fs", "cp", "-r", "volmini", ":"],
        base_cmd + ["fs", "cp", "-r", "data", ":"],
        base_cmd + ["reset"],
    ]

    for cmd in commands:
        print("Running:", " ".join(cmd))
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("Error: mpremote command failed. Ensure `pip install mpremote` and ESP32 is connected.")
            return res.returncode

    print("[OK] Volmini deployed to ESP32 successfully!")
    return 0


if __name__ == "__main__":
    port_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(deploy(port_arg))
