# HP 3458A NVRAM Tool

**Read, decode, edit, and write the calibration RAM of the HP 3458A 8.5-digit precision multimeter via GPIB — including the factory-protected Cal_RAM area.**

> Version: V0.9 Beta

---

## What is this?

The HP 3458A stores all calibration constants (zero offsets, gain values, DAC trims, ACAL results) in a battery-backed NVRAM chip (DS1220Y). This area is normally write-protected at the hardware level — the chip's `/WE` line is behind an I/O latch that cannot be reached directly over GPIB.

This tool bypasses that protection by triggering the instrument's own **Level 7 NMI firmware routine** via a GPIB JSR backdoor combined with 68000 machine code injected into Settings RAM. The approach was discovered through full firmware reverse engineering of the HP 3458A REV9 ROM. See [`research/`](research/) for the complete analysis.

**Supported operations:**
- Cal_RAM dump (3-pass read with MD5 verification)
- Field-level decode of all 200+ calibration constants
- Edit individual calibration fields
- Upload modified Cal_RAM back to the instrument (fast block mode or word-by-word safe mode)
- Verify write by reading back and comparing
- Settings RAM dump and decode
- Calibration report generation

---

## Download

**Windows EXE — no Python required:**

Download `hp3458a_nvram_tool.exe` from the [Releases](../../releases) page and run it directly.

**Python source:**

```
cd program
python hp3458a_gui.py
```

Requirements: Python 3.8+, tkinter (built-in). For NI-488.2 direct mode: NI-VISA or NI-488.2 DLL must be installed.

---

## Hardware requirements

| Component | Details |
|---|---|
| Instrument | HP 3458A (tested on REV9 firmware, A5 REV A board, MC68HC000P8 CPU) |
| GPIB adapter | Any of the following (see Connection section) |

**Supported GPIB connections:**

| Mode | Hardware needed |
|---|---|
| **TCP Bridge (Prologix)** | Prologix GPIB-ETHERNET or GPIB-USB + TCP bridge script running on a PC on the same network |
| **Direct NI-488.2** | NI GPIB-USB-HS (or any NI GPIB adapter) connected to the PC running this tool |

---

## Usage

### 1. Connect

Launch the tool, select connection mode (TCP or NI-488.2), enter the host/port or GPIB board index, set GPIB address (default: 22), and click **Connect**.

Settings are saved automatically to `hp3458a_tool.ini` next to the executable.

### 2. Read Cal_RAM

Go to the **Cal_RAM** tab and click **Dump**. The tool performs 3 read passes and verifies them with MD5 checksums. All three passes must match — if they don't, re-run the dump.

### 3. Edit calibration fields

Double-click any field in the list to edit its value. Fields are decoded as IEEE 754 double-precision floats (or integers where applicable). The tool shows the raw hex alongside the decoded value.

### 4. Upload to instrument

- **Fast block mode** (recommended for most cases) — uploads in blocks, takes a few minutes
- **Word-by-word safe mode** — uploads one word at a time, takes ~1 hour, most conservative

After uploading, always run **Verify** to confirm the instrument received the correct data.

### 5. Checksum

If you edited any field inside a checksum region, click **Recalculate Checksum** before uploading. The HP 3458A will refuse calibration data with an incorrect checksum.

---

## How it works (technical summary)

The DS1220Y Cal_RAM chip's `/WE` line is controlled by an I/O latch that is not memory-mapped — it can only be driven by specific firmware routines. Through disassembly of the REV9 ROM, we identified the **Level 7 NMI handler** as the only routine that opens the `/WE` window.

The write sequence:
1. Machine code is injected into the Settings RAM (DS1235, writable over GPIB via `MWRITE`)
2. The NMI handler is triggered via a GPIB JSR backdoor command with 4 "magic word" security checks
3. During the NMI service routine, the `/WE` window is open and the injected code writes the target Cal_RAM word
4. The window closes when the NMI handler returns

**Critical constraint:** Settings RAM must not be read during the `/WE` window — doing so causes a bus conflict and CPU crash. See [`failed_attempts/`](failed_attempts/) for methods that were tried and ruled out for this and other reasons.

---

## Repository structure

| Folder | Contents |
|---|---|
| [`program/`](program/) | The tool itself: tkinter GUI and backend modules, hardware-tested |
| [`research/`](research/) | Scripts and outputs from the reverse engineering process — shows HOW the solution was found |
| [`external_sources/`](external_sources/) | Raw ROM dumps read from the instrument's firmware chips — the starting point of analysis |
| [`failed_attempts/`](failed_attempts/) | Cal_RAM write approaches that were tried and didn't work, documented to prevent re-investigation |

---

## Compatibility

Tested on:
- HP 3458A with REV9 firmware, A5 REV A board, MC68HC000P8 CPU
- Windows 10, Python 3.13

Compatibility with other firmware revisions is untested. The NMI mechanism and magic word sequence are firmware-specific.

---

## License

MIT License — see [LICENSE](LICENSE).

The ROM dumps in `external_sources/` are read from a physical instrument owned by the author and are provided for research and interoperability purposes.
