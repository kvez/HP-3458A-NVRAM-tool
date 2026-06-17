"""
HP 3458A cal_ram decoder
Bemenet: dump_XXXXX/dump_01_cal_ram.bin  (2048 byte, DS1220Y NVRAM, base 0x60000)
Kimenet: szöveges riport stdout-ra

Mezőtípusok:
  dbl   — IEEE 754 64-bit big-endian double
  i32   — signed 32-bit big-endian int
  u16   — unsigned 16-bit big-endian int
  u8    — unsigned 8-bit int
  str   — null-padded ASCII (Calstr)
"""

import struct
import sys
import os
import argparse

CAL_RAM_SIZE  = 2048
CAL_RAM_BASE  = 0x60000

# ---------------------------------------------------------------------------
# Mezőtábla: (offset, típus, név)
# Forrás: image_gpib olvasott_decoded.txt + HP 3458A Service Manual
# ---------------------------------------------------------------------------
FIELDS = [
    (0x000, 'dbl', '40Kohm reference'),
    (0x008, 'dbl', '7Vdc reference'),
    (0x010, 'dbl', 'dcv zero front 100mV'),
    (0x018, 'dbl', 'dcv zero rear  100mV'),
    (0x020, 'dbl', 'dcv zero front 1V'),
    (0x028, 'dbl', 'dcv zero rear  1V'),
    (0x030, 'dbl', 'dcv zero front 10V'),
    (0x038, 'dbl', 'dcv zero rear  10V'),
    (0x040, 'dbl', 'dcv zero front 100V'),
    (0x048, 'dbl', 'dcv zero rear  100V'),
    (0x050, 'dbl', 'dcv zero front 1KV'),
    (0x058, 'dbl', 'dcv zero rear  1KV'),
    (0x060, 'dbl', 'ohm zero front 10'),
    (0x068, 'dbl', 'ohm zero front 100'),
    (0x070, 'dbl', 'ohm zero front 1K'),
    (0x078, 'dbl', 'ohm zero front 10K'),
    (0x080, 'dbl', 'ohm zero front 100K'),
    (0x088, 'dbl', 'ohm zero front 1M'),
    (0x090, 'dbl', 'ohm zero front 10M'),
    (0x098, 'dbl', 'ohm zero front 100M'),
    (0x0A0, 'dbl', 'ohm zero front 1G'),
    (0x0A8, 'dbl', 'ohm zero rear 10'),
    (0x0B0, 'dbl', 'ohm zero rear 100'),
    (0x0B8, 'dbl', 'ohm zero rear 1K'),
    (0x0C0, 'dbl', 'ohm zero rear 10K'),
    (0x0C8, 'dbl', 'ohm zero rear 100K'),
    (0x0D0, 'dbl', 'ohm zero rear 1M'),
    (0x0D8, 'dbl', 'ohm zero rear 10M'),
    (0x0E0, 'dbl', 'ohm zero rear 100M'),
    (0x0E8, 'dbl', 'ohm zero rear 1G'),
    (0x0F0, 'dbl', 'ohmf zero front 10'),
    (0x0F8, 'dbl', 'ohmf zero front 100'),
    (0x100, 'dbl', 'ohmf zero front 1K'),
    (0x108, 'dbl', 'ohmf zero front 10K'),
    (0x110, 'dbl', 'ohmf zero front 100K'),
    (0x118, 'dbl', 'ohmf zero front 1M'),
    (0x120, 'dbl', 'ohmf zero front 10M'),
    (0x128, 'dbl', 'ohmf zero front 100M'),
    (0x130, 'dbl', 'ohmf zero front 1G'),
    (0x138, 'dbl', 'ohmf zero rear 10'),
    (0x140, 'dbl', 'ohmf zero rear 100'),
    (0x148, 'dbl', 'ohmf zero rear 1K'),
    (0x150, 'dbl', 'ohmf zero rear 10K'),
    (0x158, 'dbl', 'ohmf zero rear 100K'),
    (0x160, 'dbl', 'ohmf zero rear 1M'),
    (0x168, 'dbl', 'ohmf zero rear 10M'),
    (0x170, 'dbl', 'ohmf zero rear 100M'),
    (0x178, 'dbl', 'ohmf zero rear 1G'),
    (0x180, 'i32', 'autorange offset ohm 10'),
    (0x184, 'i32', 'autorange offset ohm 100'),
    (0x188, 'i32', 'autorange offset ohm 1K'),
    (0x18C, 'i32', 'autorange offset ohm 10K'),
    (0x190, 'i32', 'autorange offset ohm 100K'),
    (0x194, 'i32', 'autorange offset ohm 1M'),
    (0x198, 'i32', 'autorange offset ohm 10M'),
    (0x19C, 'i32', 'autorange offset ohm 100M'),
    (0x1A0, 'i32', 'autorange offset ohm 1G'),
    (0x1A4, 'dbl', 'cal 0 temperature'),
    (0x1AC, 'dbl', 'cal 10 temperature'),
    (0x1B4, 'dbl', 'cal 10k temperature'),
    (0x1BC, 'u16', 'Cal_Sum0'),
    (0x1BE, 'u16', 'vos dac'),
    (0x1C0, 'dbl', 'dci zero rear 100nA'),
    (0x1C8, 'dbl', 'dci zero rear 1uA'),
    (0x1D0, 'dbl', 'dci zero rear 10uA'),
    (0x1D8, 'dbl', 'dci zero rear 100uA'),
    (0x1E0, 'dbl', 'dci zero rear 1mA'),
    (0x1E8, 'dbl', 'dci zero rear 10mA'),
    (0x1F0, 'dbl', 'dci zero rear 100mA'),
    (0x1F8, 'dbl', 'dci zero rear 1A'),
    (0x200, 'dbl', 'dcv gain 100mV'),
    (0x208, 'dbl', 'dcv gain 1V'),
    (0x210, 'dbl', 'dcv gain 10V'),
    (0x218, 'dbl', 'dcv gain 100V'),
    (0x220, 'dbl', 'dcv gain 1KV'),
    (0x228, 'dbl', 'ohm gain 10'),
    (0x230, 'dbl', 'ohm gain 100'),
    (0x238, 'dbl', 'ohm gain 1K'),
    (0x240, 'dbl', 'ohm gain 10K'),
    (0x248, 'dbl', 'ohm gain 100K'),
    (0x250, 'dbl', 'ohm gain 1M'),
    (0x258, 'dbl', 'ohm gain 10M'),
    (0x260, 'dbl', 'ohm gain 100M'),
    (0x268, 'dbl', 'ohm gain 1G'),
    (0x270, 'dbl', 'ohm ocomp gain 10'),
    (0x278, 'dbl', 'ohm ocomp gain 100'),
    (0x280, 'dbl', 'ohm ocomp gain 1K'),
    (0x288, 'dbl', 'ohm ocomp gain 10K'),
    (0x290, 'dbl', 'ohm ocomp gain 100K'),
    (0x298, 'dbl', 'ohm ocomp gain 1M'),
    (0x2A0, 'dbl', 'ohm ocomp gain 10M'),
    (0x2A8, 'dbl', 'ohm ocomp gain 100M'),
    (0x2B0, 'dbl', 'ohm ocomp gain 1G'),
    (0x2B8, 'dbl', 'dci gain 100nA'),
    (0x2C0, 'dbl', 'dci gain 1uA'),
    (0x2C8, 'dbl', 'dci gain 10uA'),
    (0x2D0, 'dbl', 'dci gain 100uA'),
    (0x2D8, 'dbl', 'dci gain 1mA'),
    (0x2E0, 'dbl', 'dci gain 10mA'),
    (0x2E8, 'dbl', 'dci gain 100mA'),
    (0x2F0, 'dbl', 'dci gain 1A'),
    (0x2F8, 'u8',  'precharge dac'),
    (0x2F9, 'u8',  'mc dac'),
    (0x2FA, 'dbl', 'high speed gain'),
    (0x302, 'dbl', 'il'),
    (0x30A, 'dbl', 'il2'),
    (0x312, 'dbl', 'rin'),
    (0x31A, 'dbl', 'low aperture'),
    (0x322, 'dbl', 'high aperture'),
    (0x32A, 'dbl', 'high aperture slope .01 PLC'),
    (0x332, 'dbl', 'high aperture slope .1 PLC'),
    (0x33A, 'dbl', 'high aperture null .01 PLC'),
    (0x342, 'dbl', 'high aperture null .1 PLC'),
    (0x34A, 'u16', 'underload dcv 100mV'),
    (0x34E, 'u16', 'underload dcv 1V'),
    (0x352, 'u16', 'underload dcv 10V'),
    (0x356, 'u16', 'underload dcv 100V'),
    (0x35A, 'u16', 'underload dcv 1000V'),
    (0x35E, 'u16', 'overload dcv 100mV'),
    (0x362, 'u16', 'overload dcv 1V'),
    (0x366, 'u16', 'overload dcv 10V'),
    (0x36A, 'u16', 'overload dcv 100V'),
    (0x36E, 'u16', 'overload dcv 1000V'),
    (0x372, 'u16', 'underload ohm 10'),
    (0x376, 'u16', 'underload ohm 100'),
    (0x37A, 'u16', 'underload ohm 1K'),
    (0x37E, 'u16', 'underload ohm 10K'),
    (0x382, 'u16', 'underload ohm 100K'),
    (0x386, 'u16', 'underload ohm 1M'),
    (0x38A, 'u16', 'underload ohm 10M'),
    (0x38E, 'u16', 'underload ohm 100M'),
    (0x392, 'u16', 'underload ohm 1G'),
    (0x396, 'u16', 'overload ohm 10'),
    (0x39A, 'u16', 'overload ohm 100'),
    (0x39E, 'u16', 'overload ohm 1K'),
    (0x3A2, 'u16', 'overload ohm 10K'),
    (0x3A6, 'u16', 'overload ohm 100K'),
    (0x3AA, 'u16', 'overload ohm 1M'),
    (0x3AE, 'u16', 'overload ohm 10M'),
    (0x3B2, 'u16', 'overload ohm 100M'),
    (0x3B6, 'u16', 'overload ohm 1G'),
    (0x3BA, 'u16', 'underload ohm ocomp 10'),
    (0x3BE, 'u16', 'underload ohm ocomp 100'),
    (0x3C2, 'u16', 'underload ohm ocomp 1K'),
    (0x3C6, 'u16', 'underload ohm ocomp 10K'),
    (0x3CA, 'u16', 'underload ohm ocomp 100K'),
    (0x3CE, 'u16', 'underload ohm ocomp 1M'),
    (0x3D2, 'u16', 'underload ohm ocomp 10M'),
    (0x3D6, 'u16', 'underload ohm ocomp 100M'),
    (0x3DA, 'u16', 'underload ohm ocomp 1G'),
    (0x3DE, 'u16', 'overload ohm ocomp 10'),
    (0x3E2, 'u16', 'overload ohm ocomp 100'),
    (0x3E6, 'u16', 'overload ohm ocomp 1K'),
    (0x3EA, 'u16', 'overload ohm ocomp 10K'),
    (0x3EE, 'u16', 'overload ohm ocomp 100K'),
    (0x3F2, 'u16', 'overload ohm ocomp 1M'),
    (0x3F6, 'u16', 'overload ohm ocomp 10M'),
    (0x3FA, 'u16', 'overload ohm ocomp 100M'),
    (0x3FE, 'u16', 'overload ohm ocomp 1G'),
    (0x402, 'u16', 'underload dci 100nA'),
    (0x406, 'u16', 'Cal_406'),
    (0x40A, 'u16', 'Cal_40a'),
    (0x40E, 'u16', 'Cal_40e'),
    (0x412, 'u16', 'Cal_412'),
    (0x416, 'u16', 'Cal_416'),
    (0x41A, 'u16', 'Cal_41a'),
    (0x41E, 'u16', 'Cal_41e'),
    (0x422, 'u16', 'overload dci 100nA'),
    (0x426, 'u16', 'Cal_426'),
    (0x42A, 'u16', 'Cal_42a'),
    (0x42E, 'u16', 'Cal_42e'),
    (0x432, 'u16', 'Cal_432'),
    (0x436, 'u16', 'Cal_436'),
    (0x43A, 'u16', 'Cal_43a'),
    (0x43E, 'u16', 'Cal_43e'),
    (0x442, 'dbl', 'acal dcv temperature'),
    (0x44A, 'dbl', 'acal ohm temperature'),
    (0x452, 'dbl', 'acal acv temperature'),
    (0x45A, 'u8',  'ac offset dac 10mV'),
    (0x45B, 'u8',  'ac offset dac 100mV'),
    (0x45C, 'u8',  'ac offset dac 1V'),
    (0x45D, 'u8',  'ac offset dac 10V'),
    (0x45E, 'u8',  'ac offset dac 100V'),
    (0x45F, 'u8',  'ac offset dac 1KV'),
    (0x460, 'u8',  'acdc offset dac 10mV'),
    (0x461, 'u8',  'acdc offset dac 100mV'),
    (0x462, 'u8',  'acdc offset dac 1V'),
    (0x463, 'u8',  'acdc offset dac 10V'),
    (0x464, 'u8',  'acdc offset dac 100V'),
    (0x465, 'u8',  'acdc offset dac 1KV'),
    (0x466, 'u8',  'acdci offset dac 100uA'),
    (0x467, 'u8',  'acdci offset dac 1mA'),
    (0x468, 'u8',  'acdci offset dac 10mA'),
    (0x469, 'u8',  'acdci offset dac 100mA'),
    (0x46A, 'u8',  'acdci offset dac 1A'),
    (0x46C, 'u16', 'flatness dac 10mV'),
    (0x46E, 'u16', 'flatness dac 100mV'),
    (0x470, 'u16', 'flatness dac 1V'),
    (0x472, 'u16', 'flatness dac 10V'),
    (0x474, 'u16', 'flatness dac 100V'),
    (0x476, 'u16', 'flatness dac 1KV'),
    (0x478, 'u8',  'level dac dc 1.2V'),
    (0x479, 'u8',  'level dac dc 12V'),
    (0x47C, 'u8',  'level dac ac 1.2V'),
    (0x47D, 'u8',  'level dac ac 12V'),
    (0x47E, 'u8',  'dcv trigger offset 100mV'),
    (0x47F, 'u8',  'dcv trigger offset 1V'),
    (0x480, 'u8',  'dcv trigger offset 10V'),
    (0x481, 'u8',  'dcv trigger offset 100V'),
    (0x482, 'u8',  'dcv trigger offset 1000V'),
    (0x484, 'dbl', 'acdcv sync offset 10mV'),
    (0x48C, 'dbl', 'acdcv sync offset 100mV'),
    (0x494, 'dbl', 'acdcv sync offset 1V'),
    (0x49C, 'dbl', 'acdcv sync offset 10V'),
    (0x4A4, 'dbl', 'acdcv sync offset 100V'),
    (0x4AC, 'dbl', 'acdcv sync offset 1KV'),
    (0x4B4, 'dbl', 'acv sync offset 10mV'),
    (0x4BC, 'dbl', 'acv sync offset 100mV'),
    (0x4C4, 'dbl', 'acv sync offset 1V'),
    (0x4CC, 'dbl', 'acv sync offset 10V'),
    (0x4D4, 'dbl', 'acv sync offset 100V'),
    (0x4DC, 'dbl', 'acv sync offset 1KV'),
    (0x4E4, 'dbl', 'acv sync gain 10mV'),
    (0x4EC, 'dbl', 'acv sync gain 100mV'),
    (0x4F4, 'dbl', 'acv sync gain 1V'),
    (0x4FC, 'dbl', 'acv sync gain 10V'),
    (0x504, 'dbl', 'acv sync gain 100V'),
    (0x50C, 'dbl', 'acv sync gain 1KV'),
    (0x514, 'dbl', 'ab ratio'),
    (0x51C, 'dbl', 'gain ratio'),
    (0x524, 'dbl', 'acv ana gain 10mV'),
    (0x52C, 'dbl', 'acv ana gain 100mV'),
    (0x534, 'dbl', 'acv ana gain 1V'),
    (0x53C, 'dbl', 'acv ana gain 10V'),
    (0x544, 'dbl', 'acv ana gain 100V'),
    (0x54C, 'dbl', 'acv ana gain 1KV'),
    (0x554, 'dbl', 'acv ana offset 10mV'),
    (0x55C, 'dbl', 'acv ana offset 100mV'),
    (0x564, 'dbl', 'acv ana offset 1V'),
    (0x56C, 'dbl', 'acv ana offset 10V'),
    (0x574, 'dbl', 'acv ana offset 100V'),
    (0x57C, 'dbl', 'acv ana offset 1KV'),
    (0x584, 'dbl', 'rmsdc ratio'),
    (0x58C, 'dbl', 'sampdc ratio'),
    (0x594, 'dbl', 'aci gain'),
    (0x59C, 'u16', 'Cal_Sum1'),
    (0x59E, 'dbl', 'Cal_59e'),
    (0x5A6, 'dbl', 'Cal_5a6'),
    (0x5AE, 'dbl', 'Cal_5ae'),
    (0x5B6, 'dbl', 'freq gain'),
    (0x5BE, 'u8',  'attenuator high frequency dac'),
    (0x5C0, 'u8',  'amplifier high frequency dac 10mV'),
    (0x5C1, 'u8',  'amplifier high frequency dac 100mV'),
    (0x5C2, 'u8',  'amplifier high frequency dac 1V'),
    (0x5C3, 'u8',  'amplifier high frequency dac 10V'),
    (0x5C4, 'u8',  'amplifier high frequency dac 100V'),
    (0x5C5, 'u8',  'amplifier high frequency dac 1KV'),
    (0x5C6, 'u8',  'interpolator'),
    (0x5C8, 'u16', 'Cal_Sum2'),
    (0x5CA, 'str', 'Calstr'),       # 80 byte null-padded ASCII (0xA0 = space padding)
    (0x61A, 'u32', 'Calnum'),
    (0x61E, 'u32', 'Cal_SecureCode'),
    (0x622, 'u8',  'Cal_AcalSecure'),
    (0x624, 'u16', 'Cal_Sum3'),
    (0x626, 'u32', 'Destructive Overloads'),
    (0x62A, 'u32', 'Defeats'),
]

