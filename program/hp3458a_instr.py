"""HP 3458A műszer parancsok — MREAD, MWRITE, JSR, dump, cal_ram írás, verify."""
import time
from dataclasses import dataclass

from hp3458a_conn import BaseConn

CAL_RAM_BASE  = 0x60000
CAL_RAM_SIZE  = 2048
SETTINGS_BASE = 0x120000
SETTINGS_SIZE = 0x10000  # 64KB

# Settings RAM területek az injektált kód és staging adat számára.
# Minden ismert firmware verzióban megerősítetten szabad zóna.
CODE_BASE = 0x12A000   # ~64 szó főkód
CB_BASE   = 0x12A100   # ~20 szó callback
DATA_BASE = 0x127200   # 1024 szó staging

NMI_TRIGGER_PORT  = 0xC0001    # IO latch port; bit7 írása triggereli a Level7 NMI-t


# ── Firmware verzió-specifikus konstansok ────────────────────────────────────

@dataclass
class FirmwareConfig:
    """NMI mechanizmus Settings RAM-beli konstansai egy adott firmware verzióhoz.

    Az NMI adatstruktúra belső elrendezése azonos minden verzióban:
      callback_ptr_addr + 0 = callback pointer (32-bit)
      callback_ptr_addr + 4 = success_flag
      callback_ptr_addr + 6 = saved_sr
      callback_ptr_addr + 8 = we_close_val
    A magic word-pároknál DEAF+2=0ACE és BAD1+2=BEAD minden verzióban.
    """
    rev_major: int
    callback_ptr_addr: int   # NMI struktúra báziscíme a Settings RAM-ban
    magic_deaf_addr: int     # DEAF magic word cím (0ACE = +2)
    magic_bad1_addr: int     # BAD1 magic word cím (BEAD = +2)

    @property
    def success_flag_addr(self):  return self.callback_ptr_addr + 4
    @property
    def saved_sr_addr(self):      return self.callback_ptr_addr + 6
    @property
    def we_close_val_addr(self):  return self.callback_ptr_addr + 8
    @property
    def magic_0ace_addr(self):    return self.magic_deaf_addr + 2
    @property
    def magic_bead_addr(self):    return self.magic_bad1_addr + 2
    @property
    def magic_words(self):
        return [
            (self.magic_deaf_addr, 0xDEAF),
            (self.magic_bad1_addr, 0xBAD1),
            (self.magic_0ace_addr, 0x0ACE),
            (self.magic_bead_addr, 0xBEAD),
        ]


FIRMWARE_CONFIGS: dict[int, FirmwareConfig] = {
    9: FirmwareConfig(9, 0x121852, 0x121780, 0x120C90),
    8: FirmwareConfig(8, 0x121852, 0x121780, 0x120C90),
    7: FirmwareConfig(7, 0x121852, 0x121780, 0x120C90),
    6: FirmwareConfig(6, 0x121A4E, 0x12197C, 0x120C62),
    5: FirmwareConfig(5, 0x121A4E, 0x12197C, 0x120C62),  # REV5.3 — azonos REV6
    4: FirmwareConfig(4, 0x121A38, 0x12196E, 0x120C62),
    3: FirmwareConfig(3, 0x1211E8, 0x120AFE, 0x1211FC),  # REV3 — azonos REV2
    2: FirmwareConfig(2, 0x1211E8, 0x120AFE, 0x1211FC),
}

SUPPORTED_REVS = sorted(FIRMWARE_CONFIGS.keys())


# Cal_RAM checksum szavak byte-offsetjei. A checksum szavakat a feltöltés
# legvégén, a normál adatblokkokból elkülönítve kell írni — ezzel elkerülhető,
# hogy részlegesen felírt adat mellé érvényes checksum kerüljön.
# A checksum értékét a CalRAMCodec számítja (hp3458a_calram.py).
_CAL_SUM_OFFSETS = [0x1BC, 0x59C, 0x5C8, 0x624]  # CS0, CS1, CS2, CS3

# A DATA_BASE staging területen 3 pozíció HIGH byte-ját egy háttérfolyamat
# felülírja a ~3 perces MWRITE alatt. Ezek a CS1 tartományba eső word-ök
# (cal_ram[946], [1018], [1022]) — a feltöltés előtt a staging megfelelő
# pozícióit a cal_ram tartalomból vissza kell állítani.
# Elemek: (pair_i, felülírt_high_byte, fizikai_even_cím)
_BULK_BUGGY_PAIRS = [
    (473, 0x02, CAL_RAM_BASE + 473 * 4),
    (509, 0x02, CAL_RAM_BASE + 509 * 4),
    (511, 0x04, CAL_RAM_BASE + 511 * 4),
]


