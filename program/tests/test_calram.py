"""hp3458a_calram.py unit tesztek — hardver nélkül futtatható.
Futtatás: cd program && pytest tests/test_calram.py -v
"""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from hp3458a_calram import (
    CAL_RAM_SIZE, CAL_SUM_DEFS, CalRAMCodec, _range_sum,
)


def _make_valid_dump() -> bytes:
    """Szintetikus 2048 bájtos dump helyes checksumokkal (flag_count=0)."""
    data = bytearray(CAL_RAM_SIZE)
    for _name, off, ranges in CAL_SUM_DEFS:
        cs = _range_sum(data, ranges)
        struct.pack_into('>H', data, off, cs & 0xFFFF)
    return bytes(data)


# ── Méret validáció ───────────────────────────────────────────────────────────

def test_size_too_small():
    with pytest.raises(ValueError):
        CalRAMCodec(b'\x00' * 100)

def test_size_too_large():
    with pytest.raises(ValueError):
        CalRAMCodec(b'\x00' * 4096)

def test_exact_size_ok():
    CalRAMCodec(_make_valid_dump())


# ── Checksum ──────────────────────────────────────────────────────────────────

def test_checksums_ok_on_valid_dump():
    assert CalRAMCodec(_make_valid_dump()).checksums_ok()

def test_checksum_fails_after_data_modification():
    codec = CalRAMCodec(_make_valid_dump())
    codec._data[0x010] ^= 0xFF          # byte a Cal_Sum0 tartományban (0x000-0x040)
    assert not codec.checksums_ok()

def test_recalculate_restores_checksums():
    codec = CalRAMCodec(_make_valid_dump())
    codec._data[0x010] ^= 0xFF
    codec.recalculate_checksums()
    assert codec.checksums_ok()

def test_verify_checksums_returns_four_entries():
    result = CalRAMCodec(_make_valid_dump()).verify_checksums()
    assert len(result) == 4
    assert all(ok for _, _, _, _, ok in result)


# ── Diff / changed words ──────────────────────────────────────────────────────

def test_find_changed_words_empty_initially():
    assert CalRAMCodec(_make_valid_dump()).find_changed_words() == []

def test_find_changed_words_detects_single_word():
    dump = _make_valid_dump()
    codec = CalRAMCodec(dump)
    codec._data[0x010] = (dump[0x010] + 1) & 0xFF
    changed = codec.find_changed_words()
    assert len(changed) == 1
    cal_off, _phys, _word = changed[0]
    assert cal_off == 0x010

def test_diff_fields_empty_initially():
    assert CalRAMCodec(_make_valid_dump()).diff_fields() == []

def test_reset_original_clears_diff():
    codec = CalRAMCodec(_make_valid_dump())
    codec._data[0x010] ^= 0xFF
    assert codec.find_changed_words() != []
    codec.reset_original()
    assert codec.find_changed_words() == []


# ── Mező írás / validáció ─────────────────────────────────────────────────────

def test_set_field_double_ok():
    codec = CalRAMCodec(_make_valid_dump())
    err = codec.set_field_str('40Kohm reference', '1.23456789012')
    assert err == ''
    val = codec.get_field_value('40Kohm reference')
    assert abs(val - 1.23456789012) < 1e-10

def test_set_field_u16_out_of_range():
    codec = CalRAMCodec(_make_valid_dump())
    err = codec.set_field_str('Cal_Sum0', '99999')
    assert err != ''

def test_set_field_unknown_name():
    codec = CalRAMCodec(_make_valid_dump())
    err = codec.set_field_str('NemLetezoMezo', '0')
    assert err != ''
