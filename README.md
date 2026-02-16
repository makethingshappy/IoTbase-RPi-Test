# IoTbase RPi 3-04 — Hardware Validation Test Suite

> **Python test scripts and report generators for manufacturing validation of the IoTbase RPi 3-04 carrier board — a Raspberry Pi HAT featuring EEPROM, Watchdog, GPIO, RS-485, CAN, I²C, UART, and mikroBUS interfaces.**

---

## Overview

The **IoTbase RPi 3-04** (Rev. 3-04) is an industrial-grade carrier board designed for Raspberry Pi. It exposes a wide range of peripherals through standardised connectors (HOST-P12, HOST-PF, mikroBUS) and provides on-board power regulation (9–36 VDC input, USB-C, or 5 V header).

This repository contains a complete **hardware validation test suite** written in Python 3 (CPython) that runs directly on the Raspberry Pi. Each script exercises a specific subsystem, performs automated pass/fail checks, and generates structured reports in both **TXT** and **JSON** formats under a `reports/` directory.

## Board Features Tested

| Subsystem | IC / Interface | Test Script |
|---|---|---|
| EEPROM (8 Kbit / 64 Kbit) | M24C08 / M24C64 via I²C | `iotbase_eeprom_report.py` |
| Hardware Watchdog | TPS3828-33 / STM6822 | `iotbase_watchdog_report.py` |
| GPIO Loopback (single pair) | AP0–AP7 via BCM GPIOs | `iotbase_gpio_report.py` |
| GPIO Pair (bidirectional) | AP0–AP7 all pairs | `iotbase_gpio_pair_report.py` |
| HOST-P12 Digital I/O | DO1–DO4 / DI1–DI4 | `hostp12_io.py` |
| RS-485 Communication | SP3485EN via UART | `iotbase_rs485_echo_test.py` |

### Auxiliary Scripts

| Script | Description |
|---|---|
| `PC.py` | RS-485 echo server — runs on a PC connected via USB-to-RS485 adapter |
| `test.py` | Minimal serial ping utility for quick UART sanity checks |
| `eeprom_test.py` | Standalone EEPROM read/write test (no report generation) |

## Hardware Requirements

- **Raspberry Pi 4** (or compatible) with Raspberry Pi OS
- **IoTbase RPi 3-04** carrier board mounted on the 40-pin GPIO header
- Loopback jumper wires for GPIO pair tests (e.g. AP0↔AP1, AP2↔AP3, etc.)
- USB-to-RS485 adapter + PC for RS-485 echo tests
- I²C enabled (`sudo raspi-config` → Interface Options → I2C → Enable)
- Watchdog enabled in `/boot/firmware/config.txt`: `dtparam=watchdog=on`

## GPIO ↔ AP Pin Mapping
```
AP0 → GPIO5  (pin 29)    AP4 → GPIO24 (pin 18)
AP1 → GPIO6  (pin 31)    AP5 → GPIO16 (pin 36)
AP2 → GPIO19 (pin 35)    AP6 → GPIO20 (pin 38)
AP3 → GPIO26 (pin 37)    AP7 → GPIO21 (pin 40)
```

HOST-P12 connector mapping: DO1–DO4 = AP0–AP3 (outputs), DI1–DI4 = AP4–AP7 (inputs).

## Installation
```bash
git clone https://github.com/<your-org>/iotbase-rpi-test-suite.git
cd iotbase-rpi-test-suite
pip install smbus2 pyserial RPi.GPIO
```

> **Note:** Some scripts require `sudo` to access `/dev/watchdog` or GPIO pins.

## Usage

All scripts generate reports in `./reports/` with timestamped filenames.

### EEPROM — Full Test
```bash
sudo python3 iotbase_eeprom_report.py --chip 24c08 --base 0x54 --bus 1 --verbose
```

Runs four subtests: last-byte write/read, page-cross, block-cross, and mid-block random data with CRC32 verification. Outputs TXT + JSON reports and a `.bin` snapshot for retention verification.

### EEPROM — Retention Verification (after power cycle)
```bash
sudo python3 iotbase_eeprom_report.py --chip 24c08 --base 0x54 --bus 1 \
    --verify reports/<timestamp>_midblock.bin
```