class HP3458A:
    def __init__(self, conn: BaseConn):
        self._conn = conn
        self._cfg: FirmwareConfig = FIRMWARE_CONFIGS[9]  # alapértelmezett; init() frissíti

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
        """SDC flush + ID? ellenőrzés minden cal_ram írás előtt.

        Egy GPIB bridge önmagában képes kielégítő választ adni (lebegő busz,
        pufferelt válasz) akkor is, ha a műszer nincs bekapcsolva — ezért az
        ERRSTR? 'NO ERROR' önmagában nem elegendő bizonyíték. Az ID? válaszban
        kötelező a 'HP3458A' karakterlánc.
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

    @property
    def fw_rev(self) -> int:
        """Detektált firmware verzió főszáma (pl. 9 = REV9)."""
        return self._cfg.rev_major

    def detect_firmware_config(self) -> FirmwareConfig:
        """REV? lekérdezés alapján visszaadja a verziófüggő konstansokat.

        A firmware válasza: 'REV 9,0' (REV prefix + major,minor formátum).
        Sikertelen lekérdezés vagy ismeretlen verzió esetén RuntimeError-t dob.
        Eredmény self._cfg-be is kerül.
        """
        resp = self.query('REV?', tmo=5.0).strip()
        try:
            # 'REV 9,0', '9,0', 'REV 5,3', 'REV 5.3,0' mindkettőt kezeli
            clean = resp.upper().replace('REV', '').strip()
            major = int(float(clean.split(',')[0].strip()))
        except (ValueError, IndexError):
            raise RuntimeError(f'REV? érvénytelen válasz: {resp!r}')
        cfg = FIRMWARE_CONFIGS.get(major)
        if cfg is None:
            raise RuntimeError(
                f'Nem támogatott firmware verzió: REV {major}. '
                f'Támogatott: REV {SUPPORTED_REVS}.'
            )
        self._cfg = cfg
        return cfg

    def init(self):
        """Műszer-jelenlét ellenőrzés + alapállapot: PRESET NORM + END ALWAYS + BEEP 1."""
        self.assert_instrument_present()
        self.send('PRESET NORM')
        time.sleep(0.8)
        self.send('END ALWAYS')
        time.sleep(0.2)
        self.send('BEEP 1')    # KÖTELEZŐ az MREAD-hez!
        time.sleep(0.2)
        self.detect_firmware_config()
        self.query('ERRSTR?')

    def test_id(self) -> str:
        """Lekérdezi az azonosítót (ID?). Sikeres kapcsolat esetén: 'HP3458A,...'"""
        return self.query('ID?', tmo=5.0)

    def errstr(self) -> str:
        return self.query('ERRSTR?', tmo=3.0)

    # ── MREAD / MWRITE ───────────────────────────────────────────────────────

    def mread_word(self, phys: int, retries: int = 3) -> int:
        """MREAD decimális cím → 16-bit word. LOW byte = 0xB9 (lebegő busz a cal_ram-nál)."""
        from hp3458a_conn import ConnError
        for attempt in range(retries):
            try:
                r = self.query(f'MREAD {phys}', tmo=2.0).strip()
                v = int(r)
                if not (-32768 <= v <= 32767):
                    raise ValueError(f'MREAD válasz tartományon kívül: {v!r}')
                return v & 0xFFFF
            except (TimeoutError, ConnError):
                if attempt == retries - 1:
                    raise
                time.sleep(0.2)
        raise RuntimeError('unreachable')

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
        for addr, val in self._cfg.magic_words:
            self.mwrite(addr, val)

    def _write_single_callback(self):
        """Callback: movep.w d2,$0(a0); rts  — 1 word (2 byte) ír cal_ram-ba."""
        self._mwrite_words(CB_BASE, [0x0588, 0x0000, 0x4E75])

    def _callback_setup_words(self) -> list:
        """Közös JSR main_code prológ: CB_BASE betöltése callback_ptr-be, success_flag törlése."""
        cfg = self._cfg
        return [
            0x287C, (CB_BASE >> 16) & 0xFFFF, CB_BASE & 0xFFFF,                      # MOVEA.L #CB_BASE, A4
            0x23CC, (cfg.callback_ptr_addr >> 16) & 0xFFFF, cfg.callback_ptr_addr & 0xFFFF,  # MOVE.L A4, callback_ptr
            0x33FC, 0x0000,
            (cfg.success_flag_addr >> 16) & 0xFFFF, cfg.success_flag_addr & 0xFFFF,  # MOVE.W #0, success_flag
        ]

    def _nmi_trigger_words(self) -> list:
        """/WE nyitás + Level7 NMI trigger + timing wait a cal_ram íráshoz.
        A timing wait az IO latch propagation delay miatt kötelező a trigger után."""
        cfg = self._cfg
        return [
            0x1C39, (cfg.we_close_val_addr >> 16) & 0xFFFF, cfg.we_close_val_addr & 0xFFFF,  # MOVE.B we_close, D6
            0x0046, 0x0080,                                                                   # ORI.W #$80, D6
            0x13C6, (NMI_TRIGGER_PORT >> 16) & 0xFFFF, NMI_TRIGGER_PORT & 0xFFFF,            # MOVE.B D6, nmi_port
            0x3C3C, 0x0009,                                                                   # MOVE.W #9, D6
            0x57CE, 0xFFFE,                                                                   # DBEQ D6, *  (timing wait)
        ]

    # ── Cal_RAM WRITE: egyszeri word ─────────────────────────────────────────

    def _write_calram_word_raw(self, phys: int, word: int) -> str:
        """Egy cal_ram word NMI-vel való írása; visszatér a nyers ERRSTR? válasszal."""
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
        """Teljes cal_RAM feltöltés blokkos JSR módban (alapértelmezés: 128 word/blokk).

        Folyamat:
          1. 1024 word MWRITE → DATA_BASE staging
          2. Háttérfolyamat által felülírt staging pozíciók korrekciója
          3. CAL RAM írás legfeljebb block_words szavas JSR-blokkokban
          4. Checksum szavak külön, a legvégén

        Főkód blokkonként: MOVE.W (A3)+,D2 → NMI → MOVEP.W D2,0(A0) → ADDQ.L #4,A0 → DBRA D0,loop
        A callback csak MOVEP.W + RTS — nem olvas forrás-RAM-ból.
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

        # ── Fázis 2: háttérfolyamat által felülírt staging pozíciók korrekciója ──
        # A staging MWRITE alatt egy háttérfolyamat 3 pozíció HIGH byte-ját
        # felülírja — ezeket a `data` tartalmából vissza kell állítani.
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

            # A DBRA displacement értékét a tényleges opcode indexekből számítjuk —
            # nem hardkódolva: cél = (DBRA_opcode_cím + 2) + displacement (68000 szabály).
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
            if not (-32768 <= displacement <= 32767):
                raise ValueError(f'DBRA displacement túl nagy blokkhoz: {displacement}')
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

    def dump_calram(self, progress_cb=None, stop_event=None) -> bytes | None:
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
        Visszatér: (ok: bool | None, diffs: list)
          ok=True: minden egyezik; ok=False: eltérés; ok=None: megszakítva
        """
        diffs = []
        for i in range(CAL_RAM_SIZE):
            if stop_event and stop_event.is_set():
                return None, []
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
                      progress_cb=None, stop_event=None) -> bytes | None:
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

    # ── CALSTR / SECURE / UNSECURE (beépített GPIB parancsok) ──────────────

    def write_calstr(self, text: str) -> str:
        """CALSTR 'szöveg' parancs küldése. Visszatér: ERRSTR? válasz."""
        safe = text[:80].replace('"', "'")
        self.send(f'CALSTR "{safe}"')
        time.sleep(0.5)
        return self.errstr()

    def read_secure_code(self) -> int:
        """Cal_SecureCode (u32 @ cal_ram 0x61E) live MREAD-del. 0 = unsecured."""
        base = CAL_RAM_BASE + 0x61E * 2   # = 0x60C3C
        b = [self.mread_hi(base + i * 2) for i in range(4)]
        return (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]

    def gpib_unsecure(self, old_code: str) -> str:
        """SECURE old_code,0 → ERRSTR?. new_code=0 törli a biztonsági kódot."""
        self.send(f'SECURE {old_code},0')
        time.sleep(0.5)
        return self.errstr()

    def gpib_secure(self, new_code: str) -> str:
        """SECURE 0,new_code,ON → ERRSTR?. Csak unsecured állapotból (old_code=0)."""
        self.send(f'SECURE 0,{new_code},ON')
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

        # Magic words + NMI pointer area (verzió-specifikus címek)
        for addr, _ in self._cfg.magic_words:
            regions.append(addr)
        cb = self._cfg.callback_ptr_addr
        for addr in (cb, cb + 2,                              # 32-bit callback pointer
                     self._cfg.success_flag_addr, self._cfg.saved_sr_addr):
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
