"""HP 3458A műszer parancsok — MREAD, MWRITE, JSR, dump, cal_ram írás, verify."""
import time
import threading

from hp3458a_conn import BaseConn, ConnError

CAL_RAM_BASE  = 0x60000
CAL_RAM_SIZE  = 2048
SETTINGS_BASE = 0x120000
SETTINGS_SIZE = 0x10000  # 64KB

# Settings_ram szabad területek az injektált kódhoz / adathoz
# Megerősített szabad (null) zóna: 0x127196–0x12A885 (~14KB, dump alapján)
CODE_BASE = 0x12A000   # ~64 byte főkód    (volt: 0x12E000 — calibráció cache)
CB_BASE   = 0x12A100   # ~20 byte callback (volt: 0x12E100 — calibráció cache)
DATA_BASE = 0x127200   # 2048 byte staging (volt: 0x12D000 — calibráció cache)

# Level7 NMI magic word-ök (power cycle után 0x0000 → MWRITE-tal beállítandó)
MAGIC_WORDS = [
    (0x121780, 0xDEAF),
    (0x120C90, 0xBAD1),
    (0x121782, 0x0ACE),
    (0x120C92, 0xBEAD),
]

# Level7 NMI handler settings_ram munkaterülete (lásd [[feedback-calram-we-mechanism]]).
# Ezeket a címeket korábban literálként (0x0012, 0x1852 stb.) írtuk be minden
# main_code listába külön-külön — most egy helyen vannak névvel ellátva.
CALLBACK_PTR_ADDR = 0x121852   # NMI handler ide olvassa be a callback hívási cím-pointert (32-bit, 2 word)
SUCCESS_FLAG_ADDR = 0x121856   # NMI handler 1-re írja siker esetén
SAVED_SR_ADDR     = 0x121858   # TRAP#5 ISR ide menti az SR-t, NMI handler ezt állítja vissza
WE_CLOSE_VAL_ADDR = 0x12185A   # /WE close érték (HIGH byte); | 0x80 = /WE open
NMI_TRIGGER_PORT  = 0xC0001    # IO latch port; bit7 írása triggereli a Level7 NMI-t


# Cal_RAM checksum szavak byte-offsetjei a cal_ram-ban.
# 2026-06-16: ITT csak az OFFSETEK kellenek (melyik szavakat kell utoljára,
# külön blokkban írni — lásd feedback_checksum_bypass: a pSOS háttér-
# ellenőrzés miatt a checksum-szó és a hozzá tartozó adat egy chunkban
# íródjon). A TÉNYLEGES checksum-érték már a `data`-ban helyesen ott van —
# azt a GUI codec (hp3458a_calram.py) számolja a firmware-szerű, több
# tartomány + dump-specifikus flag_count modellel (lásd cs.txt), NEM ez a
# fájl. A korábbi itt élt fix seed-es újraszámítás KIVÉVE, mert csak 2 saját
# dumpra illeszkedett — lásd research/python/verify_checksum_hypothesis.py.
_CAL_SUM_OFFSETS = [0x1BC, 0x59C, 0x5C8, 0x624]  # CS0, CS1, CS2, CS3

# A pSOS felülírja e 3 staging word HIGH BYTE-ját a ~3 perces MWRITE alatt.
# pSOS a PÁROS CÍM-re ír (DATA_BASE + pair_i*2 = HIGH byte pozíció):
#   0x1275B2 = DATA_BASE+946  → cal_RAM[946] HIGH BYTE (pair 473)
#   0x1275FA = DATA_BASE+1018 → cal_RAM[1018] HIGH BYTE (pair 509)
#   0x1275FE = DATA_BASE+1022 → cal_RAM[1022] HIGH BYTE (pair 511)
# Az érintett byte-ok a CS1 tartományban vannak (0x1BE-0x59B = 446-1435).
# pair_i, pSOS által beírt HIGH byte érték, fizikai even cím
_BULK_BUGGY_PAIRS = [
    (473, 0x02, CAL_RAM_BASE + 473 * 4),   # cal_ram[946] HIGH BYTE → 0x02, phys=0x60764
    (509, 0x02, CAL_RAM_BASE + 509 * 4),   # cal_ram[1018] HIGH BYTE → 0x02, phys=0x607F4
    (511, 0x04, CAL_RAM_BASE + 511 * 4),   # cal_ram[1022] HIGH BYTE → 0x04, phys=0x607FC
]


