# HP 3458A GPIB Memory Dump — Teljes útmutató

## Hardver összefoglalás

| Komponens | Részlet |
|-----------|---------|
| Műszer | HP 3458A 8.5 digites multimeter |
| CPU | Motorola 68000/ MC68HC000 (8 MHz) |
| RTOS | pSOS (Phase One Systems) |
| GPIB adapter | NI GPIB-USB-HS (IEEE 488.1) |
| Bridge PC | 192.168.2.88:1234 (Prologix TCP bridge, NI-488.2 DLL) |
| Fejlesztő PC | Windows 10 Pro, Python 3.13 |

---

## 1. Hogyan kell csatlakozni?

### Fizikai kapcsolat

```
HP 3458A  ←[IEEE 488 kábel]→  NI GPIB-USB-HS  ←[USB]→  Bridge PC (192.168.2.88)
                                                             gpib_bridge.exe fut
                                                                    ↑ TCP 1234
                                                         Fejlesztő PC
                                                          hp3458a_cal_dump.py
```

### Bridge indítása

A bridge PC-n:
```
gpib_bridge.exe
```
(Nincs ablak — a háttérben fut. Logot a konzol ablakban ír ha `console=True`-val fordítva.)

### Kapcsolat tesztelése

A fejlesztő PC-ről:
```python
import socket
s = socket.socket()
s.connect(('192.168.2.88', 1234))
s.sendall(b'++addr 22\n')
s.sendall(b'ID?\n')
s.sendall(b'++read\n')
print(s.recv(256))  # "HP3458A,..."
```

---

## 2. Hogyan kell kiolvasni?

### Parancs

```bash
cd C:\Users\Mate\Desktop\teszt\FW
python hp3458a_cal_dump.py --bridge 192.168.2.88 --no-diff --fixed-regions
```

### Mit csinál a script?

1. **Inicializálás** (`GpibSession.__enter__`):
   - `++addr 22` — GPIB cím beállítása
   - `++read_tmo_ms 300` — T300ms NI timeout (MREAD ~10-50ms, 6x margó)
   - `++clr` — HP 3458A GPIB buffer törlése (SDC, Device Clear)
   - 1 másodperc várakozás (SDC feldolgozás)
   - `END ALWAYS, NPLC 0, NRDGS 1, TRIG HOLD, QFORMAT NUM`

2. **Dump** (3 pass az összehasonlításhoz):
   - Minden szóhoz: `MREAD {cím}` küldése GPIB-en → ASCII decimális szám visszaolvasása
   - Ha timeout/ERR: 5 retry 100ms-enként
   - Haladás: minden 200. szónál kiírva

3. **Ellenőrzés**: 3 pass MD5 összehasonlítása régiónként

4. **Mentés**: `dump_YYYYMMDD_HHMMSS/` könyvtárba

### Mappa tartalom

```
dump_20260613_213730/
├── dump_01.hex          — teljes hexdump (Pass 1)
├── dump_01.json         — teljes dump JSON-ban
├── dump_01_cal_ram.bin      — 2048 byte DS1220Y (8-bit EVEN bank)
├── dump_01_settings_ram.bin — 65536 byte DS1235
├── dump_01_vectors.bin      — 1024 byte ROM
├── dump_02*.bin / dump_03*.bin  — Pass 2, 3
└── summary.json         — hash-ek, idők
```

### Sebessége

~32 másodperc / 1000 word = ~18 perc a 35328 word-ös teljes dumphoz (1 pass).

---

## 3. Mit jelent az MREAD parancs?

```
MREAD {cím}
```

A HP 3458A firmware saját parancsa. A `{cím}` egy decimális egész, ami a Motorola 68000 busz fizikai (nem virtuális) memóriacímét jelenti.

- A firmware kiad egy 68000 MOVE.W (D{addr},D0) utasítást
- A 68000 a buszon meghajtja a cím vonalakat, aktiválja /DS-t (data strobe)
- Az adott chips /CS-e (chip select) aktiválódik, az adat megjelenik a buszon
- A firmware visszaküldi az eredményt GPIB-en ASCII decimálisban

**Unmapped cím esetén**: A 68000 Bus Error kivételt generál. A pSOS RTOS elkapja, loggol a settings_ram-ba, majd visszatér — a GPIB timeout-ol (ERR válasz).

---

## 4. A három memória régió és mit tartalmaznak

### cal_ram (0x60000–0x60FFF, DS1220Y, 2 KB)

**Statikus** — csak kalibráláskor változik. A HP 3458A mérési pontosságának alapja.

