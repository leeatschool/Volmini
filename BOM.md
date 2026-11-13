# Volmini — Official Bill of Materials (BOM) & Hardware Assembly Guide

This document specifies the official reference Bill of Materials (BOM), power distribution architecture, and pin-by-pin wiring guide for building a standalone **Volmini** ESP32-S3 writerdeck.

---

## 📦 Official Reference Bill of Materials (BOM)

| # | Subsystem | Official Selected Component | Qty | Purchase Link | Key Specs & Build Notes |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **1** | **Display** | **Good Display 7.5" 800×480 E-Paper (`GDEY075T7`, UC8179)** | 1 | [AliExpress — Good Display 7.5" GDEY075T7 800×480 E-Paper](https://www.aliexpress.us/item/3256812131718419.html?spm=a2g0o.cart.0.0.50de38daZDibk0&mp=1&pdp_npi=6%40dis%21USD%21USD+38.80%21USD+31.70%21%21USD+30.75%21%21%21%4021030f4a17945382373303834e0fd2%2112000058068457995%21ct%21US%21-1%21%211%210%21&_gl=1*tj6vpq*_gcl_aw*R0NMLjE3OTQ1Mzc4NzAuQ2owS0NRaUE1TlhYQmhERUFSSXNBQkFKaGRKd2ItTzlqMUg1SDB5WF9OaGUxR3o1YU5jSjNKRjgxeXYwbnQ5MkZ1X0lMR29kUEVSOG9RNGFBdnB1RUFMd193Y0I.*_gcl_dc*R0NMLjE3OTQ1Mzc4NzAuQ2owS0NRaUE1TlhYQmhERUFSSXNBQkFKaGRKd2ItTzlqMUg1SDB5WF9OaGUxR3o1YU5jSjNKRjgxeXYwbnQ5MkZ1X0lMR29kUEVSOG9RNGFBdnB1RUFMd193Y0I.*_gcl_au*MTE5MDcxNDM0My4xNzk0NTM2NDgz*_ga*MjA1NTA5OTM5MjA2NTA4MC4xNzk0NTM2NDc3ODAz*_ga_VED1YSGNC7*czE3OTQ1MzY0ODMkbzEkZzEkdDE3OTQ1MzgyMzckajU5JGwwJGgw&gatewayAdapt=glo2usa) | 1-bit B/W reflective E-Paper (`163.2 × 97.9 mm`), `0.34s` hardware partial refresh, `2 µA` deep sleep. Pair with the **Good Display `DESPI-C02`** 24-pin FPC-to-SPI booster adapter board (set switch to `RES = 0.47Ω`). |
| **2** | **Touchpad** | **MIKROE Touchpad 5 Click (`Azoteq IQS550`)** | 1 | [Mikroe — Touchpad 5 Click](https://www.mikroe.com/touchpad-5-click?srsltid=AYCX9vLUsS4gneSMQKFpkoWlaU9Du-4_vM4PriNl-eRTm_yi-ITSIbEt61s) | `29 × 23 mm` capacitive trackpad over `3.3V` I2C (`0x74`). Hardware single-tap click, two-finger scroll, and `INT` (`RDY`) wake-on-touch. |
| **3** | **USB Keyboard Host Converter** | **MusRock `CH9350` USB HID Host to UART Module (`B0FR94RZ82`)** | 1 | [Amazon — MusRock CH9350 Keyboard Scanner Extension (`B0FR94RZ82`)](https://www.amazon.com/MusRock-CH9350-Keyboard-Scanner-Extension/dp/B0FR94RZ82/ref=sr_1_2?crid=3QOYLWYSVU3D6&dib=eyJ2IjoiMSJ9.6dI4_Bnps4OAzHgpInd7m0jsnoNJ-AGcftzJYGsG3EhzWwQ2hHSGPUxR8wTMyuGqnQPS87nOGZgrjmqElbe7kwgb1d67lN63TuTYp4Wqa1dvQqs4Ckj8SBTOg69EfcBIGvhrMJDJNLxmQXEb-gBoAyQ4s_47qkzztDpXBHku802Kyu65u5Qf35QcwOe8agoqOqTPDycdTnp20z_i3VgKwJzGED3Qfw97Au4nAKt2iQrUVVqoECrKxGHM-pwLyWrbq_JQtr0bJmy7PZE35_oPxsPVBjjwB8fBh5bfVTdIzGk.-aK_ClXrawRXLgdFdpOubJ6aU0qsK9uy4FbBbxA5CFs&dib_tag=se&keywords=USB+HID+Host+to+UART&qid=1794539741&s=electronics&sprefix=usb+hid+host+to+uart%2Celectronics%2C173&sr=1-2) | Converts any standard USB 60%/65% keyboard into `115200` baud UART HID frames (`0x57 0xAB 0x01 ...`). *(Use only the Female USB-A "Lower Computer" Host board).* |
| **4** | **MCU + 8MB PSRAM** | **DORHEA `ESP32-S3-DevKitC-1-N16R8` (`ESP32-S3-WROOM-1`, `B0CKXJLP4B`)** | 1 | [Amazon — DORHEA ESP32-S3-DevKitC-1-N16R8 Development Board (`B0CKXJLP4B`)](https://www.amazon.com/DORHEA-Development-Bluetooth-ESP32-S3-DevKit-ESP32-S3-WROOM/dp/B0CKXJLP4B?dib=eyJ2IjoiMSJ9.HVXlqk5xyVqLymsQ28cko5B1nLp1egRsyWyPtVjgkZ85jgmANALPSLsCT8Wv1i-piwaReR3DkIW0G_XZaiCdbURkhtVYGZqRSQDhKvTggkx64yp-SaO0nlRd4TXuB2ZZsATN78ss0jlmHoNegdqz_wLZ-m-ZxnbCjCdfOu6Rx0GKkZ8nrc_CwKDIUpOa6-YNUCQe0OwMvYLaICT9-ZcUlBtVgROOBmKT1v0H5sB3NTY.pjBQPGdK-i3uebU26-kQH6mJ74T9YOZVEoxgaz7Fqgo&dib_tag=se&keywords=ESP32-S3-DevKitC-1%2BN16R8&qid=1794541380&sr=8-3&th=1) | **16MB Flash + 8MB Octal PSRAM** (`N16R8`), dual-core 240 MHz Xtensa LX7, dual USB-C ports, onboard `AMS1117-3.3` step-down regulator. |
| **5** | **Power / Charger / Boost Shield** | **Diymore Dual 18650 Lithium Battery Shield V8 (`5V 2A` / `3V 1A`, `B07SZKNST4`)** | 1 | [Amazon — Diymore Dual 18650 Lithium Battery Shield V8 (`B07SZKNST4`)](https://www.amazon.com/Diymore-Lithium-Battery-Charging-Arduino/dp/B07SZKNST4?crid=V9C8LXR5919X&dib=eyJ2IjoiMSJ9.9-8uIJ6jlbVpdfldcqfdBvFoP_uiFTMU0Kv0uO4x7v4aIubHwe_e4WadgXsfMMLNugBLePP5umGqCInGmg-GNWNMZ0zNYJ2evuiSy0Fw1qQYPLWinP3OSu0NHm3tZBrqnzI1PJxQmTOOFrPgGjTeEWDOyJgHlUffcHOUgq5Eb8nAOMVkrL_coSHvaxW96mPq-G891tsz6uIQfn2_s3h2l9TVsdB7VrSJfRfvcVP4MoA.1QHygQ-TaIuw8-OmoU0KkDtWV5oFhgJmQo4qS24a19E&dib_tag=se&keywords=21700%2BBattery%2BShield%2BV8%2B5V%2B3V%2BESP32&qid=1794541223&sprefix=21700%2Bbattery%2Bshield%2BV8%2B5V%2B3V%2BESP32%2Caps%2C292&sr=8-1&th=1) | Dual-18650 parallel battery sled with USB charging, dedicated **`5V` (`2A`)** AND **`3V` (`3.3V 1A`)** breakout headers, and a **`NORMAL / HOLD`** slide switch (set to **`HOLD`** for continuous always-on operation with zero low-load auto-shutoff). |
| **6** | **Batteries (`7,000 mAh` Total)** | **Samsung `35E` 18650 `3500mAh` 8A Flat-Top Li-Ion Battery** | **2** | [18650BatteryStore — Samsung 35E 18650 3500mAh 8A Battery](https://www.18650batterystore.com/products/samsung-35e-18650-3500mah-8a-battery?_pos=3&_sid=aa5cbab47&_ss=r&_su_rec=9qK-aOJeGmCkpNApNrBV-_8Hf_jvKXkHV-1Y927g2AZVd3JFJDROPUBK7x15qght3nmRyX18CpmK36EiYFX_X-odoCi5YOaB6Wz4Rj-bH-F6CUUAIWFIjIV6coRPItZk3NtRfTpGnuE3SVWgMtqd9QH69EiCchPL9NkVMeFCRFEXIZr13B0ScTD6cWNg3ue50ksW9t3IcXailxNqs223DE2cM45_Q7UikkD_NVTTTOdf8O3bnfZdfk6K5K-rUkRdXKeb9IZ_48V_laz3yNMZ6rjCiDKfNbwABcxfpsOrj7WXaPIgvCrHnL_4m3DUsj4ZtGhGGdHP90je3T10ddMjPCISN-c9UgQnx3BjwsecyyX9y_Q&_su_rec_id=3bca799a-bad2-47a7-9cd7-f8e17cb2dfc0-1794541670) | Two genuine `3500 mAh` flat-top cells in parallel inside the Diymore V8 shield = **`7,000 mAh` (`25.9 Wh`)**, delivering **`~130–150+ hours`** of continuous active writing time on a single charge. |
| **7** | **MicroSD Reader Module** | **WWZMDiB Micro SD TF Card Adapter Reader Module (`B0B779R5TZ`)** | 1 | [Amazon — WWZMDiB Micro SD TF Card Adapter Module (`B0B779R5TZ`)](https://www.amazon.com/WWZMDiB-Adater-Module-Support-Arduino/dp/B0B779R5TZ?dib=eyJ2IjoiMSJ9.walHlm3MKM8lfci1a8CLPHgMh7vIW4sqtSMjt1KEKbYNkIISLxCrz-fgb6T0ABRq4tvse5wxPth7qsXwXQavTBCrlh6yi2thiTMq4xtNH50l5tJgoiPSjUGlrPB_nZUCVx93NyLUbZ6_RQvSL3lQ2LmYm55yuh6VV2_iYg7hfj9rm4JVX0q5LxzPBz211f620YRwsp7fTroAgsn6eMEZBxk-XCasEeba7pttk1IEpnI.F1DfBfsmogJ2fridj0hdd4JenAohzW6dbNe5rdm6KfI&dib_tag=se&keywords=3.3V+Micro+SD+Card+Module+SPI+ESP32&qid=1794541442&sr=8-3) | 6-pin SPI MicroSD reader with onboard `3.3V` LDO regulator and `74LVC125A` `3.3V` logic level shifter (feed `5V` to its `VCC` pin; all SPI data pins operate at `3.3V` logic). |
| **8** | **MicroSD Card** | **Patriot `16GB` MicroSDHC Flash Memory Card (`B08KSTKGVX`)** | 1 | [Amazon — Patriot 16GB MicroSDHC Flash Memory Card (`B08KSTKGVX`)](https://www.amazon.com/Patriot-Micro-Flash-Memory-Card/dp/B08KSTKGVX?crid=3B1WL3N8DFYUQ&dib=eyJ2IjoiMSJ9.iD6BTVVBpE98nLoxEQVfSEOfI51GxvahbLbLbPQ0edYDmoUnZrSnveLdnGXCpZ-VoNMdL0BL36ulQX4rFn26CPLByJQ3yG69Ym8uh07oym-kGTJRW6qlcduylQM8ZdE3mqizoWqqgnuF4-NIIogalTWKlDNbThnIr23inbC_wg26XGkMqu_LA_psT_yg9XJM5U2r-5Q44sTgVNmziXjF2ymXnZoPvESBFhpjbQadk7_FM.QqaUrf3Cg-g9K6om54d0MDQ-jc7k3GtawFRtr_yMGsM&dib_tag=se&keywords=16gb%2Bmicro%2Bsd%2Bcard&qid=1794541494&sprefix=16gb%2Bmicro%2Caps%2C207&sr=8-4&th=1) | **16GB MicroSDHC** comes **pre-formatted as `FAT32`** out of the box (unlike `64GB+` SDXC cards which use `exFAT`), so MicroPython mounts it at `/sd` immediately. Holds ~8,000,000 pages of manuscripts. |
| **9** | **Keyboard** | **60% / 65% Wired USB Keyboard** (e.g., *MageGee MK-Box 65%* or *Redragon K617 Fizz 60%*) | 1 | Any standard wired USB 60% or 65% keyboard | Full-size `19.05 mm` (`1u`) keys; plugs into the Female USB-A port on the MusRock `CH9350`. |
| **10** | **Manual Power Switch** | **ZUPAYIPA 2-Pin SPST Snap-In Mini Rocker Switch (`B01N2U8PK0`)** | 1 | [Amazon — ZUPAYIPA 2-Pin SPST Mini Rocker Switch (`B01N2U8PK0`)](https://www.amazon.com/ZUPAYIPA-Solder-Rocker-Switch-Toggle/dp/B01N2U8PK0?crid=SRGGHEOVD4RI&dib=eyJ2IjoiMSJ9.Cyo34wfWmd9A6KRPQMl0bPkrOW95RfFIH7Vp0P17Jlyqy3f91EgnEenmByJfXKPoWSBIOHbfENUv2IPwS13W3gJTvnIC-XekkQH3FTz6MeAU3sWkBVpRVxEQb2JurwzQmDj9YXmNXYgrW3r8Ay1xVft-TcQmiUfe2qo-zxSJWSfB-mzQ-oDTkTwReQqeiAkU_ZBLHryboHz2EpnJQw7o81tNN3gkZnbv0WESXVkKFI8.hyv1jGC0kFYNj-tKNTOLPXK9vh77Z3kke4U7kkZj6KA&dib_tag=se&keywords=spst+switch&qid=1794542241&sprefix=SPST%2Caps%2C153&sr=8-11) | `10A` rated `I/O` snap-in panel rocker (`~13 × 19 mm` cutout). Wired in series on the **`5V` output line** from the Diymore V8 shield for a tactile exterior ON/OFF switch. |

---

## ⚠️ Three Important Assembly Notes for These Exact Parts

1. **Diymore V8 Battery Shield Polarity & `HOLD` Switch (`B07SZKNST4`)**:
   * **Cell Polarity**: Both Samsung `35E` 18650 cells in the Diymore V8 shield sit **in the same direction (in parallel)**, **not** alternating like a TV remote! Check the `+` and `-` markings inside the plastic sled carefully before snapping the cells in, as reversing a cell on a V8 shield will permanently damage its protection IC.
   * **`HOLD` Switch**: Set the slide switch on the Diymore V8 shield to **`HOLD`** (Always-On). In `NORMAL` mode, the shield shuts off after ~30 seconds if current draw is under `50 mA`; in **`HOLD`** mode, it stays continuously active regardless of how little power the E-Paper screen draws!
2. **Powering the WWZMDiB MicroSD Module (`B0B779R5TZ`)**:
   * Because the WWZMDiB adapter has its own onboard `AMS1117-3.3` voltage regulator and `74LVC125A` `3.3V` logic level shifter, wire its **`VCC` pin to `5V`** (from the Diymore V8 `5V` rail or ESP32-S3 `5V` pin). Its onboard regulator will supply a clean `3.3V` to the Patriot 16GB MicroSD card while keeping all SPI signal pins (`MISO`, `MOSI`, `SCK`, `CS`) at safe `3.3V` logic for the ESP32-S3.
3. **Good Display `GDEY075T7` E-Paper Ribbon Adapter (`DESPI-C02`)**:
   * Make sure to include the **Good Display `DESPI-C02`** 24-pin FPC-to-SPI adapter board when ordering the bare 7.5" `GDEY075T7` panel on AliExpress, and slide its resistor switch to **`0.47Ω`**.

---

## 🔌 Complete Power & Wiring Diagram

```text
  [2× Samsung 35E 18650 (7,000 mAh) in Diymore Battery Shield V8 (Switch = HOLD)]
     │
     ├──► 5V Header Rail (2A)
     │      ├──► DORHEA ESP32-S3-DevKitC-1 (5V / VBUS Pin)
     │      ├──► MusRock CH9350 Host Board (5V) ──► 60% / 65% USB Keyboard
     │      └──► WWZMDiB MicroSD Module (VCC Pin; onboard LDO -> 3.3V Logic)
     │
     └──► 3.3V Rail (from ESP32-S3 `3V3` Pin or Diymore V8 `3V` Header)
            ├──► Good Display 7.5" GDEY075T7 + DESPI-C02 (VCC = 3.3V)
            └──► MIKROE Touchpad 5 Click (3.3V Pin)
```

| Peripheral | Peripheral Pin | DORHEA ESP32-S3-DevKitC-1 Pin | Function / Config Key (`hardware_config.json`) |
| :--- | :--- | :--- | :--- |
| **Good Display `GDEY075T7` (`DESPI-C02`)** | `VCC` / `GND` | `3V3` / `GND` | `3.3V` Power (`RES` switch = `0.47Ω`) |
| | `SCK` (`CLK`) | **`GPIO 12`** | `spi.sck_pin` (`10 MHz` SPI1) |
| | `SDI` (`MOSI`) | **`GPIO 11`** | `spi.mosi_pin` |
| | `CS` (`CSB`) | **`GPIO 10`** | `spi.cs_pin` |
| | `D/C` | **`GPIO 9`** | `spi.dc_pin` |
| | `RES` (`RST`) | **`GPIO 8`** | `spi.rst_pin` |
| | `BUSY` | **`GPIO 13`** | `spi.busy_pin` (Active-LOW: `0`=Busy, `1`=Ready) |
| **MIKROE Touchpad 5 Click (`IQS550`)** | `3.3V` / `GND` | `3V3` / `GND` | `3.3V` Power (`0x74` I2C address) |
| | `SDA` | **`GPIO 1`** | `i2c.sda_pin` |
| | `SCL` | **`GPIO 2`** | `i2c.scl_pin` (`400 kHz`) |
| | `INT` (`RDY`) | **`GPIO 14`** | `pointer.rdy_pin` (Active-HIGH Ready Window) |
| **MusRock `CH9350` USB Host (`B0FR94RZ82`)** | `5V` / `GND` | `5V` / `GND` | Powers CH9350 Host + USB Keyboard |
| | `TX` (`TXD`) | **`GPIO 18`** | `keyboard.uart_rx_pin` (`115200` baud) |
| **WWZMDiB MicroSD (`B0B779R5TZ`)** | `VCC` / `GND` | `5V` / `GND` | Onboard LDO steps `5V -> 3.3V` for Patriot 16GB SD |
| | `SCK` | **`GPIO 15`** | `sdcard.sck_pin` (SPI2 Slot 2) |
| | `MOSI` | **`GPIO 16`** | `sdcard.mosi_pin` |
| | `MISO` | **`GPIO 7`** | `sdcard.miso_pin` |
| | `CS` | **`GPIO 5`** | `sdcard.cs_pin` |
| **Battery Monitor (Optional)** | Raw `BAT+` via `2× 100kΩ` divider | **`GPIO 4`** | `battery_adc_pin` (Live `0–100%` gauge in top bar) |