### Watchdog — Non-Destructive (feed-only)
```bash
sudo python3 iotbase_watchdog_report.py --mode feed-only --timeout 5 --run-seconds 180 --period 0.5
```

### Watchdog — Trigger Reboot
```bash
sudo python3 iotbase_watchdog_report.py --mode trigger-reboot --timeout 5 --run-seconds 10 --period 0.5
```

### Watchdog — Post-Reboot Check
```bash
sudo python3 iotbase_watchdog_report.py --mode post-check
```

### GPIO Pair Test (bidirectional)
```bash
sudo python3 iotbase_gpio_pair_report.py AP0 AP1 --bidir
sudo python3 iotbase_gpio_pair_report.py AP2 AP3 --bidir
sudo python3 iotbase_gpio_pair_report.py AP4 AP5 --bidir
sudo python3 iotbase_gpio_pair_report.py AP6 AP7 --bidir
```

### HOST-P12 Digital I/O
```bash
sudo python3 hostp12_io.py
```

Takes a DI1–DI4 input snapshot on startup, then enters an interactive shell for controlling DO1–DO4.

### RS-485 Echo Test
```bash
# PC side — start echo server first (adjust COM port)
python3 PC.py

# RPi side
python3 iotbase_rs485_echo_test.py --port /dev/ttyAMA0 --baud 115200
```

> **Configuration:** RS-485 direction-control jumpers must be in the **AUTO** position.

## Report Output

Each test generates timestamped files in `./reports/`:
```
reports/
├── 20260204_103504_report.txt          # Human-readable EEPROM report
├── 20260204_103504_results.json        # Machine-readable EEPROM results
├── 20260204_103504_midblock.bin        # Binary snapshot for retention verify
├── 20260204_104501_wdt_report.txt      # Watchdog feed-only report
├── 20260204_104501_wdt_report.json
├── 20260204_110512_hostp12_inputs.txt  # HOST-P12 I/O snapshot
├── 20260209_163359_rs485_echo_test.txt # RS-485 echo results
└── ...
```

JSON reports include full environment metadata (hostname, platform, Python version, kernel info) for traceability.

## Test Summary (Reference Run — Feb 2026)

| Component | Status | Notes |
|---|---|---|
| EEPROM (24C08) | ✅ PASS | All 4 subtests passed |
| Watchdog | ✅ PASS | Reboot triggered and verified |
| GPIO Pairs (AP0–AP7) | ✅ PASS | 32/32 bidirectional tests passed |
| HOST-P12 I/O | ✅ PASS | Snapshot OK |
| RS-485 Communication | ✅ PASS | TX/RX echo verified at 115200 baud |

## Schematic Reference

The hardware design (Altium Designer) covers four sheets:

1. **Raspberry Pi & EEPROM** — 40-pin connector, M24C08, TPS3828 watchdog
2. **Connectors** — mikroBUS (M1), HOST-PF, HOST-P12, J31/J32 headers
3. **I²C, UART & RS-485** — SP3485EN transceiver, MCP2515 CAN controller
4. **Power Supply** — 9–36 VDC input (K7805M DC-DC), USB-C, AMS1117-3.3 LDO

## Project Structure
```
.
├── README.md
├── iotbase_eeprom_report.py       # EEPROM full test + retention verify
├── iotbase_watchdog_report.py     # Watchdog (feed-only / trigger-reboot / post-check)
├── iotbase_gpio_report.py         # Single GPIO pair loopback test
├── iotbase_gpio_pair_report.py    # Multi-pair bidirectional GPIO test
├── hostp12_io.py                  # HOST-P12 DI snapshot + DO interactive control
├── iotbase_rs485_echo_test.py     # RS-485 echo test (RPi side)
├── PC.py                          # RS-485 echo server (PC side)
├── eeprom_test.py                 # Standalone EEPROM test (no reports)
├── test.py                        # Minimal serial ping utility
├── docs/
│   ├── IoTbase_RPi_3-04_OUTPUT.PDF
│   └── IoTbase_RPi_Test_Summary.docx
└── reports/                       # Auto-generated (gitignored)
```

## .gitignore (recommended)
```
reports/
__pycache__/
*.pyc
```

## License

*Add your license here.*

## Author

Developed for **BOKRA** — *make Things Happy!*
