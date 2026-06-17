# HP 3458A NVRAM Programozó — program

A HP 3458A NVRAM Programozó éles tkinter GUI-ja és backend moduljai.

## Fájlok

| Fájl | Szerep |
|---|---|
| `hp3458a_gui.py` | Tkinter felület — Cal_RAM tab, Settings RAM tab, Cal Riport tab, NMI debug eszközök. |
| `hp3458a_instr.py` | GPIB parancsok: MREAD/MWRITE/JSR, Cal_RAM olvasás/írás/verify (Level7 NMI mechanizmuson keresztül), Settings_RAM dump. |
| `hp3458a_calram.py` | Cal_RAM codec — mező olvasás/írás, checksum, diff, riport generálás. |
| `hp3458a_calram_decoder.py` | A Cal_RAM mezőtáblája (200+ kalibrációs mező offset/típus/név szerint). |
| `hp3458a_conn.py` | Kapcsolat réteg — TCP (Prologix GPIB-ETHERNET bridge) vagy NI-488.2 DLL közvetlen. |
| `hp3458a_tool.ini` | Mentett kapcsolódási beállítások (host/port/GPIB cím) — automatikusan létrejön első csatlakozáskor. |
| `tests/test_calram.py` | Pytest unit tesztek — hardver nélkül futtatható (checksum, diff, mező validáció). |

## Futtatás

### EXE (ajánlott, függőség nélkül)

```
dist\hp3458a_nvram_tool.exe
```

### Python forrásból

```
python hp3458a_gui.py
```

**Követelmények:** Python 3.8+, tkinter (beépített). NI-488.2 módhoz: NI-VISA vagy NI-488.2 DLL telepítve.

## Tipikus használat

1. Csatlakozás (TCP vagy NI-488.2)
2. Cal_RAM tab → **Dump (letöltés)** — 3 menetes, MD5 ellenőrzéssel
3. Mező szerkesztése dupla kattintással a listában
4. **Checksum újraszámítás** (ha checksum tartományban módosítottál)
5. **Feltöltés műszerre** (gyors blokkos mód) vagy **Szavankénti feltöltés (~1 óra)** (legbiztonságosabb)
6. **Verify (visszaolvasás)** — kötelező lépés

## Tesztek futtatása

```
cd program
pytest tests/test_calram.py -v
```

## Miért működik

A Cal_RAM (DS1220Y NVRAM) /WE lába hardveres IO latch mögött van, GPIB-ről
direktben nem érhető el. A `hp3458a_instr.py` a műszer saját Level7 NMI
mechanizmusát triggereli (4 "magic word" biztonsági ellenőrzéssel) egy
GPIB JSR backdoor + Settings_RAM-ba injektált 68000 gépi kód kombinációjával.

**Kritikus szabály bővítésnél:** a /WE ablak alatt (Level7 NMI kiszolgálása közben)
SOHA nem szabad Settings_RAM-ból olvasni — busz-konfliktust / CPU crash-t okoz.
Lásd `failed_attempts/archive_unused_calram_methods.py`.