class HP3458A:
    def __init__(self, conn: BaseConn):
        self._conn = conn

    # ── Alap kommunikáció ────────────────────────────────────────────────────

    def send(self, cmd: str):
        self._conn.send(cmd)

    def query(self, cmd: str, tmo: float = 5.0) -> str:
        return self._conn.query(cmd, tmo)

    # ── Init / azonosítás ────────────────────────────────────────────────────

    def gpib_clear(self):
        """GPIB Device Clear (SDC) — Prologix ++clr / ibclr. Teli buffer törlése."""
        self._conn.gpib_clear()

    def assert_instrument_present(self) -> str:
        """SDC + ID? ellenőrzés — KÖTELEZŐ minden cal_ram írás ELEJÉN.

        2026-06-16 felfedezés: a szoftver korábban "sikeresnek" jelzett egy
        teljes word-feltöltést úgy is, hogy a műszer KI volt kapcsolva, és
        csak a GPIB bridge futott — a bridge/busz canned vagy lebegő
        válaszokat adott, amiket a kód hibásan érvényes ERRSTR?="NO ERROR"
        válasznak vett. Ez minden bizonnyal hozzájárult egy cal_ram
        korrupcióhoz (RAM-teszt-szerű mintázat egy feltöltés után).

        Ezért MINDEN írási útvonal elején SDC-t küldünk, és megköveteljük,
        hogy az ID? válasz tartalmazza a "HP3458A" karakterláncot — csak
        ekkor garantált, hogy egy valódi, válaszoló műszerrel beszélünk.
        """
        self._conn.gpib_clear()  # SDC: GPIB buffer flush
        resp = self.query('ID?', tmo=5.0)
        if 'HP3458A' not in resp:
            raise RuntimeError(
                f'A műszer nem válaszolt megfelelően (ID?={resp!r}). '
                'Ellenőrizd, hogy be van-e kapcsolva és valóban a GPIB '
                'buszon van-e, mielőtt cal_ram írást indítasz!'
            )
        return resp

    def init(self):
        """Műszer-jelenlét ellenőrzés + alapállapot: PRESET NORM + END ALWAYS + BEEP 1."""
        self.assert_instrument_present()
        self.send('PRESET NORM')
        time.sleep(0.8)
        self.send('END ALWAYS')
        time.sleep(0.2)
        self.send('BEEP 1')    # KÖTELEZŐ az MREAD-hez!
        time.sleep(0.2)
        self.query('ERRSTR?')

    def test_id(self) -> str:
        """Lekérdezi az azonosítót (ID?). Sikeres kapcsolat esetén: 'HP3458A,...'"""
        return self.query('ID?', tmo=5.0)

    def errstr(self) -> str:
        return self.query('ERRSTR?', tmo=3.0)

    # ── MREAD / MWRITE ───────────────────────────────────────────────────────

    def mread_word(self, phys: int, retries: int = 3) -> int:
        """MREAD decimális cím → 16-bit word. LOW byte = 0xB9 (lebegő busz a cal_ram-nál)."""
        for attempt in range(retries):
            try:
                r = self.query(f'MREAD {phys}', tmo=2.0)
                return int(float(r)) & 0xFFFF
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(0.2)
        return 0

    def mread_hi(self, phys: int) -> int:
        """Cal_RAM byte olvasás: MREAD word HIGH byte = érvényes adat."""
        return (self.mread_word(phys) >> 8) & 0xFF

    def mwrite(self, phys: int, value: int):
        """MWRITE decimális cím, előjeles 16-bit érték."""
        v = value & 0xFFFF
        signed = v if v <= 32767 else v - 65536
        self.send(f'MWRITE {phys},{signed}')
        time.sleep(0.05)

    def _mwrite_words(self, base: int, words: list):
        for i, w in enumerate(words):
            self.mwrite(base + i * 2, w)

    # ── JSR ──────────────────────────────────────────────────────────────────

    def flush_errors(self, max_iter: int = 8) -> str:
        """ERRSTR? ismétlése amíg 'NO ERROR' — queued hibák törlése JSR előtt.
        HP 3458A error queue max ~8 bejegyzés → 8 iteráció elegendő.
        """
        last = ''
        for _ in range(max_iter):
            last = self.errstr()
            if 'NO ERROR' in last:
                return last
            time.sleep(0.1)
        return last

    def jsr(self, addr: int, wait: float = 2.0) -> str:
        """JSR decimális cím → futtat, vár, ERRSTR? választ ad.
        flush_errors() NEM itt fut — a hívó felelőssége egyszer meghívni.
        """
        self.send(f'JSR {addr}')
        time.sleep(wait)
        return self.errstr()

    # ── NMI mechanizmus segédfüggvények ─────────────────────────────────────

    def _set_magic_words(self):
        """Level7 NMI biztonsági ellenőrzés: 4 magic word beállítása settings_ram-ba."""
        for addr, val in MAGIC_WORDS:
            self.mwrite(addr, val)

    def _write_single_callback(self):
        """Callback: movep.w d2,$0(a0); rts  — 1 word (2 byte) ír cal_ram-ba."""
        self._mwrite_words(CB_BASE, [0x0588, 0x0000, 0x4E75])

    @staticmethod
    def _callback_setup_words() -> list:
        """CB_BASE pointer beállítása + sikerjelző törlése — minden main_code eleji,
        közös blokk. Korábban 3x duplikálva volt szó szerint (write_calram_word,
        write_calram_words_list, run_block) — most egy helyen él."""
        return [
            0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,                  # MOVEA.L #CB_BASE, A4
            0x23CC, (CALLBACK_PTR_ADDR >> 16) & 0xFFFF, CALLBACK_PTR_ADDR & 0xFFFF,  # MOVE.L A4, callback_ptr
            0x33FC, 0x0000,
            (SUCCESS_FLAG_ADDR >> 16) & 0xFFFF, SUCCESS_FLAG_ADDR & 0xFFFF,      # MOVE.W #0, success_flag
        ]

    @staticmethod
    def _nmi_trigger_words() -> list:
        """A /WE nyitása + Level7 NMI trigger + timing wait — a tényleges
        cal_ram írást elindító közös szósorozat. Korábban 3x duplikálva volt
        szó szerint — most egy helyen él, lásd [[feedback-calram-we-mechanism]]
        (IO latch propagation delay → timing wait KÖTELEZŐ a trigger után)."""
        return [
            0x1C39, (WE_CLOSE_VAL_ADDR >> 16) & 0xFFFF, WE_CLOSE_VAL_ADDR & 0xFFFF,  # MOVE.B we_close, D6
            0x0046, 0x0080,                                                          # ORI.W #$80, D6
            0x13C6, (NMI_TRIGGER_PORT >> 16) & 0xFFFF, NMI_TRIGGER_PORT & 0xFFFF,    # MOVE.B D6, nmi_port
            0x3C3C, 0x0009,                                                          # MOVE.W #9, D6
            0x57CE, 0xFFFE,                                                          # DBEQ D6, *  (timing wait)
        ]

    # ── Cal_RAM WRITE: egyszeri word ─────────────────────────────────────────

    def _write_calram_word_raw(self, phys: int, word: int) -> str:
        """Egy cal_ram word írása NMI-vel; visszaadja a nyers ERRSTR? választ.

        Közös implementáció write_calram_word() és write_calram_words_list()
        alatt — ide kerül a TRAP#5 + D2 betöltés + a megosztott callback-setup
        és NMI-trigger szekvencia. NE duplikáld ezt az opcode listát máshol.
        """
        self._set_magic_words()
        self._write_single_callback()
        main_code = [
            0x4E45,                                            # trap #5  (SR→saved_sr, int mask↑)
            0x343C, word & 0xFFFF,                             # move.w #word, d2
            0x207C, (phys >> 16) & 0xFFFF, phys & 0xFFFF,      # movea.l #phys, a0
            *self._callback_setup_words(),
            *self._nmi_trigger_words(),
            0x4E75,                                            # rts  (NMI már lefutott)
        ]
        self._mwrite_words(CODE_BASE, main_code)
        return self.jsr(CODE_BASE, wait=1.5)

    def write_calram_word(self, phys: int, word: int) -> bool:
        """2 byte ír cal_ram-ba MOVEP.W-vel. phys = fizikai cím (even).

        D2[15:8] → cal_ram[phys], D2[7:0] → cal_ram[phys+2]
        Pl. cal_ram offset i → phys = 0x60000 + i*2
        """
        self.assert_instrument_present()
        self.flush_errors()
        err = self._write_calram_word_raw(phys, word)
        return 'NO ERROR' in err

    def write_calram_words_list(self, word_list: list,
                                progress_cb=None, stop_event=None) -> bool:
        """Csak a megadott word-öket írja cal_ram-ba, egyenként NMI-vel.

        word_list: [(phys_addr, word), ...]
        Lassabb mint bulk (~2s/word), de kisebb kockázat és könnyebb debug.
        """
        self.assert_instrument_present()
        self.flush_errors()
        total = len(word_list)
        for idx, (phys, word) in enumerate(word_list):
            if stop_event and stop_event.is_set():
                return False
            if progress_cb:
                progress_cb(idx, total,
                            f'Írás {idx + 1}/{total}: 0x{phys:06X} = 0x{word:04X}')
            err = self._write_calram_word_raw(phys, word)
            if 'NO ERROR' not in err:
                if progress_cb:
                    progress_cb(idx, total,
                                f'HIBA @ 0x{phys:06X}: {err}')
                return False
        if progress_cb:
            progress_cb(total, total, f'{total} word sikeresen írva')
        return True

    def test_nmi_write(self, progress_cb=None) -> tuple:
        """NMI mechanizmus teszt: első cal_ram word visszaírása (adat nem változik).

        1. MREAD 0x60000, 0x60002 → eredeti word
        2. write_calram_word(0x60000, eredeti_word)  ← NMI tesztelve
        3. MREAD → verify egyezik-e

        Visszatér: (ok: bool, detail: str)
        """
        if progress_cb:
            progress_cb(0, 3, 'NMI teszt: olvasás cal_ram[0]...')
        self.assert_instrument_present()
        hi = self.mread_hi(CAL_RAM_BASE)
        lo = self.mread_hi(CAL_RAM_BASE + 2)
        orig = (hi << 8) | lo

        if progress_cb:
            progress_cb(1, 3, f'NMI teszt: visszairas 0x{orig:04X} -> 0x{CAL_RAM_BASE:06X}')
        ok = self.write_calram_word(CAL_RAM_BASE, orig)

        if progress_cb:
            progress_cb(2, 3, 'NMI teszt: verify...')
        hi2 = self.mread_hi(CAL_RAM_BASE)
        lo2 = self.mread_hi(CAL_RAM_BASE + 2)
        got = (hi2 << 8) | lo2

        match = (got == orig)
        detail = (f'JSR={"OK" if ok else "ERR"}, '
                  f'eredeti=0x{orig:04X}, visszaolvasott=0x{got:04X}, '
                  f'{"OK" if match else "ELTERES"}')
        if progress_cb:
            progress_cb(3, 3, detail)
        return ok and match, detail

    # ── Cal_RAM WRITE: teljes 2KB, BIZTONSÁGOS mód ──────────────────────────

    def write_calram_bin_safe(self, data: bytes, progress_cb=None, stop_event=None) -> bool:
        """Teljes cal_RAM feltöltés biztonságos, 1 word/NMI módban.

        A /WE ablak alatt CSAK MOVEP.W D2,0(A0) + RTS fut — nincs RAM olvasás,
        nincs loop a callbackben. Sorrend: normál adatok → checksum wordök.

        Idő: ~30-60 perc (1024 NMI call). Megbízható — azonos mechanizmus
        mint a bizonyítottan működő egyedi word írás.
        """
        if len(data) != CAL_RAM_SIZE:
            raise ValueError(f'Méret hiba: {len(data)} byte (kell: {CAL_RAM_SIZE})')

        # Checksum mezők byte-offsetjei (utoljára írandók)
        cs_offsets = set(_CAL_SUM_OFFSETS)

        normal_pairs = []
        cs_pairs = []
        for i in range(CAL_RAM_SIZE // 2):
            phys = CAL_RAM_BASE + i * 4
            word = (data[i * 2] << 8) | data[i * 2 + 1]
            if i * 2 in cs_offsets:
                cs_pairs.append((phys, word))
            else:
                normal_pairs.append((phys, word))

        total = len(normal_pairs) + len(cs_pairs)
        if progress_cb:
            progress_cb(0, total, f'Safe feltoltes: {len(normal_pairs)} adat + {len(cs_pairs)} checksum word')

        return self.write_calram_words_list(
            normal_pairs + cs_pairs,
            progress_cb=progress_cb,
            stop_event=stop_event,
        )

    # ── Cal_RAM WRITE: teljes 2KB, GYORS belső loop mód ─────────────────────

    def write_calram_bin_fast(self, data: bytes, progress_cb=None, stop_event=None,
                              block_words: int = 128) -> bool:
        """Teljes cal_RAM feltöltés gyors, de blokkolt módban.

        Alapértelmezés: 128 word / JSR-blokk.

        Fontos pontosítás:
          - 1 CAL word = 2 byte adat.
          - 1 NMI / WE pulse továbbra is csak 1 wordöt ír.
          - Egy JSR-en belül most legfeljebb 128 egymás utáni NMI trigger fut.
          - Ez NEM a régi 1024 word / egyetlen JSR módszer.

        Miért így?
          A korábbi 1024 word / JSR túl hosszú volt: kb. 0x0230 CAL offsetig
          jutott, majd a műszer kifagyott (ráadásul az a verzió egy hibás,
          hardkódolt DBRA-displacementet is tartalmazott: -32 helyett -30
          kellett volna, ami "114,'CPU EXCEPTION -- 4'" illegális utasítás
          hibát okozott — lásd lent, a displacementet most már számoljuk).
          A 128 wordes blokkolás nagyobb tartalékot ad, de megtartja a
          gyors belső loop előnyét.

        Folyamat:
          1. 1024 word MWRITE → DATA_BASE staging (/WE zárva)
          2. pSOS-korrupt staging pozíciók javítása
          3. checksumok kiszámítása és stagingbe írása
          4. CAL RAM írás 128 wordes JSR-blokkokban
          5. checksum wordök külön, a legvégén íródnak

        Főkód blokkonként:
          MOVE.W (A3)+, D2  → adat stagingből D2-be
          NMI trigger       → callback: MOVEP.W D2,0(A0); RTS
          ADDQ.L #4, A0
          DBRA D0, loop

        Megjegyzés:
          A callback továbbra is single-word callback, tehát nem olvas
          forrás-RAM-ból. A staging olvasás a főkódban történik, közvetlenül
          az adott NMI trigger előtt.
        """
        if len(data) != CAL_RAM_SIZE:
            raise ValueError(f'Méret hiba: {len(data)} byte (kell: {CAL_RAM_SIZE})')
        self.assert_instrument_present()
        total_words = CAL_RAM_SIZE // 2  # 1024

        if block_words < 1:
            raise ValueError('block_words must be >= 1')
        if block_words > 128:
            raise ValueError('block_words must be <= 128 ebben a biztonsági verzióban')

        # Checksum word indexek. Ezeket nem írjuk fel lineáris sorrendben,
        # hanem csak a legvégén, hogy ne kerüljenek túl korán friss állapotba.
        cs_word_indexes = sorted({cs_off // 2 for cs_off in _CAL_SUM_OFFSETS})

        # ── Fázis 1: 1024 word staging MWRITE ───────────────────────────────
        # Ez még nem CAL RAM írás. Itt a CAL RAM /WE elvileg zárva van.
        total_progress = 1024 + 4 + total_words + len(cs_word_indexes)
        if progress_cb:
            progress_cb(0, total_progress, 'Staging (1024 szó → DATA_BASE)...')
        for i in range(total_words):
            if stop_event and stop_event.is_set():
                return False
            word = (data[i * 2] << 8) | data[i * 2 + 1]
            self.mwrite(DATA_BASE + i * 2, word)
            if progress_cb and i % 64 == 0:
                progress_cb(i, total_progress, f'Staging {i}/1024 szó')

        # ── Fázis 2: pSOS-korrupt pozíciók javítása ──────────────────────────
        # FONTOS (2026-06-16): itt KORÁBBAN a checksumokat is újraszámoltuk
        # egy fix seed-es képlettel — ez FELESLEGES volt (a Fázis 1 staging
        # ciklus már a `data`-ból helyesen írta ki őket), és VESZÉLYES, mert
        # az a képlet csak 2 saját dumpra volt illesztve (lásd cs.txt,
        # research/python/verify_checksum_hypothesis.py) — bármilyen más
        # dumpnál ROSSZ checksumot írt volna a stagingbe, majd a valós
        # cal_ram-ba. A `data` (a GUI codec által, a helyes flag_count-os
        # modellel előállított) checksuma már helyesen ott van a staging
        # területen a Fázis 1 után — nincs mit "javítani" rajta.
        if progress_cb:
            progress_cb(1024, total_progress, 'Korrupció javítás stagingben...')
        if stop_event and stop_event.is_set():
            return False

        for pair_i, _psos_hi, _phys in _BULK_BUGGY_PAIRS:
            word = (data[pair_i * 2] << 8) | data[pair_i * 2 + 1]
            self.mwrite(DATA_BASE + pair_i * 2, word)

        # Single-word callback: MOVEP.W D2,0(A0); RTS
        self._write_single_callback()

        db_base = DATA_BASE
        cr_base = CAL_RAM_BASE

        def run_block(start_word: int, count: int, done_words: int, label: str) -> bool:
            """Egy legfeljebb block_words hosszú, folytonos CAL word blokk írása."""
            if count <= 0:
                return True
            if count > block_words:
                raise ValueError('internal error: count > block_words')
            if stop_event and stop_event.is_set():
                return False

            a3 = db_base + start_word * 2
            a0 = cr_base + start_word * 4

            # A magic wordöket közvetlenül minden JSR előtt frissítjük.
            self._set_magic_words()

            # A DBRA visszaugró displacementjét NEM hardkódoljuk (ez okozta a
            # korábbi 114,"CPU EXCEPTION -- 4" hibát: -32 helyett -30 kellett
            # volna, így a CPU a LOOP előtti immediate adatszóba ugrott vissza
            # és illegális utasításként dekódolta azt — 68000 vector 4).
            # Helyette a LOOP címke és a DBRA szó indexéből számoljuk ki,
            # hogy a kód bármilyen átszerkesztése esetén is helyes maradjon.
            code = [
                0x4E45,                                            # TRAP #5
                0x267C, (a3 >> 16) & 0xFFFF, a3 & 0xFFFF,         # MOVEA.L #staging_start, A3
                0x207C, (a0 >> 16) & 0xFFFF, a0 & 0xFFFF,         # MOVEA.L #cal_start, A0
                *self._callback_setup_words(),
                0x303C, count - 1,                                  # MOVE.W #count-1, D0
            ]
            loop_start_word = len(code)                            # LOOP cimke ide mutat
            code += [
                0x341B,                                            # MOVE.W (A3)+, D2
                *self._nmi_trigger_words(),
                0x5888,                                            # ADDQ.L #4, A0
            ]
            dbra_word = len(code)                                  # ide kerül a 0x51C8 opcode
            # 68000 szabály: cél = (DBRA opcode címe + 2) + displacement
            # → displacement = LOOP címe - (DBRA opcode címe + 2)
            displacement = (loop_start_word * 2) - (dbra_word * 2 + 2)
            assert -32768 <= displacement <= 32767, 'DBRA displacement túl nagy blokkhoz'
            code += [
                0x51C8, displacement & 0xFFFF,                     # DBRA D0, loop
                0x4E75,                                            # RTS
            ]
            main_code = code
            self._mwrite_words(CODE_BASE, main_code)

            if progress_cb:
                progress_cb(1028 + done_words, total_progress,
                            f'{label}: start={start_word}, count={count}, '
                            f'CAL=0x{a0:06X}, D0=0x{(count - 1) & 0xFFFF:04X}')

            self.flush_errors()
            err = self.jsr(CODE_BASE, wait=1.5)
            ok = 'NO ERROR' in err
            if not ok and progress_cb:
                progress_cb(1028 + done_words, total_progress,
                            f'HIBA blokk start={start_word}, count={count}: {err}')
            return ok

        # ── Fázis 3: normál adatwordök, checksum wordök kihagyásával ────────
        # Folytonos tartományokat képezünk, hogy A0/A3 lineárisan léphessen.
        ranges = []
        start = 0
        for cs_i in cs_word_indexes:
            if start < cs_i:
                ranges.append((start, cs_i - start))
            start = cs_i + 1
        if start < total_words:
            ranges.append((start, total_words - start))

        done_words = 0
        block_no = 0
        for range_start, range_count in ranges:
            pos = range_start
            remaining = range_count
            while remaining > 0:
                count = min(block_words, remaining)
                block_no += 1
                if not run_block(pos, count, done_words,
                                 f'Adat blokk {block_no} ({block_words} word max / JSR)'):
                    return False
                pos += count
                remaining -= count
                done_words += count

        # ── Fázis 4: checksum wordök legvégén, egyenként rövid blokként ──────
        for cs_i in cs_word_indexes:
            block_no += 1
            if not run_block(cs_i, 1, done_words,
                             f'Checksum blokk {block_no}'):
                return False
            done_words += 1

        if progress_cb:
            progress_cb(total_progress, total_progress,
                        f'Kész: {done_words} CAL word írva, max {block_words} word / JSR-blokk')
        return True

    # ── Cal_RAM DUMP ─────────────────────────────────────────────────────────

    def dump_calram(self, progress_cb=None, stop_event=None) -> bytes:
        """2048 byte MREAD-del olvas. Visszaadja a bytes-t vagy None (ha megszakadt)."""
        result = bytearray(CAL_RAM_SIZE)
        for i in range(CAL_RAM_SIZE):
            if stop_event and stop_event.is_set():
                return None
            phys = CAL_RAM_BASE + i * 2
            result[i] = self.mread_hi(phys)
            if progress_cb and i % 16 == 0:
                progress_cb(i, CAL_RAM_SIZE, f'MREAD {i}/{CAL_RAM_SIZE}')
        if progress_cb:
            progress_cb(CAL_RAM_SIZE, CAL_RAM_SIZE, 'Kész')
        return bytes(result)

    # ── Cal_RAM VERIFY ────────────────────────────────────────────────────────

    def verify_calram(self, expected: bytes,
                      progress_cb=None, stop_event=None) -> tuple:
        """Visszaolvassa a cal_ram-ot és összehasonlítja.
        Visszatér: (ok: bool, diffs: [(offset, expected_byte, got_byte), ...])
        """
        diffs = []
        for i in range(CAL_RAM_SIZE):
            if stop_event and stop_event.is_set():
                return False, []
            phys = CAL_RAM_BASE + i * 2
            got = self.mread_hi(phys)
            if got != expected[i]:
                diffs.append((i, expected[i], got))
            if progress_cb and i % 16 == 0:
                progress_cb(i, CAL_RAM_SIZE, f'Verify {i}/{CAL_RAM_SIZE}')
        if progress_cb:
            progress_cb(CAL_RAM_SIZE, CAL_RAM_SIZE, 'Verify kész')
        return (len(diffs) == 0, diffs)

    # ── Settings_RAM DUMP ────────────────────────────────────────────────────

    def dump_settings(self, word_count: int = 16384,
                      progress_cb=None, stop_event=None) -> bytes:
        """Settings_ram dump. word_count: 16384=32KB, 32768=64KB (full, ~27 perc)."""
        result = bytearray(word_count * 2)
        for i in range(word_count):
            if stop_event and stop_event.is_set():
                return None
            phys = SETTINGS_BASE + i * 2
            w = self.mread_word(phys)
            result[i * 2]     = (w >> 8) & 0xFF
            result[i * 2 + 1] = w & 0xFF
            if progress_cb and i % 64 == 0:
                progress_cb(i, word_count, f'MREAD 0x{phys:06X}')
        if progress_cb:
            progress_cb(word_count, word_count, 'Kész')
        return bytes(result)

    # ── CALSTR írás (beépített GPIB parancs) ────────────────────────────────

    def write_calstr(self, text: str) -> str:
        """CALSTR 'szöveg' parancs küldése. Visszatér: ERRSTR? válasz."""
        safe = text[:80].replace('"', "'")
        self.send(f'CALSTR "{safe}"')
        time.sleep(0.5)
        return self.errstr()

    # ── Settings_RAM cleanup ──────────────────────────────────────────────────

    def cleanup_injected(self, include_data: bool = True,
                         progress_cb=None, stop_event=None) -> int:
        """Nullázza a settings_ram-ba írt kódot/adatot.

        Területek (MWRITE 0x0000):
          Magic words   : 4 word  (0x121780, 0x120C90, 0x121782, 0x120C92)
          NMI pointers  : 4 word  (0x121852–0x121858)
          CB_BASE       : 7 word  (0x12A100–0x12A10C)
          CODE_BASE     : 64 word (0x12A000–0x12A07E)
          DATA_BASE     : 1024 word (0x127200–0x127A00)  — ha include_data=True

        Visszatér: nullázott word-ök száma.
        """
        regions = []

        # Magic words + NMI pointer area
        for addr, _ in MAGIC_WORDS:
            regions.append(addr)
        for addr in (CALLBACK_PTR_ADDR, CALLBACK_PTR_ADDR + 2,  # 32-bit pointer, 2 word
                     SUCCESS_FLAG_ADDR, SAVED_SR_ADDR):
            regions.append(addr)

        # CB_BASE (7 word)
        regions += [CB_BASE + i * 2 for i in range(7)]

        # CODE_BASE (64 word — lefedi a leghosszabb főkódot is)
        regions += [CODE_BASE + i * 2 for i in range(64)]

        # DATA_BASE (1024 word) — csak ha kérték
        if include_data:
            regions += [DATA_BASE + i * 2 for i in range(1024)]

        total = len(regions)
        for idx, addr in enumerate(regions):
            if stop_event and stop_event.is_set():
                return idx
            self.mwrite(addr, 0x0000)
            if progress_cb and idx % 32 == 0:
                progress_cb(idx, total, f'Törlés {idx}/{total}')

        if progress_cb:
            progress_cb(total, total, 'Cleanup kész')
        return total