Tartalom:
- **DCV zero offsets**: minden mérési tartományhoz (100mV–1KV) front/rear terminál
- **OHM zero offsets**: 2-wire és 4-wire (OCOMP), front/rear, 10Ω–1GΩ
- **Gain értékek**: DCV, OHM, DCI minden tartományhoz
- **DAC értékek**: VOS DAC, precharge DAC, mc DAC, AC offset DAC-ok
- **Hőmérséklet referenciák**: kalibrálás pillanatának hőmérséklete
- **ACAL értékek**: utolsó automatikus kalibráció parameterei
- **Checksumok**: Cal_Sum0, Cal_Sum1, Cal_Sum2, Cal_Sum3
- **Calnum**: hányadik kalibrálás (jelen esetben 29)
- **Destructive Overloads**: túlterhelési számláló

**Adatformátum**: IEEE 754 64-bit big-endian double (8 byte), big-endian int32/uint16/uint8.

**Olvasás (DS1220Y 8-bit chip)**:
- A chip a D15–D8 vonalakon ad adatot (EVEN bank, 16-bites buszra illesztve)
- Minden MREAD WORD HIGH byte-ja = valódi adat, LOW byte = 0xB9 (lebegő)
- A dump script csak a HIGH byte-okat menti (`cal_ram.bin`)

### settings_ram (0x120000–0x12FFFF, DS1235, 64 KB)

**Dinamikus** — futás közben folyamatosan változik. Pillanatképet ad a műszer állapotáról.

Tartalom:
- **0x120000**: Magic bytes `55 55 AA AA` (HP 3458A boot szignál)
- **0x12000C**: pSOS crash log (utolsó kivétel PC és típusa)
- **0x12004C–0x1201xx**: 68000 JMP abs.l vektortábla (~33 RTOS interrupt vektor)
- **0x120A4C**: VFD display buffer (256 byte — mit mutat a kijelző)
- **0x120DAE**: Utolsó ADC mérési eredmény ASCII floatként
- **0x120E38**: Math memória értékek (`RMEM 1= ...`)
- **0x120F0A–**: Firmware hibaüzenet stringek (RAM-ba másolt ROM konstansok)
- **0x121B10–0x121C81**: DEFKEY F0–F9 frontpanel makrók (10 × 41 byte)
- **0x121CB0–**: Tömörített parancs/state history (NPLC, TARM, TRIG, CAL stb.)
- **0x12711C, 0x12B018**: STATE0 blokkok (műszer üzemmód snapshot)

### vectors (0x000000–0x0003FF, ROM, 1 KB)

**Statikus** — ROM, nem változik. A 68000 processzor exception vector tábla.

- 0x000000: Initial SSP (supervisor stack pointer)
- 0x000004: Initial PC (reset vector)
- 0x000008–: Bus Error, Address Error, Illegal Instruction stb. vektorok
- 0x000064–: GPIB interrupt, timer interrupt stb.

---

## 5. Hogyan kell dekódolni?

### cal_ram decoder

```bash
python hp3458a_calram_decoder.py
# Automatikusan a legfrissebb dump_XXXXX/dump_01_cal_ram.bin-t olvassa

python hp3458a_calram_decoder.py dump_20260613_213730/dump_01_cal_ram.bin
# Konkrét fájl
```

Kimenet: minden mező neve, absolute + relative offsetje, hex, és értéke.

**Összefoglaló példa** (a mi műszerünkre):
```
40Kohm reference       : 4.0000152839497E+04   (40000.15 Ω — belső referencia ellenállás)
7Vdc reference         : 7.1779483686781E+00   (7.1779 V — belső feszültség referencia)
dcv zero front 100mV   : -9.0835000000000E-04  (-0.9 mV offset)
dcv gain 10V           : 2.9693194500000E-02   (≈ 1/33.7 — erősítési tényező)
Calnum                 : 29                    (29. kalibrálás)
Cal_AcalSecure         : 0                     (0 = nincs kalibrálási zár)
```

### settings_ram decoder

```bash
python hp3458a_settings_decoder.py
# Automatikusan a legfrissebb dump_01_settings_ram.bin-t olvassa
```

**Példa kimenetek**:
```
Crash log: "#PC=017BEA,072000    08-Bus Error---"
  -> MREAD scan mellékterméke — unmapped cím Bus Error-t okoz

ADC buffer   : "5.256766142E-07"     (utolsó mérés: ~0.53 nA)
Math memória : "RMEM 1=  4.99918556E+00"  (RMEM 1 = ~5.0000 V)
Display      : ".      mV DC"        (mV DC mód, értéket mutat)
DEFKEY F0-F9 : mind üres             (gyári alapértelmezés)
```

---

## 6. Stabilitás és konzisztencia ellenőrzése

A dump script 3 passot csinál és MD5-öt számol régiónként:

| Régió | Elvárás |
|-------|---------|
| cal_ram | 3/3 azonos ← **MINDIG ezt kell ellenőrizni** |
| vectors (ROM) | 3/3 azonos |
| settings_ram | Minden pass más — ez normális |

Ha a cal_ram pass-ok különböznek: hibás olvasás vagy a műszer kalibráláson esett át közben.

### Cal_ram referencia összehasonlítás

```powershell
# Ha a 3 pass egyezik, összehasonlítás a referenciával:
$a = (Get-FileHash "dump_20260613_213730\dump_01_cal_ram.bin" -Algorithm MD5).Hash
$b = (Get-FileHash "C:\Users\Mate\Desktop\teszt\FRAM\image_gpib olvasott.bin" -Algorithm MD5).Hash
if ($a -eq $b) { "EGYEZIK" } else { "ELTÉR: $a vs $b" }
```

---

## 7. Bridge architektúra

```
hp3458a_cal_dump.py          gpib_bridge.py (Windows, 192.168.2.88)
    │                              │
    │  TCP socket (port 1234)      │
    │  Prologix-kompatibilis       │
    │  szöveg protokoll            │  NI-488.2 ctypes
    │ ──────────────────────────>  │ ─────────────────> NI GPIB-USB-HS
    │                              │                         │
    │  ++addr 22                   │  ni_open()              │  GPIB
    │  ++read_tmo_ms 300           │  ni_write()             │  IEEE 488.1
    │  ++clr                       │  ni_read()              │ ─────────────>
    │  MREAD 393216                │  ni_close()             │        HP 3458A
    │  ++read                      │                         │        GPIB addr 22
    │ <──────────────────────────  │ <────────────────  ("393216\r\n")
    │  "393216"                    │  rstrip(\x00).decode()
```

### Kritikus beállítások

| Beállítás | Érték | Miért |
|-----------|-------|-------|
| `++read_tmo_ms 300` | T300ms (~300ms) | MREAD 10-50ms → 6x margó; unmapped Bus Error ~300ms-es timeout = gyors retry |
| Socket timeout | 30s | 5 retry × 300ms << 30s |
| `++clr` + 1s sleep | init előtt kötelező | HP 3458A GPIB output buffer törlése (SDC) |
| `rstrip(b'\x00')` | ni_read()-ban | ibcnt stale érték: előző ibrd méretét adja vissza → null byte padding |

---

## 8. Ismert problémák és megoldásaik

### "MREAD no valid response"
- **Ok**: 5 retry mind kudarcot vallott
- **Megoldás**: ellenőrizd a bridge kapcsolatot, az `++read_tmo_ms` beállítást

### Null byte-ok a válaszban (`\x00\x00\x00...`)
- **Ok**: NI-488.2 ibcnt stale értéket ad vissza (előző ibrd mérete marad)
- **Megoldás**: `raw.rstrip(b'\x00')` a `ni_read()`-ban — ez már be van építve

### "TimeoutError: timed out" a sendall()-ban
- **Ok**: Bridge ibrd timeout (unmapped cím Bus Error) + socket timeout ütközés
- **Megoldás**: socket timeout 10s → 30s; `mread_word()` `TimeoutError`-t retry-ol

### settings_ram pass-ok különböznek
- **Ez normális** — a DS1235 tartalmaz dinamikusan változó adatokat (mérési eredmény, RTOS státusz)
- A cal_ram-ot és vectors-t kell nézni — azoknak stabilnak kell lenniük

### HP 3458A "CAL NVRAM ERROR" hibaüzenet
- A cal_ram checksum hibás → `hp3458a_calram_decoder.py` futtatása megmutatja a Cal_Sum mezőket
- Ha a dump OK de a műszer panaszkodik: időzítési/kompatibilitási probléma (ld. FRAM howto)

---

## 9. Fájl referencia

| Fájl | Leírás |
|------|--------|
| `hp3458a_cal_dump.py` | Fő dump script (3 pass, 35328 word) |
| `hp3458a_calram_decoder.py` | Cal RAM decoder (200+ mező) |
| `hp3458a_settings_decoder.py` | Settings RAM decoder (dinamikus tartalom) |
| `tests/test_hp3458a_dump.py` | 42 unit teszt |
| `gpib_bridge.py` / `.exe` | Prologix TCP bridge |
| `dump_20260613_213730/` | Legfrissebb sikeres dump |
| `FRAM/image_gpib olvasott.bin` | Cal RAM referencia (2048 byte) |
| `FRAM/image_gpib olvasott_decoded.txt` | Decoded referencia (emberi olvasható) |
| `FRAM/howto.txt` | FRAM adapter (FM18W08 + Pico) útmutató |