TYPE_SIZE = {'dbl': 8, 'i32': 4, 'u32': 4, 'u16': 2, 'u8': 1, 'str': 80}

# ---------------------------------------------------------------------------

def read_field(data, offset, typ):
    s = TYPE_SIZE[typ]
    if offset + s > len(data):
        return None
    chunk = data[offset:offset + s]
    if typ == 'dbl':
        return struct.unpack('>d', chunk)[0]
    elif typ == 'i32':
        return struct.unpack('>i', chunk)[0]
    elif typ == 'u32':
        return struct.unpack('>I', chunk)[0]
    elif typ == 'u16':
        return struct.unpack('>H', chunk)[0]
    elif typ == 'u8':
        return chunk[0]
    elif typ == 'str':
        return chunk.replace(b'\xa0', b' ').rstrip(b'\x00 ').decode('ascii', errors='replace')
    return None


def hex_bytes(data, offset, n):
    return ' '.join(f'{b:02X}' for b in data[offset:offset + n])


def fmt_value(val, typ):
    if val is None:
        return '???'
    if typ == 'dbl':
        return f'{val:.13E}'
    elif typ == 'str':
        return repr(val)
    else:
        return str(val)


def decode(path):
    with open(path, 'rb') as f:
        data = f.read()

    if len(data) != CAL_RAM_SIZE:
        print(f'HIBA: {len(data)} byte, elvárt {CAL_RAM_SIZE}', file=sys.stderr)
        sys.exit(1)

    print(f'HP 3458A cal_ram decoder')
    print(f'Fájl  : {path}')
    print(f'Méret : {len(data)} byte')
    print(f'Base  : 0x{CAL_RAM_BASE:06X}')
    print()
    print(f'{"Abs cím":<10} {"Rel off":<8} {"Típus":<5} {"Hex":<24} {"Érték":<26} Mező')
    print('-' * 100)

    for off, typ, name in FIELDS:
        sz = TYPE_SIZE[typ]
        val = read_field(data, off, typ)
        hex_s = hex_bytes(data, off, min(sz, 8))
        if sz > 8:
            hex_s += ' …'
        val_s = fmt_value(val, typ)
        print(f'0x{CAL_RAM_BASE + off:06X}   0x{off:04X}   {typ:<5} {hex_s:<24} {val_s:<26} {name}')

    print()
    print('=== Összefoglaló ===')
    print(f'  Kalibráció szám    : {read_field(data, 0x61A, "u32")}')
    print(f'  Secure code        : 0x{read_field(data, 0x61E, "u32"):08X}')
    print(f'  Cal_AcalSecure     : {read_field(data, 0x622, "u8")}')
    print(f'  Calstr             : {repr(read_field(data, 0x5CA, "str"))}')
    print(f'  Cal 0°C temp       : {read_field(data, 0x1A4, "dbl"):.6f} °C')
    print(f'  ACAL DCV temp      : {read_field(data, 0x442, "dbl"):.6f} °C')
    print(f'  ACAL OHM temp      : {read_field(data, 0x44A, "dbl"):.6f} °C')
    print(f'  ACAL ACV temp      : {read_field(data, 0x452, "dbl"):.6f} °C')
    print(f'  Destructive OL     : {read_field(data, 0x626, "u32")}')
    print(f'  Defeats            : {read_field(data, 0x62A, "u32")}')
    print()
    print('  Checksum mezők (csak tájékoztató — a műszer saját maga ellenőrzi):')
    print(f'    Cal_Sum0 (0x601BC) : 0x{read_field(data, 0x1BC, "u16"):04X}')
    print(f'    Cal_Sum1 (0x6059C) : 0x{read_field(data, 0x59C, "u16"):04X}')
    print(f'    Cal_Sum2 (0x605C8) : 0x{read_field(data, 0x5C8, "u16"):04X}')
    print(f'    Cal_Sum3 (0x60624) : 0x{read_field(data, 0x624, "u16"):04X}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='HP 3458A cal_ram decoder')
    p.add_argument('bin', nargs='?', default=None,
                   help='cal_ram .bin fájl (alapértelmezett: legfrissebb dump könyvtárból)')
    args = p.parse_args()

    path = args.bin
    if path is None:
        # Legfrissebb dump könyvtár automatikus keresése
        fw_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = sorted(
            [d for d in os.listdir(fw_dir) if d.startswith('dump_')],
            reverse=True
        )
        if not candidates:
            print('Nem található dump_* könyvtár. Add meg a fájlt argumentumként.', file=sys.stderr)
            sys.exit(1)
        path = os.path.join(fw_dir, candidates[0], 'dump_01_cal_ram.bin')
        print(f'[auto] {path}')

    decode(path)
