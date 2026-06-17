"""HP 3458A cal_ram codec — olvas, ír, checksum, riport.
Importálja a FIELDS listát a meglévő hp3458a_calram_decoder.py-ból.
"""
import struct
import hashlib
from pathlib import Path

CAL_RAM_SIZE = 2048
CAL_RAM_BASE = 0x60000

try:
    from hp3458a_calram_decoder import FIELDS, TYPE_SIZE
except ImportError:
    raise ImportError('hp3458a_calram_decoder.py nem található a program mappájában')

# Checksum definíciók: (mező_neve, offset, [(tartomány_start, tartomány_end_exclusive), ...])
#
# 2026-06-16: a korábbi "egy tartomány + fix seed" modellt ELVETETTÜK — 6
# független dumpon (2 saját friss, 2 régebbi saját-szerű, 2 VALÓDI külső/régi
# műszer dumpja) tesztelve csak 2/6-on egyezett (lásd
# research/python/verify_checksum_hypothesis.py és research/dumps/cs.txt).
# Még a saját, friss műszerdump is hibásnak látszott vele — a régi képlet
# csak 2 konkrét, egymással rokon dumpra volt illesztve, nem általános.
#
# A helyes modell (cs.txt hipotézis, megerősítve): TÖBB tartomány összege +
# egy "flag_count" maradék, amit minden BETÖLTÖTT dumpból külön kell
# visszafejteni (lásd CalRAMCodec.__init__ / _derive_flag_counts), NEM egy
# globális konstans. CS0/CS2 flag_count tökéletesen stabil volt mind a 6
# dumpon (56 / 11), CS1/CS3 5/6-on (187 / 3) — ez utóbbi kettő valószínűleg
# egy firmware-revíziónként vagy biztonsági-állapotonként változó flag-bitet
# tartalmaz, ezért MINDIG a betöltött dump saját értékét kell megőrizni,
# nem feltételezni egy univerzális konstanst.
CAL_SUM_DEFS = [
    ('Cal_Sum0', 0x1BC, [(0x000, 0x040), (0x060, 0x1BC)]),
    ('Cal_Sum1', 0x59C, [(0x040, 0x060), (0x1C0, 0x59C)]),
    ('Cal_Sum2', 0x5C8, [(0x5A0, 0x5C8)]),
    ('Cal_Sum3', 0x624, [(0x5CA, 0x624)]),
]

# Checksum tartományon kívüli mezők (nem kell checksum frissítés):
OUTSIDE_CHECKSUM = {0x626, 0x62A}  # Destructive Overloads, Defeats


def _range_sum(data: bytes, ranges) -> int:
    total = 0
    for start, end in ranges:
        total += sum(data[start:end])
    return total & 0xFFFF


def _compute_checksum(data: bytes, ranges, flag_count: int) -> int:
    """Cal_Sum = (több tartomány összege + flag_count) & 0xFFFF.

    A flag_count NEM globális konstans — minden dumpból a betöltéskor kell
    visszafejteni (stored - rangesum), és megőrizni a módosítások során.
    Lásd a CAL_SUM_DEFS feletti megjegyzést.
    """
    return (_range_sum(data, ranges) + flag_count) & 0xFFFF


def _read_field(data: bytes, offset: int, typ: str):
    sz = TYPE_SIZE[typ]
    if offset + sz > len(data):
        return None
    chunk = data[offset:offset + sz]
    if typ == 'dbl': return struct.unpack('>d', chunk)[0]
    if typ == 'i32': return struct.unpack('>i', chunk)[0]
    if typ == 'u32': return struct.unpack('>I', chunk)[0]
    if typ == 'u16': return struct.unpack('>H', chunk)[0]
    if typ == 'u8':  return chunk[0]
    if typ == 'str':
        return chunk.replace(b'\xa0', b' ').rstrip(b'\x00 ').decode('ascii', errors='replace')
    return None


def _write_field(data: bytearray, offset: int, typ: str, value) -> str:
    """Validál és visszaír. Visszatér: '' (ok) vagy hibaüzenet."""
    sz = TYPE_SIZE[typ]
    try:
        if typ == 'dbl':
            v = float(value)
            struct.pack_into('>d', data, offset, v)
        elif typ == 'i32':
            v = int(value, 0) if isinstance(value, str) else int(value)
            if not (-2147483648 <= v <= 2147483647):
                return 'Tartomány: -2 147 483 648 .. 2 147 483 647'
            struct.pack_into('>i', data, offset, v)
        elif typ == 'u32':
            v = int(value, 0) if isinstance(value, str) else int(value)
            if not (0 <= v <= 4294967295):
                return 'Tartomány: 0 .. 4 294 967 295'
            struct.pack_into('>I', data, offset, v)
        elif typ == 'u16':
            v = int(value, 0) if isinstance(value, str) else int(value)
            if not (0 <= v <= 65535):
                return 'Tartomány: 0 .. 65 535'
            struct.pack_into('>H', data, offset, v)
        elif typ == 'u8':
            v = int(value, 0) if isinstance(value, str) else int(value)
            if not (0 <= v <= 255):
                return 'Tartomány: 0 .. 255'
            data[offset] = v
        elif typ == 'str':
            s = str(value)[:80]
            bad = [c for c in s if not (32 <= ord(c) <= 126)]
            if bad:
                return f'Csak ASCII 32-126 (rossz: {bad[:5]})'
            enc = s.encode('ascii').ljust(80, b'\x00')
            data[offset:offset + sz] = enc
    except (ValueError, struct.error) as exc:
        return f'Formátum hiba: {exc}'
    return ''


