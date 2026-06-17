"""ARCHÍV — nem használt / nem bizonyítottan működő cal_ram írási metódusok.

Ezeket a `HP3458A` osztály metódusait 2026-06-16-án vettük ki a production
`hp3458a_instr.py`-ból, mert vagy soha nem voltak GUI-gombhoz kötve, vagy a
gomb most már egy másik, bizonyítottan biztonságos mechanizmust hív.

KÖZÖS GYÖKÉROK, amiért ezek mind kockázatosak: a `_write_loop_callback()`
a Level7 NMI handler ÁLTAL HÍVOTT callback-en belül futtat egy DBRA-ciklust,
ami `MOVE.W (A1)+,D2`-vel a /WE (write-enable) ablak alatt olvas
settings_RAM-ból. Ez buszkonfliktust / CPU crash-t okozhat — lásd a
[[feedback-bulk-callback-unsafe]] memóriát. Ezzel szemben a megtartott,
működő metódusok (`write_calram_word`, `write_calram_words_list`,
`write_calram_bin_safe`, `write_calram_bin_fast`) SOHA nem olvasnak
forrás-RAM-ot a callbacken belül — az adat mindig D2-ben van már, mielőtt
az NMI elsül.

Ha ezek közül bármelyikre a jövőben mégis szükség lenne (pl. egy "folytasd
a blokkos feltöltést onnan, ahol elakadt" funkció), újra kell írni a
biztonságos (single-word callback + főkódban futó, számolt displacement-ű)
mintára — NE ezt a fájlt élesítsd vissza változatlanul.

---

## write_calram_bin() — KÍSÉRLETI, instabil bulk (1 JSR / 1024 szó)

Soha nem volt GUI-gombhoz kötve ebben a formában. A `_write_loop_callback()`-et
használja (lásd fent) + a pSOS staging-korrupció workaroundját
(`_make_adjusted_upload` / `_atomic_fix_pairs_and_cs`) — ez utóbbi kettő
ÖNMAGÁBAN korrekt ötlet (adjusted checksum + atomikus utófix), de csak ezzel
a bulk metódussal együtt volt használva, ezért együtt archiváljuk.

```python
def write_calram_bin(self, data: bytes, progress_cb=None, stop_event=None) -> bool:
    \"\"\"Teljes 2048-byte cal_ram feltöltése egyetlen NMI-vel.

    1. fázis (0→60%): 1024 word MWRITE settings_ram DATA_BASE-be (~1 perc)
    2. fázis (60→80%): loop callback + főkód MWRITE
    3. fázis (80→100%): JSR → NMI → 1024×MOVEP.W → minden byte megírva

    DATA_BASE/CODE_BASE/CB_BASE a settings_ram megerősített nulla zónájában
    vannak (0x127196–0x12A885). Power cycle után SRAM marad, de a
    magic word-ök (0x121780 stb.) törlődnek → véletlen NMI nem trigger.
    \"\"\"
    assert len(data) == CAL_RAM_SIZE

    # Fázis 1: source data MWRITE settings_ram-ba
    # Az adjusted_data a pSOS-korrupt értékekre számított CS1-et tartalmazza,
    # így a firmware a NMI után érvényes checksumot lát és NEM pánikol.
    # Magic word-öket NEM itt állítjuk — a firmware felülírhatja a hosszú
    # MWRITE fázis alatt. Közvetlenül JSR előtt kerülnek beállításra.
    # Minden word = cal_ram[2i] << 8 | cal_ram[2i+1]
    # MOVEP.W: D2[15:8]→(a0)=cal_ram[2i], D2[7:0]→(a0+2)=cal_ram[2i+1]
    adjusted_data = self._make_adjusted_upload(data)
    for i in range(1024):
        if stop_event and stop_event.is_set():
            return False
        word = (adjusted_data[i * 2] << 8) | adjusted_data[i * 2 + 1]
        self.mwrite(DATA_BASE + i * 2, word)
        if progress_cb and i % 32 == 0:
            progress_cb(i, 1024, f'Adat írás {i}/1024 word')

    if stop_event and stop_event.is_set():
        return False

    # Fázis 2: magic words + callback + főkód (közvetlenül JSR előtt)
    if progress_cb:
        progress_cb(1024, 1024, 'Magic words + callback írás...')
    self._set_magic_words()   # FONTOS: 1024 MWRITE után, nem előtte!
    self._write_loop_callback()

    db = DATA_BASE
    main_code = [
        0x4E45,                                   # trap #5  (SR→$121858, int mask↑)
        0x207C, 0x0006, 0x0000,                   # movea.l #0x60000, a0  (cal_ram start)
        0x227C, (db >> 16) & 0xFFFF, db & 0xFFFF, # movea.l #DATA_BASE, a1
        0x303C, 0x03FF,                            # move.w #1023, d0  (1024 iter)
        0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,  # movea.l #CB_BASE, a4
        0x23CC, 0x0012, 0x1852,                    # move.l a4, $121852
        0x33FC, 0x0000, 0x0012, 0x1856,            # move.w #0, $121856
        0x1C39, 0x0012, 0x185A,                    # move.b $12185A, d6
        0x0046, 0x0080,                            # ori.w #$80, d6
        0x13C6, 0x000C, 0x0001,                    # NMI TRIGGER
        0x3C3C, 0x0009,                            # move.w #9, d6  (timing wait)
        0x57CE, 0xFFFE,                            # dbeq d6, *  (IO latch delay)
        0x4E75,                                    # rts (NMI már lefutott)
    ]
    self._mwrite_words(CODE_BASE, main_code)

    # Fázis 3: futtatás
    if progress_cb:
        progress_cb(0, 1, 'JSR futtatás (NMI -> 1024xMOVEP.W)...')
    self.flush_errors()
    err = self.jsr(CODE_BASE, wait=3.0)
    ok = 'NO ERROR' in err
    if progress_cb:
        progress_cb(1, 1, 'JSR kész' if ok else f'Hiba: {err}')

    # Fázis 4: atomikus fix — 3 adatbyte + CS1 egyetlen NMI-vel korrigálva
    # Az adjusted_data pSOS-kompatibilis CS1-el ment fel, firmware nem pánikolt.
    # Most az eredeti (helyes) adatokkal és helyes CS1-el írjuk felül atomikusan.
    if ok:
        ok = self._atomic_fix_pairs_and_cs(data, progress_cb)

    return ok
```

### _make_adjusted_upload — csak write_calram_bin() segédje

```python
def _make_adjusted_upload(self, data: bytes) -> bytes:
    \"\"\"Feltöltési adat előkészítése: pSOS-korrupciónak megfelelő checksummal.

    A pSOS felülírja a 3 staging word low byte-ját:
      cal_RAM[947]=0x02, cal_RAM[1019]=0x02, cal_RAM[1023]=0x04

    Ezért a feltöltési adatban CS1-et EZEKRE az értékekre számítjuk.
    A bulk NMI után a firmware helyes checksumot talál → nem pánikol.
    Ezután egyetlen 4-pair NMI-vel korrigáljuk a 3 bájtot + CS1-et.
    \"\"\"
    upload = bytearray(data)

    # Szimulált korrupció: pSOS a HIGH BYTE-ot írja (páros cím = pair_i*2)
    for pair_i, psos_hi, phys in _BULK_BUGGY_PAIRS:
        upload[pair_i * 2] = psos_hi   # HIGH byte cseréje (NEM +1!)

    # CS1 újraszámítás a korrupt adatokra
    _, cs1_off, cs1_start, cs1_end, cs1_seed = _CAL_SUMS[1]
    adjusted_cs1 = self._compute_calsum(bytes(upload), cs1_start, cs1_end, cs1_seed)
    upload[cs1_off]     = (adjusted_cs1 >> 8) & 0xFF
    upload[cs1_off + 1] = adjusted_cs1 & 0xFF

    return bytes(upload)
```

### _atomic_fix_pairs_and_cs — csak write_calram_bin() segédje

```python
def _atomic_fix_pairs_and_cs(self, data: bytes, progress_cb=None) -> bool:
    \"\"\"Egyetlen NMI-vel korrigálja a 3 bugos pair-t ÉS CS1-et.

    Atomikus: a firmware soha nem lát érvénytelen checksumot,
    mert a 3 bájt és CS1 egyetlen Level7 NMI alatt változik.

    Callback (CB_BASE): 4× (move.w (a1)+, d2; movea.l #phys, a0; movep.w d2, $0(a0)) + rts
    Staging (DATA_BASE, csak 4 word): [pair473_word, pair509_word, pair511_word, cs1_word]
    \"\"\"
    # Correct CS1 a valódi (nem korrupt) adatokra
    _, cs1_off, cs1_start, cs1_end, cs1_seed = _CAL_SUMS[1]
    correct_cs1 = self._compute_calsum(data, cs1_start, cs1_end, cs1_seed)

    # CS1 fizikai cím a cal_RAM-ban: pair = cs1_off//2, phys = CAL_RAM_BASE + pair*4
    cs1_pair = cs1_off // 2
    cs1_phys = CAL_RAM_BASE + cs1_pair * 4

    # 4 javítandó pair: 3 adat + CS1
    fix_pairs = [
        (pair_i, phys, (data[pair_i * 2] << 8) | data[pair_i * 2 + 1])
        for pair_i, psos_lo, phys in _BULK_BUGGY_PAIRS
    ] + [(cs1_pair, cs1_phys, correct_cs1)]

    if progress_cb:
        progress_cb(0, 1,
                    f'Atomikus fix: 3 pair + CS1=0x{correct_cs1:04X} '
                    f'egyetlen NMI-ben...')

    # Staging: 4 word az adatokkal (DATA_BASE elejére, 8 byte)
    for i, (pair_i, phys, word) in enumerate(fix_pairs):
        self.mwrite(DATA_BASE + i * 2, word)

    # Sparse-4 callback (CB_BASE, 25 word = 50 byte)
    # 4× blokk: move.w (a1)+,d2 ; movea.l #phys,a0 ; movep.w d2,$0(a0)
    # Záró: rts
    cb = []
    for pair_i, phys, word in fix_pairs:
        ph = phys & 0xFFFFFFFF
        cb += [
            0x3419,                              # move.w (a1)+, d2
            0x207C, (ph >> 16) & 0xFFFF, ph & 0xFFFF,  # movea.l #phys, a0
            0x0588, 0x0000,                      # movep.w d2, $0(a0)
        ]
    cb.append(0x4E75)  # rts
    self._mwrite_words(CB_BASE, cb)

    # Főkód: a1 = DATA_BASE, setup, NMI trigger
    db = DATA_BASE
    self._set_magic_words()
    main_code = [
        0x4E45,                                      # trap #5
        0x227C, (db >> 16) & 0xFFFF, db & 0xFFFF,   # movea.l #DATA_BASE, a1
        0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,  # movea.l #CB_BASE, a4
        0x23CC, 0x0012, 0x1852,                      # move.l a4, $121852
        0x33FC, 0x0000, 0x0012, 0x1856,              # move.w #0, $121856
        0x1C39, 0x0012, 0x185A,                      # move.b $12185A, d6
        0x0046, 0x0080,                              # ori.w #$80, d6
        0x13C6, 0x000C, 0x0001,                      # NMI TRIGGER
        0x3C3C, 0x0009,                              # timing wait
        0x57CE, 0xFFFE,
        0x4E75,                                      # rts
    ]
    self._mwrite_words(CODE_BASE, main_code)

    self.flush_errors()
    err = self.jsr(CODE_BASE, wait=2.0)
    ok = 'NO ERROR' in err

    if progress_cb:
        status = 'OK' if ok else f'HIBA: {err}'
        progress_cb(1, 1, f'Atomikus fix JSR: {status}')
    return ok
```

---

## write_calram_bin_chunked() — a "Csoportos feltöltés"/"10k unrolled" backendje

2026-06-16: a GUI gombja (mindkét fájlban) `write_calram_bin_safe()`-re lett
átkötve (1 word/NMI, checksum utoljára) — lásd [[feedback-dbra-displacement-bug]].
Ez a függvény innentől sehonnan nem hívott.

```python
def write_calram_bin_chunked(self, data: bytes, chunk_size: int = 32,
                              progress_cb=None, stop_event=None) -> bool:
    \"\"\"2KB cal_ram feltöltése kétfázisban.

    1. fázis: teljes 1024 szó MWRITE → DATA_BASE staging terület (stabil, egyszer)
    2. fázis: chunk-onként NMI transfer, A1 pointer a DATA_BASE-n belül tolódik

    Az A1 = DATA_BASE + start_word*2 minden chunk-ban a saját szavakra mutat —
    nincs per-chunk adatfeltöltés. Minden JSR előtt friss main_code + flush_errors.
    Becsült idő (chunk_size=32): ~4 perc Phase1 + ~5 perc Phase2 ≈ 9 perc.
    \"\"\"
    assert len(data) == CAL_RAM_SIZE
    total_words = CAL_RAM_SIZE // 2   # 1024
    chunks = (total_words + chunk_size - 1) // chunk_size

    # ── Phase 1: teljes adatfeltöltés DATA_BASE staging területre ───────
    self.flush_errors()
    for i in range(total_words):
        if stop_event and stop_event.is_set():
            return False
        w = (data[i * 2] << 8) | data[i * 2 + 1]
        self.mwrite(DATA_BASE + i * 2, w)
        if progress_cb and i % 64 == 0:
            progress_cb(i, total_words * 2,
                        f'1. fazis: {i}/{total_words} szo -> DATA_BASE')

    if progress_cb:
        progress_cb(total_words, total_words * 2, '1. fázis kész, callback írás...')

    # Loop callback egyszer — stabil a Phase1 után
    self._write_loop_callback()

    # ── Phase 2: chunk-onként NMI transfer ──────────────────────────────
    for chunk_idx in range(chunks):
        if stop_event and stop_event.is_set():
            return False

        start_word = chunk_idx * chunk_size
        end_word   = min(start_word + chunk_size, total_words)
        count      = end_word - start_word

        cal_phys = CAL_RAM_BASE + start_word * 4     # 0x60000 + start*4
        a1_addr  = DATA_BASE   + start_word * 2      # staging offset

        if progress_cb:
            progress_cb(total_words + start_word, total_words * 2,
                        f'2. fázis chunk {chunk_idx + 1}/{chunks}: '
                        f'{count} szó, byte#{start_word * 2}–{end_word * 2 - 1}')

        main_code = [
            0x4E45,                                                   # trap #5
            0x207C, (cal_phys >> 16) & 0xFFFF, cal_phys & 0xFFFF,   # movea.l #cal_phys, a0
            0x227C, (a1_addr >> 16)  & 0xFFFF, a1_addr  & 0xFFFF,   # movea.l #a1_addr, a1
            0x303C, count - 1,                                        # move.w #count-1, d0
            0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,        # movea.l #CB_BASE, a4
            0x23CC, 0x0012, 0x1852,                                   # move.l a4, $121852
            0x33FC, 0x0000, 0x0012, 0x1856,                          # move.w #0, $121856
            0x1C39, 0x0012, 0x185A,                                   # move.b $12185A, d6
            0x0046, 0x0080,                                           # ori.w #$80, d6
            0x13C6, 0x000C, 0x0001,                                   # NMI trigger
            0x3C3C, 0x0009,                                           # timing wait
            0x57CE, 0xFFFE,                                           # dbeq d6, *
            0x4E75,                                                   # rts
        ]

        self._set_magic_words()
        self.flush_errors()
        self._mwrite_words(CODE_BASE, main_code)

        err = self.jsr(CODE_BASE, wait=1.5)
        if 'NO ERROR' not in err:
            if progress_cb:
                progress_cb(total_words + start_word, total_words * 2,
                            f'HIBA chunk {chunk_idx + 1}: {err}')
            return False

    if progress_cb:
        progress_cb(total_words * 2, total_words * 2,
                    f'Kész: {chunks} chunk ({chunk_size} szó/NMI)')
    return True
```

---

## retry_calram_bulk_jsr() — JSR-újrapróbálás meglévő staginggel

2026-06-16: a GUI "JSR Újrapróbálás" gombja törölve. Az eredeti szándék
("ha a staging sikerült, de a JSR hibázott, ne kelljen újra a lassú
staginget végigvárni") továbbra is hasznos lehet, de ez az implementáció
a régi, egy-darab 1024-szavas `_write_loop_callback()` mechanizmust
futtatja — NEM ugyanazt, mint amit a javított `write_calram_bin_fast()`
valójában használ (128-szavas blokkok, számolt DBRA displacement). Ha
"retry"-ként hívnád a write_calram_bin_fast egy hibázott blokkja után, egy
teljesen más, kockázatosabb útvonalat futtatna le, mint ami a staginget
végezte — nem koherens. Ha ÚJRA kell egy ilyen funkció, a write_calram_bin_fast
blokkos mechanizmusára épülve kell megírni (folytatás egy adott start_word-től),
nem ezt felélesztve.

```python
def retry_calram_bulk_jsr(self, progress_cb=None) -> bool:
    \"\"\"JSR-újrapróbálás meglévő DATA_BASE tartalommal.

    Kihagyja az 1024 MWRITE fázist — a settings_RAM (battery-backed)
    megőrzi az előző feltöltés adatát. Csak kód+callback újraírás + JSR.
    Hasznos ha az adatfázis sikerült de a JSR hibás volt.
    \"\"\"
    if progress_cb:
        progress_cb(0, 3, 'Hibavár törlése...')
    self.flush_errors()

    if progress_cb:
        progress_cb(1, 3, 'Magic words + callback + főkód írása...')
    self._set_magic_words()
    self._write_loop_callback()

    db = DATA_BASE
    main_code = [
        0x4E45,                                   # trap #5  (SR→$121858)
        0x207C, 0x0006, 0x0000,                   # movea.l #0x60000, a0
        0x227C, (db >> 16) & 0xFFFF, db & 0xFFFF, # movea.l #DATA_BASE, a1
        0x303C, 0x03FF,                            # move.w #1023, d0
        0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,  # movea.l #CB_BASE, a4
        0x23CC, 0x0012, 0x1852,                    # move.l a4, $121852
        0x33FC, 0x0000, 0x0012, 0x1856,            # move.w #0, $121856
        0x1C39, 0x0012, 0x185A,                    # move.b $12185A, d6
        0x0046, 0x0080,                            # ori.w #$80, d6
        0x13C6, 0x000C, 0x0001,                    # NMI TRIGGER
        0x3C3C, 0x0009,                            # timing wait
        0x57CE, 0xFFFE,
        0x4E75,                                    # rts
    ]
    self._mwrite_words(CODE_BASE, main_code)

    if progress_cb:
        progress_cb(2, 3, 'JSR futtatás (NMI -> 1024xMOVEP.W)...')
    err = self.jsr(CODE_BASE, wait=3.0)
    ok = 'NO ERROR' in err
    if progress_cb:
        progress_cb(3, 3, 'Kész' if ok else f'Hiba: {err}')
    return ok
```

---

## _write_loop_callback() — a közös, kockázatos callback-építő

Csak a fenti három metódus használta. Miután mindhármat archiváltuk, ez is
dead code lett a production fájlban.

```python
def _write_loop_callback(self):
    \"\"\"Bulk callback: 1024×movep.w loop  — d0 word-öt ír a0→-ba a1-ből.

    Kód (14 byte = 7 word):
      loop: move.w (a1)+, d2       ; 3419
            movep.w d2, $0(a0)     ; 0588 0000
            addq.w #4, a0          ; 5848
            dbra d0, loop          ; 51C8 FFF4  (displacement = 0-12 = -12)
            rts                    ; 4E75
    \"\"\"
    self._mwrite_words(CB_BASE, [
        0x3419,        # move.w (a1)+, d2
        0x0588, 0x0000,# movep.w d2, $0(a0)
        0x5848,        # addq.w #4, a0
        0x51C8, 0xFFF4,# dbra d0, -12 (back to loop start)
        0x4E75,        # rts
    ])
```

**Megjegyzés (2026-06-16 felfedezés):** ennek a callbacknek a DBRA
displacementje ÖNMAGÁBAN is hibás (-12 helyett -10 (0xFFF6) kellene a
loop_start(byte0)/dbra_opcode(byte8) alapján) — ugyanaz a hibaosztály,
mint amit a `write_calram_bin_fast`-ban javítottunk. Mivel ez a callback
így is, úgy is archiválásra kerül (a /WE-alatti RAM-olvasás miatt), a
displacement bugot NEM javítottuk ki — csak dokumentáljuk, hogy ha valaha
ezt a mintát felélesztenéd, ez is hibás.
"""
