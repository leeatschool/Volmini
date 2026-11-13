# Volmini — Standalone ESP32 MicroPython Word Processing & Codex Studio

> **Stripped-down embedded MicroPython edition of Volumenodex engineered for ESP32-S3.**

---

## ✨ Overview & Architecture

**Volmini** distills the core authoring experience of **Volumenodex** into a standalone, distraction-free, ultra-low-memory **MicroPython** environment for **ESP32-S3** hardware (with SPI monochrome/RGB565 TFT or e-Ink display, SD card / internal Flash storage, and I2C/matrix physical keyboard) plus a pixel-accurate **Desktop Simulator**.

### Key Capabilities

1. **Power-On Initiating Boot Splash & Instant Session Resume**:
   * Displays the signature `V|` monochrome emblem (`volmini/ui/splash_logo.py`), step-by-step hardware & index initialization progress bar, and automatically resumes your last edited manuscript at your exact cursor position (or press `Space` to open the Document Launcher).
2. **Stripped-Down Print-Accurate Monochrome Display & Dynamic Top Ribbon**:
   * True WYSIWYG physical page sheets with prepress margin crop ticks, running headers/footers (`- {page} -`), accurate line wrapping for paper presets (`US Letter`, `A4`, `US Legal`, `Executive`, `Trade Paperback 6x9`), and margins (`Normal`, `Narrow`, `Wide`, `Manuscript`).
   * **Dynamic Simplified Top Ribbon (`F8` or `[Rib:ON]`)**: Live formatting toolbar (`[Title] [H1] [H2] [Quote] [Body] | [B] [I] [U] | [L] [C] [R] | [Save] [Outline] [Ref] [Review] [Corvus] [BLE] [Page]`) that dynamically inverts active style/inline/alignment buttons as the cursor moves and responds to pointer/touchpad hover and clicks.
   * **Pointer / Touchpad / Trackball Support**: Native I2C pointer polling (`Pimoroni Trackball`, `FT6236 Capacitive Touch`, etc.) and desktop mouse simulation for clicking Ribbon buttons, clicking directly onto page text to reposition the cursor, and scrolling.
   * **Wide DIY Multi-Display Support (`hardware_config.json`)**: Native profiles and SPI drivers for the **Good Display 7.5" 800×480 E-Paper (`GDEY075T7` / `UC8179`)** with `0.34s` hardware partial window updates and `2 uA` deep sleep, plus `ssd1680_400x300` (4.2" E-Paper), `ssd1680_296x128` (2.9" E-Paper), `sharp_400x240` (2.7" Memory LCD), `st7796_480x320` (3.5"/4.0" TFT), `st7789_320x240` (2.4"/2.8" IPS TFT), and custom resolutions.
3. **Creative Fiction & General Non-Fiction Authoring Modes**:
   * Dedicated mode switching (`Ctrl+M`) tailoring starter templates and writing companion prompts.
4. **Chapter Outline Navigator (`F2`)**:
   * Automatically scans manuscript headings (`Title`, `H1`–`H3`, `Chapter ...`, `Prologue`, `Epilogue`), calculates word counts per chapter, tracks chapter statuses (`Draft`, `In Progress`, `Needs Revision`, `Completed`), reorders chapters in-place (`U`/`D`), and jumps to any chapter on `Enter`.
5. **Stripped Offline Writer's Reference Compendium (`F3`)**:
   * Compiles all 262 articles across 12 categories from `bundled_knowledge.json` into a plain-text data store (`data/ref_data.txt`, 673 KB) and a 22 KB byte-offset index (`data/ref_index.json`).
   * Zero cross-references and zero rich-text overhead; loads article text on demand via `seek()` + `read()` using <2 KB of RAM per lookup, with 1-key (`I`) insertion into your manuscript.
6. **Revision Lenses & Low-RAM Binary-Searched Spell Check (`F4`)**:
   * **Four Editorial Lenses**: Adverbs, Passive Voice, Filler Phrases, and Sentence Pacing with active-verb replacement suggestions.
   * **O(log N) Flash/SD Spell Checker**: Binary-searches `data/dict_words.txt` directly on disk without loading the dictionary into RAM, paired with inflection stemming, common-typo corrections, and a persistent `user_dict.json`.