def _fmt_value(val, typ: str) -> str:
    if val is None: return '???'
    if typ == 'dbl': return f'{val:.13E}'
    if typ == 'str': return val
    return str(val)


def _which_checksums_affected(offset: int, size: int) -> list:
    """Visszaadja azokat a Cal_Sum neveket amelyek (bármelyik) tartományát érinti az offset+size."""
    affected = []
    field_end = offset + size
    for name, _cs_off, ranges in CAL_SUM_DEFS:
        if any(offset < end and field_end > start for start, end in ranges):
            affected.append(name)
    return affected


class CalRAMCodec:
    """Cal_RAM olvasás, írás, checksum, riport."""

    def __init__(self, data: bytes):
        if len(data) != CAL_RAM_SIZE:
            raise ValueError(f'Méret hiba: {len(data)} byte (kell: {CAL_RAM_SIZE})')
        self._data     = bytearray(data)
        self._original = bytes(data)
        self._flag_counts = self._derive_flag_counts(self._original)

    @staticmethod
    def _derive_flag_counts(data: bytes) -> dict:
        """flag_count = stored_checksum - rangesum, EBBŐL a (még módosítatlan)
        dumpból visszafejtve — lásd a CAL_SUM_DEFS feletti megjegyzést.
        Ezt kell megőrizni minden további újraszámításnál, NEM egy globális
        konstanst feltételezni.
        """
        out = {}
        for name, off, ranges in CAL_SUM_DEFS:
            stored = _read_field(data, off, 'u16') or 0
            out[name] = (stored - _range_sum(data, ranges)) & 0xFFFF
        return out

    # ── Konstruktorok ────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path) -> 'CalRAMCodec':
        data = Path(path).read_bytes()
        return cls(data)

    def reset_original(self):
        """Jelenlegi állapotot "eredeti"-ként rögzíti (pl. sikeres feltöltés után)."""
        self._original = bytes(self._data)
        self._flag_counts = self._derive_flag_counts(self._original)

    # ── Exportálás ───────────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def to_file(self, path):
        Path(path).write_bytes(bytes(self._data))

    def md5(self) -> str:
        return hashlib.md5(bytes(self._data)).hexdigest()

    # ── Mező műveletek ────────────────────────────────────────────────────────

    def get_all_fields(self) -> list:
        """Visszaadja az összes mező szótárát (offset, typ, name, raw, value, value_str, changed)."""
        result = []
        for off, typ, name in FIELDS:
            sz   = TYPE_SIZE[typ]
            raw  = bytes(self._data[off:off + sz])
            val  = _read_field(self._data, off, typ)
            orig = self._original[off:off + sz]
            result.append({
                'offset':    off,
                'typ':       typ,
                'name':      name,
                'raw':       raw,
                'value':     val,
                'value_str': _fmt_value(val, typ),
                'size':      sz,
                'changed':   raw != orig,
                'checksums': _which_checksums_affected(off, sz),
            })
        return result

    def get_field_value(self, name: str):
        for off, typ, n in FIELDS:
            if n == name:
                return _read_field(self._data, off, typ)
        return None

    def set_field_str(self, name: str, str_value: str) -> str:
        """Beállít egy mezőt string bevitelből. Visszatér: '' (ok) vagy hibaüzenet."""
        for off, typ, n in FIELDS:
            if n == name:
                return _write_field(self._data, off, typ, str_value)
        return f'Ismeretlen mező: {name}'

    def validate_field_str(self, name: str, str_value: str) -> str:
        """Validál, nem módosít. Visszatér: '' (ok) vagy hibaüzenet."""
        for off, typ, n in FIELDS:
            if n == name:
                tmp = bytearray(self._data)
                return _write_field(tmp, off, typ, str_value)
        return f'Ismeretlen mező: {name}'

    # ── Checksum ─────────────────────────────────────────────────────────────

    def verify_checksums(self) -> list:
        """Visszaadja: [(név, offset, tárolt, számított, ok), ...]

        A "számított" érték a betöltéskor (vagy utolsó reset_original()-kor)
        rögzített flag_count-tal készül, NEM globális konstanssal — ezért ha
        a checksum tartományon belül módosítottál egy mezőt, de még nem
        számoltál újra, itt eltérést fogsz látni (ez a helyes, várt jelzés).
        """
        d = bytes(self._data)
        out = []
        for name, off, ranges in CAL_SUM_DEFS:
            stored   = _read_field(d, off, 'u16') or 0
            computed = _compute_checksum(d, ranges, self._flag_counts[name])
            out.append((name, off, stored, computed, stored == computed))
        return out

    def recalculate_checksums(self):
        """A checksumokat a betöltéskor megőrzött flag_count-tal frissíti —
        SOHA nem a jelenlegi (esetleg már módosított) adatból fejti vissza
        újra a flag_count-ot, mert az tautologikusan mindig "helyesnek"
        tüntetne fel bármilyen adatot."""
        for name, off, ranges in CAL_SUM_DEFS:
            cs_val = _compute_checksum(self._data, ranges, self._flag_counts[name])
            struct.pack_into('>H', self._data, off, cs_val)

    def checksums_ok(self) -> bool:
        return all(ok for _, _, _, _, ok in self.verify_checksums())

    # ── Diff ─────────────────────────────────────────────────────────────────

    def find_changed_words(self) -> list:
        """Összehasonlítja az original-lal, visszaadja: [(cal_even_offset, phys, new_word), ...]"""
        changed = []
        for i in range(1024):
            b0, b1 = self._data[i * 2], self._data[i * 2 + 1]
            o0, o1 = self._original[i * 2], self._original[i * 2 + 1]
            if b0 != o0 or b1 != o1:
                cal_off = i * 2
                phys    = CAL_RAM_BASE + cal_off * 2
                changed.append((cal_off, phys, (b0 << 8) | b1))
        return changed

    def diff_fields(self) -> list:
        """Visszaadja a változott mezők listáját: [(name, old_str, new_str), ...]"""
        diffs = []
        for off, typ, name in FIELDS:
            sz   = TYPE_SIZE[typ]
            raw  = bytes(self._data[off:off + sz])
            orig = self._original[off:off + sz]
            if raw != orig:
                old_val = _read_field(self._original, off, typ)
                new_val = _read_field(self._data,     off, typ)
                diffs.append((name, _fmt_value(old_val, typ), _fmt_value(new_val, typ)))
        return diffs

    # ── Riport ───────────────────────────────────────────────────────────────

    def generate_report(self, lang: str = 'hu') -> str:
        from datetime import datetime
        d   = bytes(self._data)
        sep = '=' * 70
        is_hu = (lang == 'hu')

        def r(off, typ): return _read_field(d, off, typ)

        lines = [
            sep,
            ('HP 3458A Kalibrációs Riport' if is_hu else 'HP 3458A Calibration Report'),
            f'Dátum / Date : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            sep, '',
        ]

        calstr  = r(0x5CA, 'str')
        calnum  = r(0x61A, 'u32')
        secure  = r(0x61E, 'u32')
        acsec   = r(0x622, 'u8')
        dolt    = r(0x626, 'u32')
        defeats = r(0x62A, 'u32')

        if is_hu:
            lines += [
                f'  Cal. szöveg (CALSTR)  : {calstr}',
                f'  Kalibrációs szám      : {calnum}',
                f'  Biztosítási kód       : 0x{secure or 0:08X}',
                f'  AcalSecure            : {acsec}',
                f'  Romboló túlterhelés   : {dolt}',
                f'  Defeats               : {defeats}',
            ]
        else:
            lines += [
                f'  Calibration String    : {calstr}',
                f'  Calibration Number    : {calnum}',
                f'  Secure Code           : 0x{secure or 0:08X}',
                f'  AcalSecure            : {acsec}',
                f'  Destructive Overloads : {dolt}',
                f'  Defeats               : {defeats}',
            ]

        lines += ['', ('Hőmérsékletek:' if is_hu else 'Temperatures:')]
        for off, lbl in [(0x1A4, 'Cal 0°C'), (0x1AC, 'Cal 10°C'), (0x1B4, 'Cal 10k°C'),
                         (0x442, 'ACAL DCV'), (0x44A, 'ACAL OHM'), (0x452, 'ACAL ACV')]:
            v = r(off, 'dbl')
            lines.append(f'  {lbl:<22}: {v:.6f} °C' if v is not None else f'  {lbl}: ???')

        lines += ['', ('Ellenőrzőösszegek:' if is_hu else 'Checksums:')]
        for name, off, stored, computed, ok in self.verify_checksums():
            status = 'OK ✓' if ok else 'HIBÁS ✗'
            lines.append(
                f'  {name:<12} @ 0x{off:04X}  '
                f'tárolt=0x{stored:04X}  számított=0x{computed:04X}  [{status}]'
            )

        lines += ['', f'MD5: {self.md5()}', '', sep,
                  ('Összes mező:' if is_hu else 'All fields:'), '']
        lines.append(f'  {"Offset":<8} {"Típus":<5} {"Érték":<30} Mező')
        lines.append(f'  {"-"*8} {"-"*5} {"-"*30} {"-"*35}')
        for off, typ, name in FIELDS:
            val = _read_field(d, off, typ)
            lines.append(f'  0x{off:04X}   {typ:<5} {_fmt_value(val, typ):<30} {name}')

        return '\n'.join(lines) + '\n'
