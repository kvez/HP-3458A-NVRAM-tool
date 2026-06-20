"""HP 3458A kapcsolat réteg — TCP Bridge (Prologix) vagy NI-488.2 DLL közvetlen."""
import socket
import time
import ctypes


class ConnError(Exception):
    pass


class BaseConn:
    def send(self, cmd: str): raise NotImplementedError
    def query(self, cmd: str, tmo: float = 5.0) -> str: raise NotImplementedError
    def close(self): pass


# ── TCP Bridge (Prologix GPIB-ETHERNET) ─────────────────────────────────────

class TCPConn(BaseConn):
    def __init__(self, host: str, port: int = 1234, gpib_addr: int = 22,
                 tmo: float = 15.0):
        self._s = socket.create_connection((host, port), timeout=tmo)
        self._buf = b''
        for cmd in ['++mode 1', f'++addr {gpib_addr}', '++auto 0',
                    '++eos 2', '++eoi 1', '++read_tmo_ms 2000', '++ifc']:
            self._s.sendall((cmd + '\n').encode())
            time.sleep(0.05)
        time.sleep(0.15)

    def _raw(self, cmd: str):
        self._s.sendall((cmd.rstrip('\n') + '\n').encode())

    def _readline(self, tmo: float = 5.0) -> str:
        deadline = time.time() + tmo
        while b'\n' not in self._buf:
            rem = max(0.1, deadline - time.time())
            if rem <= 0:
                raise TimeoutError('Nincs válasz a műszertől')
            self._s.settimeout(rem)
            chunk = self._s.recv(4096)
            if not chunk:
                raise ConnError('A kapcsolat megszakadt')
            self._buf += chunk
        line, self._buf = self._buf.split(b'\n', 1)
        return line.strip().decode('ascii', errors='replace')

    def gpib_clear(self):
        """GPIB Selected Device Clear (SDC) — Prologix ++clr parancs.
        Törli a műszer GPIB input/output bufferét. Stuck/teli buffer esetén.
        SDC a HP 3458A END módját END OFF-ra reseti (power-on default) —
        ezért END ALWAYS visszaállítása kötelező utána, különben az ibrd
        soha nem kap EOI jelet és 1MB null byte-ot olvas (buffer-telt).
        """
        self._raw('++clr')
        time.sleep(1.5)
        self._raw('TARM HOLD')
        time.sleep(0.15)
        self._raw('END ALWAYS')
        time.sleep(0.1)

    def send(self, cmd: str):
        self._raw(cmd)
        time.sleep(0.12)

    def query(self, cmd: str, tmo: float = 5.0) -> str:
        self._raw(cmd)
        time.sleep(0.05)
        self._raw('++ifc')
        time.sleep(0.15)
        self._raw('++read 10')
        return self._readline(tmo)

    def close(self):
        try: self._s.close()
        except Exception: pass


# ── NI-488.2 DLL közvetlen ──────────────────────────────────────────────────

_NI_PATHS = [
    r'C:\Windows\System32\ni4882.dll',
    'ni4882.dll',
    r'C:\Windows\System32\gpib-32.dll',
    'gpib-32.dll',
]
_T10s = 13   # NI timeout konstans: ~10 s
_ERR  = 0x8000

# NI-488.2 ibtmo() timeout kód-tábla: (felső határ másodpercben, kód).
# A query(tmo=...) hívásnál a legkisebb olyan kódot választjuk, amelynek
# a határa >= a kért tmo — így a hívó által kért timeout legalább annyi,
# soha nem kevesebb (csak felfelé kerekítünk a driver discrét lépcsőihez).
_TMO_TABLE = [
    (1e-5, 1), (3e-5, 2), (1e-4, 3), (3e-4, 4), (1e-3, 5), (3e-3, 6),
    (1e-2, 7), (3e-2, 8), (1e-1, 9), (3e-1, 10), (1, 11), (3, 12),
    (10, 13), (30, 14), (100, 15), (300, 16), (1000, 17),
]


def _tmo_code(seconds: float) -> int:
    for threshold, code in _TMO_TABLE:
        if seconds <= threshold:
            return code
    return 17  # T1000s — leghosszabb elérhető


class NIConn(BaseConn):
    def __init__(self, board: int = 0, gpib_addr: int = 22, tmo: int = _T10s):
        lib = None
        for path in _NI_PATHS:
            try:
                lib = ctypes.WinDLL(path)
                break
            except OSError:
                pass
        if lib is None:
            raise ConnError('ni4882.dll / gpib-32.dll nem található')

        for name, ret, args in [
            ('ibdev', ctypes.c_int, [ctypes.c_int] * 6),
            ('ibwrt', ctypes.c_int, [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]),
            ('ibrd',  ctypes.c_int, [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]),
            ('ibclr', ctypes.c_int, [ctypes.c_int]),
            ('ibonl', ctypes.c_int, [ctypes.c_int, ctypes.c_int]),
        ]:
            getattr(lib, name).restype  = ret
            getattr(lib, name).argtypes = args

        # ibtmo régebbi DLL-ekben elérhető, de ni4882.dll újabb verzióiban nincs exportálva.
        self._ibtmo = None
        try:
            lib.ibtmo.restype  = ctypes.c_int
            lib.ibtmo.argtypes = [ctypes.c_int, ctypes.c_int]
            self._ibtmo = lib.ibtmo
        except AttributeError:
            pass

        ud = lib.ibdev(board, gpib_addr, 0, tmo, 1, 0)
        if ud < 0:
            raise ConnError(f'ibdev sikertelen: ud={ud}  (helytelen board/GPIB cím?)')
        lib.ibclr(ud)
        time.sleep(0.5)
        self._lib, self._ud = lib, ud

    def _ibcnt(self) -> int:
        for sym in ('ThreadIbcnt', 'ibcnt'):
            try: return ctypes.c_long.in_dll(self._lib, sym).value
            except OSError: pass
        return 0

    def send(self, cmd: str):
        b = (cmd.rstrip('\n') + '\n').encode()
        st = self._lib.ibwrt(self._ud, b, len(b))
        if st & _ERR:
            raise ConnError(f'ibwrt hiba: ibsta=0x{st:04X}')
        time.sleep(0.1)

    def query(self, cmd: str, tmo: float = 5.0) -> str:
        if self._ibtmo is not None:
            self._ibtmo(self._ud, _tmo_code(tmo))
        self.send(cmd)
        buf = ctypes.create_string_buffer(8192)
        st = self._lib.ibrd(self._ud, buf, 8192)
        if st & _ERR:
            raise ConnError(f'ibrd hiba: ibsta=0x{st:04X}')
        n = self._ibcnt()
        return buf.raw[:n].rstrip(b'\x00\r\n').decode('ascii', errors='replace').strip()

    def gpib_clear(self):
        """GPIB Selected Device Clear (ibclr) — flush műszer GPIB buffer."""
        self._lib.ibclr(self._ud)
        time.sleep(1.0)

    def close(self):
        try: self._lib.ibonl(self._ud, 0)
        except Exception: pass