7. **Corvus the Raven Companion & Sprint Timer (`F5`)**:
   * 16x16 1-bit pixel-art Raven sprite with mood states (`IDLE`, `WRITING`, `ALERT`, `CELEBRATING`, `SLEEPING`, `NUDGING`), word-count milestones, real-time active-sentence duplicate-word detection, mode-specific writing sparks (`S`), and a 25-minute sprint timer (`T`).
8. **Dual-Mode On-Demand Bluetooth Beam to Phone (`F6`)**:
   * **Wi-Fi is permanently disabled**, and the **BLE radio stays strictly OFF (`0mW`)** during normal writing.
   * When triggered in the `F6` modal, choose between:
     * **Mode 1 (`BLE UART / NUS`)**: Streams framed, CRC32-verified `.md` chunks to any BLE Serial or Web-Bluetooth phone app.
     * **Mode 2 (`BLE HID Keyboard Auto-Type`)**: Acts as a standard Bluetooth keyboard and types your manuscript directly into an open Notes/Docs app on iOS/Android with zero app installation required.
   * Automatically powers the BLE radio back OFF immediately after beaming finishes or is cancelled.
9. **Atomic Autosave & Zero-Dependency `.docx` Export**:
   * Saves `.md`, `.txt`, and `.story.json` companion metadata using atomic `.tmp` write + rename for power-loss safety, and includes a pure-Python zero-dependency Microsoft Word `.docx` (PKZIP + OpenXML) exporter (`Ctrl+E`).

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+B` / `Ctrl+I` / `Ctrl+U` | Toggle Inline Bold / Italic / Underline |
| `Ctrl+T` / `Ctrl+1..3` | Paragraph Style: Title / Heading 1 / Heading 2 / Heading 3 |
| `Ctrl+Q` / `Ctrl+0` | Paragraph Style: Blockquote / Normal Body |
| `Ctrl+L` / `Ctrl+K` / `Ctrl+R` | Paragraph Align: Left / Center / Right |
| `Ctrl+P` | Insert Explicit Page Break |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+S` / `Ctrl+O` / `Ctrl+E` | Atomic Save / Open File Browser / Export (`.docx`, `.md`, `.txt`) |
| `Ctrl+M` | Toggle Creative Fiction / General Non-Fiction Mode |
| `F1` | Quick Keyboard Help Card |
| `F2` | Chapter Outline Navigator (`Enter`: Jump, `N`: +Chapter, `S`: Status, `U`/`D`: Reorder) |
| `F3` | Stripped Writer's Reference Compendium (`Tab`: Category, `Enter`: Read, `I`: Insert) |
| `F4` | Revision Lenses & Spell Check Inspector (`Enter`: Apply Suggestion, `A`: +User Dict, `H`: Toggle Highlights) |
| `F5` | Corvus the Raven Companion & 25m Sprint Timer (`S`: Spark Prompt, `T`: Start/Stop Sprint) |
| `F6` | On-Demand BLE Beam to Phone (`1`: BLE UART Stream, `2`: BLE HID Auto-Type, `Enter`: Beam) |
| `F7` | Print Page Setup (Paper Size, Orientation, Margins, First-Page Number Suppression) |
| `F8` | Toggle Dynamic Simplified Top Ribbon (`[Rib:ON]` / `[Rib:OFF]`) |
| `Alt+1..8` | 60% Keyboard Function Key Equivalents (`F1`..`F8`) |
| `Alt+I/J/K/L` | 60% Keyboard Arrow Key Equivalents (`Up` / `Left` / `Down` / `Right`) |

---

## 🛠️ Recommended Bill of Materials (BOM)

See the full **[Bill of Materials & Wiring Guide (`BOM.md`)](BOM.md)** for complete pinouts and build notes.

| Subsystem | Recommended Component & Link | Interface & Driver |
| :--- | :--- | :--- |
| **Display** | **[Good Display 7.5" 800×480 E-Paper (`GDEY075T7`, UC8179)](https://www.aliexpress.us/item/3256812131718419.html?spm=a2g0o.cart.0.0.50de38daZDibk0&mp=1&pdp_npi=6%40dis%21USD%21USD+38.80%21USD+31.70%21%21USD+30.75%21%21%21%4021030f4a17945382373303834e0fd2%2112000058068457995%21ct%21US%21-1%21%211%210%21&_gl=1*tj6vpq*_gcl_aw*R0NMLjE3OTQ1Mzc4NzAuQ2owS0NRaUE1TlhYQmhERUFSSXNBQkFKaGRKd2ItTzlqMUg1SDB5WF9OaGUxR3o1YU5jSjNKRjgxeXYwbnQ5MkZ1X0lMR29kUEVSOG9RNGFBdnB1RUFMd193Y0I.*_gcl_dc*R0NMLjE3OTQ1Mzc4NzAuQ2owS0NRaUE1TlhYQmhERUFSSXNBQkFKaGRKd2ItTzlqMUg1SDB5WF9OaGUxR3o1YU5jSjNKRjgxeXYwbnQ5MkZ1X0lMR29kUEVSOG9RNGFBdnB1RUFMd193Y0I.*_gcl_au*MTE5MDcxNDM0My4xNzk0NTM2NDgz*_ga*MjA1NTA5OTM5MjA2NTA4MC4xNzk0NTM2NDc3ODAz*_ga_VED1YSGNC7*czE3OTQ1MzY0ODMkbzEkZzEkdDE3OTQ1MzgyMzckajU5JGwwJGgw&gatewayAdapt=glo2usa)** *(+ `DESPI-C02` 24-pin FPC SPI adapter)* | 4-wire SPI (`GDEY075T7Driver`, `0.34s` partial refresh, `2 µA` sleep) |
| **Touchpad** | **[MIKROE Touchpad 5 Click (`Azoteq IQS550`)](https://www.mikroe.com/touchpad-5-click?srsltid=AYCX9vLUsS4gneSMQKFpkoWlaU9Du-4_vM4PriNl-eRTm_yi-ITSIbEt61s)** | I2C `0x74` + `INT` (`Touchpad5ClickDriver`, tap-to-click & 2-finger scroll) |
| **USB Keyboard Converter** | **[MusRock `CH9350` USB HID Host to UART Module (`B0FR94RZ82`)](https://www.amazon.com/MusRock-CH9350-Keyboard-Scanner-Extension/dp/B0FR94RZ82/ref=sr_1_2?crid=3QOYLWYSVU3D6&dib=eyJ2IjoiMSJ9.6dI4_Bnps4OAzHgpInd7m0jsnoNJ-AGcftzJYGsG3EhzWwQ2hHSGPUxR8wTMyuGqnQPS87nOGZgrjmqElbe7kwgb1d67lN63TuTYp4Wqa1dvQqs4Ckj8SBTOg69EfcBIGvhrMJDJNLxmQXEb-gBoAyQ4s_47qkzztDpXBHku802Kyu65u5Qf35QcwOe8agoqOqTPDycdTnp20z_i3VgKwJzGED3Qfw97Au4nAKt2iQrUVVqoECrKxGHM-pwLyWrbq_JQtr0bJmy7PZE35_oPxsPVBjjwB8fBh5bfVTdIzGk.-aK_ClXrawRXLgdFdpOubJ6aU0qsK9uy4FbBbxA5CFs&dib_tag=se&keywords=USB+HID+Host+to+UART&qid=1794539741&s=electronics&sprefix=usb+hid+host+to+uart%2Celectronics%2C173&sr=1-2)** | UART1 RX `GPIO 18` @ `115200` baud (`USBHIDKeyboardDecoder`) |
| **Keyboard** | **60% / 65% Wired USB Keyboard** (e.g., *[MageGee MK-Box 65%](https://www.amazon.com/s?k=MageGee+MK-Box+65%25+wired+mechanical+keyboard)* or *[Redragon K617 Fizz 60%](https://www.amazon.com/s?k=Redragon+K617+Fizz+60%25+wired+keyboard)*) | Standard USB-A into MusRock `CH9350` Host |
| **MCU + 8MB PSRAM** | **[DORHEA ESP32-S3-DevKitC-1-N16R8 (`ESP32-S3-WROOM-1`, `B0CKXJLP4B`)](https://www.amazon.com/DORHEA-Development-Bluetooth-ESP32-S3-DevKit-ESP32-S3-WROOM/dp/B0CKXJLP4B?dib=eyJ2IjoiMSJ9.HVXlqk5xyVqLymsQ28cko5B1nLp1egRsyWyPtVjgkZ85jgmANALPSLsCT8Wv1i-piwaReR3DkIW0G_XZaiCdbURkhtVYGZqRSQDhKvTggkx64yp-SaO0nlRd4TXuB2ZZsATN78ss0jlmHoNegdqz_wLZ-m-ZxnbCjCdfOu6Rx0GKkZ8nrc_CwKDIUpOa6-YNUCQe0OwMvYLaICT9-ZcUlBtVgROOBmKT1v0H5sB3NTY.pjBQPGdK-i3uebU26-kQH6mJ74T9YOZVEoxgaz7Fqgo&dib_tag=se&keywords=ESP32-S3-DevKitC-1%2BN16R8&qid=1794541380&sr=8-3&th=1)** | 16MB Flash + 8MB Octal PSRAM, onboard `AMS1117-3.3` regulator |
| **MicroSD Reader & Card** | **[WWZMDiB Micro SD TF Adapter (`B0B779R5TZ`)](https://www.amazon.com/WWZMDiB-Adater-Module-Support-Arduino/dp/B0B779R5TZ?dib=eyJ2IjoiMSJ9.walHlm3MKM8lfci1a8CLPHgMh7vIW4sqtSMjt1KEKbYNkIISLxCrz-fgb6T0ABRq4tvse5wxPth7qsXwXQavTBCrlh6yi2thiTMq4xtNH50l5tJgoiPSjUGlrPB_nZUCVx93NyLUbZ6_RQvSL3lQ2LmYm55yuh6VV2_iYg7hfj9rm4JVX0q5LxzPBz211f620YRwsp7fTroAgsn6eMEZBxk-XCasEeba7pttk1IEpnI.F1DfBfsmogJ2fridj0hdd4JenAohzW6dbNe5rdm6KfI&dib_tag=se&keywords=3.3V+Micro+SD+Card+Module+SPI+ESP32&qid=1794541442&sr=8-3)** + **[Patriot 16GB MicroSDHC (`B08KSTKGVX`)](https://www.amazon.com/Patriot-Micro-Flash-Memory-Card/dp/B08KSTKGVX?crid=3B1WL3N8DFYUQ&dib=eyJ2IjoiMSJ9.iD6BTVVBpE98nLoxEQVfSEOfI51GxvahbLbPQ0edYDmoUnZrSnveLdnGXCpZ-VoNMdL0BL36ulQX4rFn26CPLByJQ3yG69Ym8uh07oym-kGTJRW6qlcduylQM8ZdE3mqizoWqqgnuF4-NIIogalTWKlDNbThnIr23inbC_wg26XGkMqu_LA_psT_yg9XJM5U2r-5Q44sTgVNmziXjF2ymXnZoPvESBFhpjbQadk7_FM.QqaUrf3Cg-g9K6om54d0MDQ-jc7k3GtawFRtr_yMGsM&dib_tag=se&keywords=16gb%2Bmicro%2Bsd%2Bcard&qid=1794541494&sprefix=16gb%2Bmicro%2Caps%2C207&sr=8-4&th=1)** | SPI2 (`CS=5`, `SCK=15`, `MOSI=16`, `MISO=7`), native `FAT32` |
| **Battery Shield & Cells (`7,000 mAh`)** | **[Diymore Dual 18650 Battery Shield V8 (`B07SZKNST4`)](https://www.amazon.com/Diymore-Lithium-Battery-Charging-Arduino/dp/B07SZKNST4?crid=V9C8LXR5919X&dib=eyJ2IjoiMSJ9.9-8uIJ6jlbVpdfldcqfdBvFoP_uiFTMU0Kv0uO4x7v4aIubHwe_e4WadgXsfMMLNugBLePP5umGqCInGmg-GNWNMZ0zNYJ2evuiSy0Fw1qQYPLWinP3OSu0NHm3tZBrqnzI1PJxQmTOOFrPgGjTeEWDOyJgHlUffcHOUgq5Eb8nAOMVkrL_coSHvaxW96mPq-G891tsz6uIQfn2_s3h2l9TVsdB7VrSJfRfvcVP4MoA.1QHygQ-TaIuw8-OmoU0KkDtWV5oFhgJmQo4qS24a19E&dib_tag=se&keywords=21700%2BBattery%2BShield%2BV8%2B5V%2B3V%2BESP32&qid=1794541223&sprefix=21700%2Bbattery%2Bshield%2BV8%2B5V%2B3V%2BESP32%2Caps%2C292&sr=8-1&th=1)** + **2× [Samsung 35E 18650 `3500mAh` Cells](https://www.18650batterystore.com/products/samsung-35e-18650-3500mah-8a-battery?_pos=3&_sid=aa5cbab47&_ss=r&_su_rec=9qK-aOJeGmCkpNApNrBV-_8Hf_jvKXkHV-1Y927g2AZVd3JFJDROPUBK7x15qght3nmRyX18CpmK36EiYFX_X-odoCi5YOaB6Wz4Rj-bH-F6CUUAIWFIjIV6coRPItZk3NtRfTpGnuE3SVWgMtqd9QH69EiCchPL9NkVMeFCRFEXIZr13B0ScTD6cWNg3ue50ksW9t3IcXailxNqs223DE2cM45_Q7UikkD_NVTTTOdf8O3bnfZdfk6K5K-rUkRdXKeb9IZ_48V_laz3yNMZ6rjCiDKfNbwABcxfpsOrj7WXaPIgvCrHnL_4m3DUsj4ZtGhGGdHP90je3T10ddMjPCISN-c9UgQnx3BjwsecyyX9y_Q&_su_rec_id=3bca799a-bad2-47a7-9cd7-f8e17cb2dfc0-1794541670)** | **`7,000 mAh` (`~130–150+ hrs`)**, `5V 2A` + `3.3V 1A` rails, `HOLD` mode |
| **Power Switch** | **[ZUPAYIPA 2-Pin SPST Snap-In Mini Rocker Switch (`B01N2U8PK0`)](https://www.amazon.com/ZUPAYIPA-Solder-Rocker-Switch-Toggle/dp/B01N2U8PK0?crid=SRGGHEOVD4RI&dib=eyJ2IjoiMSJ9.Cyo34wfWmd9A6KRPQMl0bPkrOW95RfFIH7Vp0P17Jlyqy3f91EgnEenmByJfXKPoWSBIOHbfENUv2IPwS13W3gJTvnIC-XekkQH3FTz6MeAU3sWkBVpRVxEQb2JurwzQmDj9YXmNXYgrW3r8Ay1xVft-TcQmiUfe2qo-zxSJWSfB-mzQ-oDTkTwReQqeiAkU_ZBLHryboHz2EpnJQw7o81tNN3gkZnbv0WESXVkKFI8.hyv1jGC0kFYNj-tKNTOLPXK9vh77Z3kke4U7kkZj6KA&dib_tag=se&keywords=spst+switch&qid=1794542241&sprefix=SPST%2Caps%2C153&sr=8-11)** | Series disconnect on the `5V` output rail (`~13 × 19 mm` panel cutout) |

---

## 🚀 Quickstart (Desktop Simulator & ESP32 Deployment)

### 1. Rebuild Stripped Assets from Volumenodex
```bash
python tools/build_assets.py
```

### 2. Run the Desktop FrameBuffer Simulator
```bash
python sim_main.py
```

### 3. Run the Automated Test Suite
```bash
pytest tests/ -v
```

### 4. Deploy to ESP32-S3 (via `mpremote`)
```bash
python tools/deploy_esp32.py COM3
```
