#!/usr/bin/env python3
"""HP 3458A Kalibráló Eszköz — tkinter GUI
Futtatás: python hp3458a_gui.py
"""
import hashlib
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from hp3458a_conn   import TCPConn, NIConn, ConnError
from hp3458a_instr  import HP3458A
from hp3458a_calram import CalRAMCodec, CAL_RAM_SIZE

SCRIPT_DIR = Path(__file__).parent

# Fagyasztott EXE-nél (PyInstaller) az írható fájlok (ini, dumps, log) az
# executable mellé kerülnek, nem a csak-olvasható bundle-be.
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    _BUNDLE_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = SCRIPT_DIR
    _BUNDLE_DIR = SCRIPT_DIR

DUMPS_DIR = APP_DIR / 'dumps'
DUMPS_DIR.mkdir(exist_ok=True)
PREF_FILE = APP_DIR / 'hp3458a_tool.ini'
LOG_FILE  = DUMPS_DIR / 'hp3458a_tool.log'
LOGO_PATH = _BUNDLE_DIR / 'psnd_ikon.png' if getattr(sys, 'frozen', False) else SCRIPT_DIR.parent.parent / 'psnd_ikon.png'

# ── i18n ────────────────────────────────────────────────────────────────────

VERSION = 'V0.9 Beta'

_S = {
'app_title':      {'hu': 'HP 3458A NVRAM Programozó',    'en': 'HP 3458A NVRAM Tool',
                   'de': 'HP 3458A NVRAM-Programmierer'},
'menu_lang':      {'hu': 'Nyelv',                        'en': 'Language',           'de': 'Sprache'},
'menu_help':      {'hu': 'Súgó',                         'en': 'Help',               'de': 'Hilfe'},
'menu_about':     {'hu': 'Névjegy',                      'en': 'About',              'de': 'Über'},
'about_text':     {'hu': f'HP 3458A Kalibráló Eszköz\nGPIB Cal_RAM dump/upload/decode/edit\n{VERSION}',
                   'en': f'HP 3458A Calibration Tool\nGPIB Cal_RAM dump/upload/decode/edit\n{VERSION}',
                   'de': f'HP 3458A Kalibrierwerkzeug\nGPIB Cal_RAM dump/upload/decode/edit\n{VERSION}'},
# Kapcsolat
'conn_frame':     {'hu': 'Kapcsolat',                    'en': 'Connection',         'de': 'Verbindung'},
'conn_tcp':       {'hu': 'TCP Bridge (Prologix)',         'en': 'TCP Bridge (Prologix)',
                   'de': 'TCP-Bridge (Prologix)'},
'conn_ni':        {'hu': 'Közvetlen (NI-488.2 DLL)',     'en': 'Direct (NI-488.2 DLL)',
                   'de': 'Direkt (NI-488.2 DLL)'},
'lbl_host':       {'hu': 'Host / IP:',                   'en': 'Host / IP:',         'de': 'Host / IP:'},
'lbl_port':       {'hu': 'Port:',                        'en': 'Port:',              'de': 'Port:'},
'lbl_board':      {'hu': 'GPIB Board:',                  'en': 'GPIB Board:',        'de': 'GPIB-Karte:'},
'lbl_gpib':       {'hu': 'GPIB Cím:',                   'en': 'GPIB Address:',      'de': 'GPIB-Adresse:'},
'btn_connect':    {'hu': 'Csatlakozás',                  'en': 'Connect',            'de': 'Verbinden'},
'btn_disconnect': {'hu': 'Lecsatlakozás',                'en': 'Disconnect',         'de': 'Trennen'},
'btn_test_id':    {'hu': 'Azonosítás (ID?)',             'en': 'Identify (ID?)',     'de': 'Identifizieren (ID?)'},
'status_ok':      {'hu': '● Kapcsolódva',                'en': '● Connected',        'de': '● Verbunden'},
'status_err':     {'hu': '● Hiba',                      'en': '● Error',            'de': '● Fehler'},
'status_none':    {'hu': '○ Nincs kapcsolat',            'en': '○ Not connected',    'de': '○ Nicht verbunden'},
# Cal_RAM tab
'tab_calram':     {'hu': 'Cal_RAM',                      'en': 'Cal_RAM',            'de': 'Cal_RAM'},
'btn_dump':       {'hu': 'Dump (letöltés)',              'en': 'Dump (download)',    'de': 'Dump (herunterladen)'},
'btn_load_bin':   {'hu': 'Betöltés .bin-ből',           'en': 'Load from .bin',     'de': 'Aus .bin laden'},
'btn_save_bin':   {'hu': 'Mentés .bin',                  'en': 'Save .bin',          'de': '.bin speichern'},
'btn_save_txt':   {'hu': 'Decoded .txt mentés',          'en': 'Save decoded .txt',  'de': 'Decodiertes .txt speichern'},
'btn_upload':     {'hu': 'Feltöltés műszerre',           'en': 'Upload to meter',    'de': 'Auf Gerät hochladen'},
'btn_verify':     {'hu': 'Verify (visszaolvasás)',       'en': 'Verify (readback)',  'de': 'Verify (Rücklesen)'},
'btn_checksum':   {'hu': 'Checksum újraszámítás',        'en': 'Recalculate Checksums',
                   'de': 'Prüfsummen neu berechnen'},
'btn_edit':       {'hu': 'Szerkesztés',                  'en': 'Edit field',         'de': 'Feld bearbeiten'},
'lbl_passes':     {'hu': 'Dump menetek:',                'en': 'Dump passes:',       'de': 'Dump-Durchläufe:'},
'col_offset':     {'hu': 'Offset',                       'en': 'Offset',             'de': 'Offset'},
'col_name':       {'hu': 'Mező neve',                    'en': 'Field name',        'de': 'Feldname'},
'col_type':       {'hu': 'Típus',                        'en': 'Type',               'de': 'Typ'},
'col_value':      {'hu': 'Érték',                        'en': 'Value',              'de': 'Wert'},
'col_mod':        {'hu': '✎',                           'en': '✎',                 'de': '✎'},
'csum_label':     {'hu': 'Checksum állapot:',            'en': 'Checksum status:',   'de': 'Prüfsummen-Status:'},
# Settings tab
'tab_settings':   {'hu': 'Settings RAM',                 'en': 'Settings RAM',       'de': 'Settings RAM'},
'btn_dump_32k':   {'hu': 'Dump 32KB (~17 perc)',         'en': 'Dump 32KB (~17 min)', 'de': 'Dump 32KB (~17 Min)'},
'btn_dump_64k':   {'hu': 'Teljes dump 64KB (~34 perc)', 'en': 'Full dump 64KB (~34 min)',
                   'de': 'Vollständiger Dump 64KB (~34 Min)'},
'btn_save_set':   {'hu': 'Mentés .bin',                  'en': 'Save .bin',          'de': '.bin speichern'},
# Report tab
'tab_report':     {'hu': 'Cal Riport',                   'en': 'Cal Report',         'de': 'Cal-Bericht'},
'lbl_calstr':     {'hu': 'CALSTR (80 char max):',        'en': 'CALSTR (80 char max):',
                   'de': 'CALSTR (max. 80 Zeichen):'},
'btn_write_cstr': {'hu': 'CALSTR írása műszerre',        'en': 'Write CALSTR to meter',
                   'de': 'CALSTR auf Gerät schreiben'},
'btn_report_gen': {'hu': 'Riport generálás',             'en': 'Generate Report',    'de': 'Bericht erstellen'},
'btn_report_save':{'hu': 'Mentés .txt',                  'en': 'Save .txt',          'de': '.txt speichern'},
# Log
'tab_log':        {'hu': 'Log',                          'en': 'Log',                'de': 'Log'},
'btn_log_clear':  {'hu': 'Törlés',                       'en': 'Clear',              'de': 'Löschen'},
# Dialógusok
'dlg_edit_title': {'hu': 'Mező szerkesztése',            'en': 'Edit field',         'de': 'Feld bearbeiten'},
'dlg_diff_title': {'hu': 'Változások áttekintése',       'en': 'Review changes',     'de': 'Änderungen prüfen'},
'dlg_diff_head':  {'hu': 'A következő mezők változtak:', 'en': 'The following fields changed:',
                   'de': 'Folgende Felder wurden geändert:'},
'dlg_proceed':    {'hu': 'Folytatás (feltöltés)',        'en': 'Proceed (upload)',   'de': 'Fortsetzen (Hochladen)'},
'btn_cancel':     {'hu': 'Mégsem',                       'en': 'Cancel',             'de': 'Abbrechen'},
'btn_ok':         {'hu': 'OK',                           'en': 'OK',                 'de': 'OK'},
'lbl_old':        {'hu': 'Régi érték:',                  'en': 'Old value:',         'de': 'Alter Wert:'},
'lbl_new':        {'hu': 'Új érték:',                    'en': 'New value:',         'de': 'Neuer Wert:'},
'lbl_type_hint':  {'hu': 'Típus',                        'en': 'Type',               'de': 'Typ'},
# Progress
'prog_dump':      {'hu': 'Cal_RAM letöltés...',          'en': 'Downloading Cal_RAM...',
                   'de': 'Cal_RAM wird herunterladen...'},
'prog_upload':    {'hu': 'Cal_RAM feltöltés...',         'en': 'Uploading Cal_RAM...', 'de': 'Cal_RAM wird hochgeladen...'},
'prog_verify':    {'hu': 'Cal_RAM ellenőrzés...',        'en': 'Verifying Cal_RAM...', 'de': 'Cal_RAM wird überprüft...'},
'prog_settings':  {'hu': 'Settings RAM letöltés...',     'en': 'Downloading Settings RAM...',
                   'de': 'Settings RAM wird herunterladen...'},
'btn_stop':       {'hu': 'Megszakítás',                  'en': 'Cancel',             'de': 'Abbrechen'},
'btn_cleanup':    {'hu': 'Settings_RAM törlés',          'en': 'Cleanup settings_RAM', 'de': 'Settings_RAM bereinigen'},
'btn_nmi_test':   {'hu': 'NMI Teszt',                   'en': 'NMI Test',           'de': 'NMI-Test'},
'btn_words_only': {'hu': 'Módosított szavak',            'en': 'Changed words only', 'de': 'Nur geänderte Wörter'},
'btn_chunked':    {'hu': 'Szavankénti feltöltés (~1 óra)', 'en': 'Word-by-word upload (~1 hour)',
                   'de': 'Wortweises Hochladen (~1 Stunde)'},
'btn_rescue':     {'hu': 'Rescue DEFKEY (F1)',           'en': 'Rescue DEFKEY (F1)',
                   'de': 'Rescue DEFKEY (F1)'},
'chk_autoclean':  {'hu': 'Verify után: settings_RAM cleanup',
                   'en': 'After verify: cleanup settings_RAM',
                   'de': 'Nach Verify: settings_RAM bereinigen'},
'prog_cleanup':   {'hu': 'Settings_RAM cleanup...',      'en': 'Cleaning up settings_RAM...',
                   'de': 'Settings_RAM wird bereinigt...'},
'cleanup_ok':     {'hu': 'Settings_RAM cleanup kész ({} word nullázva)',
                   'en': 'Settings_RAM cleanup done ({} words zeroed)',
                   'de': 'Settings_RAM-Bereinigung fertig ({} Wörter genullt)'},
}

_lang = 'hu'

def t(key: str) -> str:
    entry = _S.get(key)
    if not entry: return key
    return entry.get(_lang, entry.get('en', entry.get('hu', key)))


def _load_prefs() -> dict:
    prefs = {'lang': 'hu', 'host': '192.168.2.88', 'port': '1234',
             'gpib': '22', 'board': '0', 'conn_type': 'tcp'}
    if PREF_FILE.exists():
        for line in PREF_FILE.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                prefs[k.strip()] = v.strip()
    return prefs


def _save_prefs(prefs: dict):
    PREF_FILE.write_text('\n'.join(f'{k}={v}' for k, v in prefs.items()),
                         encoding='utf-8')


# ── Induló biztonsági figyelmeztetés (3 nyelven, minden indításnál) ──────────

_SAFETY_WARNING_HU = (
    'Figyelem!\n\n'
    'Ez a program kísérleti jellegű, tanulási és kutatási céllal készült. '
    'Nem dokumentált és nem gyártó által megerősített folyamatokra épül.\n\n'
    'Használata kockázattal jár: a műszerben kár keletkezhet, illetve a '
    'Cal_RAM adatai megsérülhetnek vagy elveszhetnek.\n\n'
    'Csak ellenőrzött biztonsági mentés után, illetve olyan műszeren javasolt '
    'kipróbálni, ahol a Cal_RAM adatai nem kritikusak vagy reprodukálhatók.\n\n'
    'A fejlesztés és tesztelés során használt referencia műszer: HP gyártmányú, '
    'REV9 verziójú készülék, A5 REV A panelen MC68HC000P8 processzorral.\n\n'
    'A programot mindenki kizárólag saját felelősségére használja.'
)

_SAFETY_WARNING_EN = (
    'Warning!\n\n'
    'This program is experimental, created for learning and research purposes. '
    'It is based on undocumented procedures not confirmed by the manufacturer.\n\n'
    'Its use carries risk: the instrument may be damaged, and the Cal_RAM data '
    'may be corrupted or lost.\n\n'
    'It is recommended to try it only after a verified backup, or on an '
    'instrument where the Cal_RAM data is not critical or is reproducible.\n\n'
    'Reference instrument used during development and testing: an HP-made, '
    'REV9 version unit, on an A5 REV A board with an MC68HC000P8 processor.\n\n'
    'Everyone uses this program entirely at their own risk.'
)

_SAFETY_WARNING_DE = (
    'Achtung!\n\n'
    'Dieses Programm ist experimentell und wurde zu Lern- und Forschungszwecken '
    'erstellt. Es basiert auf nicht dokumentierten und vom Hersteller nicht '
    'bestätigten Verfahren.\n\n'
    'Die Nutzung ist mit Risiken verbunden: Das Gerät kann beschädigt werden, '
    'und die Cal_RAM-Daten können beschädigt werden oder verloren gehen.\n\n'
    'Es wird empfohlen, es nur nach einer geprüften Datensicherung auszuprobieren, '
    'bzw. an einem Gerät, dessen Cal_RAM-Daten nicht kritisch oder reproduzierbar '
    'sind.\n\n'
    'Referenzgerät, das während der Entwicklung und Tests verwendet wurde: ein '
    'Gerät der Marke HP, Version REV9, auf einer A5-REV-A-Platine mit einem '
    'MC68HC000P8-Prozessor.\n\n'
    'Jeder nutzt dieses Programm ausschließlich auf eigene Verantwortung.'
)


class SafetyWarningDialog(tk.Toplevel):
    """Minden induláskor megjelenő figyelmeztetés — HU+EN+DE egyszerre,
    függetlenül az aktuálisan beállított UI nyelvtől (biztonsági szöveg,
    ne lehessen csak az aktuális nyelv miatt kihagyni)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f'⚠ {t("menu_about")} / Warning / Achtung — {VERSION}')
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill='both', expand=True)

        txt = tk.Text(frame, width=86, height=28, wrap='word',
                       font=('TkDefaultFont', 9))
        scroll = ttk.Scrollbar(frame, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        content = (
            _SAFETY_WARNING_HU + '\n\n' + ('─' * 70) + '\n\n' +
            _SAFETY_WARNING_EN + '\n\n' + ('─' * 70) + '\n\n' +
            _SAFETY_WARNING_DE
        )
        txt.insert('1.0', content)
        txt.config(state='disabled')

        btn_text = 'Megértettem / I understand / Verstanden'
        ttk.Button(frame, text=btn_text, command=self._close).grid(
            row=1, column=0, columnspan=2, pady=(10, 0))

        self.protocol('WM_DELETE_WINDOW', self._close)
        self.update_idletasks()
        self._center_on(parent)
        self.wait_window(self)

    def _center_on(self, parent):
        try:
            parent.update_idletasks()
            x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f'+{max(x, 0)}+{max(y, 0)}')
        except Exception:
            pass

    def _close(self):
        self.grab_release()
        self.destroy()


# ── Progress dialógus ────────────────────────────────────────────────────────

class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title: str, maximum: int = 100):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self._cancelled = False

        self._lbl = ttk.Label(self, text='', width=55, anchor='w')
        self._lbl.pack(padx=16, pady=(14, 4))

        self._bar = ttk.Progressbar(self, length=420, maximum=maximum or 1)
        self._bar.pack(padx=16, pady=4)

        self._time_lbl = ttk.Label(self, text='', anchor='w')
        self._time_lbl.pack(padx=16, fill='x')

        ttk.Button(self, text=t('btn_stop'), command=self._cancel).pack(pady=(6, 12))
        self._t0 = time.time()
        self.transient(parent)
        self.protocol('WM_DELETE_WINDOW', lambda: None)
        self.update()

    def _cancel(self):
        if messagebox.askyesno(
                'Megszakítás',
                'Biztosan megszakítja a műveletet?\n\nAz aktuális szó befejezése után áll le.',
                parent=self):
            self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def update_progress(self, current: int, total: int, msg: str = ''):
        try:
            self._bar['maximum'] = max(total, 1)
            self._bar['value']   = current
            self._lbl.config(text=msg)
            elapsed = time.time() - self._t0
            if current > 0 and current < total:
                eta = elapsed / current * (total - current)
                self._time_lbl.config(text=f'Eltelt: {elapsed:.0f}s  ·  Maradék: ~{eta:.0f}s')
            else:
                self._time_lbl.config(text=f'Eltelt: {elapsed:.0f}s')
            self.update_idletasks()
        except Exception:
            pass

    def close(self):
        try: self.destroy()
        except Exception: pass


# ── Mező szerkesztő dialógus ─────────────────────────────────────────────────

class EditDialog(tk.Toplevel):
    def __init__(self, parent, field: dict, codec: CalRAMCodec, on_save):
        super().__init__(parent)
        self.title(t('dlg_edit_title'))
        self.resizable(False, False)
        self.grab_set()
        self._codec   = codec
        self._field   = field
        self._on_save = on_save

        name = field['name']
        typ  = field['typ']
        cur  = field['value_str']

        ttk.Label(self, text=name, font=('TkDefaultFont', 10, 'bold')).pack(padx=16, pady=(12, 2))
        ttk.Label(self, text=f'{t("lbl_type_hint")}: {typ}  |  Offset: 0x{field["offset"]:04X}',
                  foreground='gray').pack(padx=16)

        ttk.Label(self, text=t('lbl_old')).pack(padx=16, pady=(8, 0), anchor='w')
        old_lbl = ttk.Label(self, text=cur, foreground='gray', wraplength=380)
        old_lbl.pack(padx=16, anchor='w')

        ttk.Label(self, text=t('lbl_new')).pack(padx=16, pady=(8, 0), anchor='w')
        self._var = tk.StringVar(value=cur)
        width = 55 if typ in ('dbl', 'str') else 30
        entry = ttk.Entry(self, textvariable=self._var, width=width)
        entry.pack(padx=16, pady=2, fill='x')
        entry.select_range(0, tk.END)
        entry.focus_set()
        entry.bind('<Return>', lambda e: self._ok())

        self._err_lbl = ttk.Label(self, text='', foreground='red', wraplength=380)
        self._err_lbl.pack(padx=16, pady=2)

        bf = ttk.Frame(self)
        bf.pack(pady=(4, 12))
        ttk.Button(bf, text=t('btn_ok'),     command=self._ok).pack(side='left', padx=8)
        ttk.Button(bf, text=t('btn_cancel'), command=self.destroy).pack(side='left', padx=8)
        self.transient(parent)
        self.update()

    def _ok(self):
        val = self._var.get().strip()
        err = self._codec.validate_field_str(self._field['name'], val)
        if err:
            self._err_lbl.config(text=err)
            return
        self._codec.set_field_str(self._field['name'], val)
        self._on_save(self._field['name'])
        self.destroy()


# ── Diff / Változás áttekintő dialógus ──────────────────────────────────────

class DiffDialog(tk.Toplevel):
    def __init__(self, parent, diffs: list, on_proceed):
        super().__init__(parent)
        self.title(t('dlg_diff_title'))
        self.grab_set()
        self._proceed = False

        ttk.Label(self, text=t('dlg_diff_head'), font=('TkDefaultFont', 10, 'bold')).pack(
            padx=16, pady=(12, 4))

        frame = ttk.Frame(self)
        frame.pack(padx=16, fill='both', expand=True)

        cols = ('name', 'old', 'new')
        tree = ttk.Treeview(frame, columns=cols, show='headings', height=min(len(diffs), 15))
        tree.heading('name', text='Mező' if _lang == 'hu' else 'Field')
        tree.heading('old',  text='Régi' if _lang == 'hu' else 'Old')
        tree.heading('new',  text='Új'   if _lang == 'hu' else 'New')
        tree.column('name', width=230); tree.column('old', width=200); tree.column('new', width=200)
        sb = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        for name, old, new in diffs:
            tree.insert('', 'end', values=(name, old[:40], new[:40]))

        bf = ttk.Frame(self)
        bf.pack(pady=(8, 12))
        ttk.Button(bf, text=t('dlg_proceed'), command=self._do_proceed).pack(side='left', padx=8)
        ttk.Button(bf, text=t('btn_cancel'),  command=self.destroy).pack(side='left', padx=8)
        self.transient(parent)

    def _do_proceed(self):
        self._proceed = True
        self.destroy()


# ── Főalkalmazás ──────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global _lang
        self._prefs   = _load_prefs()
        _lang         = self._prefs.get('lang', 'hu')
        self._conn    = None   # BaseConn
        self._instr   = None   # HP3458A
        self._codec   = None   # CalRAMCodec
        self._set_data = None  # bytes (settings dump)
        self._i18n_w  = []    # [(widget, attr, key)] for language refresh
        self._stop_ev = threading.Event()
        self._writing = False
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close_request)
        self.after(50, lambda: SafetyWarningDialog(self))
        self.after(100, lambda: self._log(f'Indulás: {VERSION} · Python {sys.version.split()[0]}'))

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.title(f"{t('app_title')} — {VERSION}")
        self.resizable(True, True)
        self._icon_img = None
        if LOGO_PATH.exists():
            try:
                self._icon_img = tk.PhotoImage(file=str(LOGO_PATH))
                self.iconphoto(True, self._icon_img)
            except Exception:
                pass
        self._build_menu()
        self._build_conn_frame()
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=6, pady=(0, 4))
        self._nb = nb
        self._build_calram_tab(nb)
        self._build_settings_tab(nb)
        self._build_report_tab(nb)
        self._build_log_frame()
        self._set_connected(False)

    def _on_close_request(self):
        if self._writing:
            messagebox.showwarning(
                'Írás folyamatban',
                'Cal_RAM írás folyamatban!\n\n'
                'Először szakítsd meg a "Megszakítás" gombbal, majd zárd be a programot.')
        else:
            self.destroy()

    def _build_menu(self):
        mb = tk.Menu(self)
        lang_m = tk.Menu(mb, tearoff=0)
        lang_m.add_command(label='Magyar',  command=lambda: self._switch_lang('hu'))
        lang_m.add_command(label='English', command=lambda: self._switch_lang('en'))
        lang_m.add_command(label='Deutsch', command=lambda: self._switch_lang('de'))
        mb.add_cascade(label=t('menu_lang'), menu=lang_m)

        help_m = tk.Menu(mb, tearoff=0)
        help_m.add_command(label=t('menu_about'), command=self._show_about)
        mb.add_cascade(label=t('menu_help'), menu=help_m)
        self.config(menu=mb)

    def _build_conn_frame(self):
        cf = ttk.LabelFrame(self, text=t('conn_frame'), padding=6)
        cf.pack(fill='x', padx=6, pady=4)

        self._conn_type = tk.StringVar(value=self._prefs.get('conn_type', 'tcp'))

        rb1 = ttk.Radiobutton(cf, text=t('conn_tcp'), variable=self._conn_type,
                               value='tcp', command=self._on_conn_type_change)
        rb2 = ttk.Radiobutton(cf, text=t('conn_ni'),  variable=self._conn_type,
                               value='ni',  command=self._on_conn_type_change)
        rb1.grid(row=0, column=0, sticky='w', padx=4)
        rb2.grid(row=0, column=1, sticky='w', padx=4)

        # TCP fields
        self._tcp_frame = ttk.Frame(cf)
        ttk.Label(self._tcp_frame, text=t('lbl_host')).grid(row=0, column=0, sticky='e', padx=4)
        self._host_var = tk.StringVar(value=self._prefs.get('host', '192.168.2.88'))
        ttk.Entry(self._tcp_frame, textvariable=self._host_var, width=18).grid(row=0, column=1, padx=4)
        ttk.Label(self._tcp_frame, text=t('lbl_port')).grid(row=0, column=2, sticky='e', padx=4)
        self._port_var = tk.StringVar(value=self._prefs.get('port', '1234'))
        ttk.Entry(self._tcp_frame, textvariable=self._port_var, width=7).grid(row=0, column=3, padx=4)

        # NI DLL fields
        self._ni_frame = ttk.Frame(cf)
        ttk.Label(self._ni_frame, text=t('lbl_board')).grid(row=0, column=0, sticky='e', padx=4)
        self._board_var = tk.StringVar(value=self._prefs.get('board', '0'))
        ttk.Entry(self._ni_frame, textvariable=self._board_var, width=5).grid(row=0, column=1, padx=4)

        # GPIB address (common)
        gpib_f = ttk.Frame(cf)
        ttk.Label(gpib_f, text=t('lbl_gpib')).grid(row=0, column=0, sticky='e', padx=4)
        self._gpib_var = tk.StringVar(value=self._prefs.get('gpib', '22'))
        ttk.Entry(gpib_f, textvariable=self._gpib_var, width=5).grid(row=0, column=1, padx=4)

        self._tcp_frame.grid(row=1, column=0, columnspan=2, sticky='w', pady=2)
        self._ni_frame.grid(row=2, column=0, columnspan=2, sticky='w', pady=2)
        gpib_f.grid(row=3, column=0, columnspan=2, sticky='w')

        # Buttons + status
        btn_f = ttk.Frame(cf)
        btn_f.grid(row=0, column=2, rowspan=4, padx=16)
        self._btn_conn    = ttk.Button(btn_f, text=t('btn_connect'),    command=self._connect)
        self._btn_disc    = ttk.Button(btn_f, text=t('btn_disconnect'), command=self._disconnect)
        self._btn_testid  = ttk.Button(btn_f, text=t('btn_test_id'),    command=self._test_id)
        self._btn_clrbuf  = ttk.Button(btn_f, text='GPIB Clear (SDC)', command=self._do_gpib_clear)
        self._btn_conn.pack(fill='x', pady=2)
        self._btn_disc.pack(fill='x', pady=2)
        self._btn_testid.pack(fill='x', pady=2)
        self._btn_clrbuf.pack(fill='x', pady=2)
        self._btn_disc.config(state='disabled')
        self._btn_testid.config(state='disabled')
        self._btn_clrbuf.config(state='disabled')

        self._status_lbl = ttk.Label(cf, text=t('status_none'), foreground='gray')
        self._status_lbl.grid(row=4, column=0, columnspan=3, pady=(4, 0), sticky='w')

        self._on_conn_type_change()

    def _on_conn_type_change(self):
        is_tcp = (self._conn_type.get() == 'tcp')
        if is_tcp:
            self._tcp_frame.grid()
            self._ni_frame.grid_remove()
        else:
            self._tcp_frame.grid_remove()
            self._ni_frame.grid()

    def _build_calram_tab(self, nb):
        tab = ttk.Frame(nb, padding=4)
        nb.add(tab, text=t('tab_calram'))
        self._calram_tab = tab

        # Toolbar
        tb = ttk.Frame(tab)
        tb.pack(fill='x', pady=(0, 4))

        self._passes_var   = tk.IntVar(value=3)
        self._autoclean_var = tk.BooleanVar(value=True)

        ttk.Label(tb, text=t('lbl_passes')).pack(side='left')
        for n in (1, 2, 3):
            ttk.Radiobutton(tb, text=str(n), variable=self._passes_var, value=n).pack(side='left')

        self._dump_btn    = ttk.Button(tb, text=t('btn_dump'),     command=self._do_dump_calram)
        self._loadb_btn   = ttk.Button(tb, text=t('btn_load_bin'), command=self._load_bin)
        self._saveb_btn   = ttk.Button(tb, text=t('btn_save_bin'), command=self._save_bin)
        self._savet_btn   = ttk.Button(tb, text=t('btn_save_txt'), command=self._save_txt)
        self._upload_btn  = ttk.Button(tb, text=t('btn_upload'),   command=self._do_upload)
        self._verify_btn  = ttk.Button(tb, text=t('btn_verify'),   command=self._do_verify)
        self._csum_btn    = ttk.Button(tb, text=t('btn_checksum'), command=self._do_checksum)
        self._edit_btn    = ttk.Button(tb, text=t('btn_edit'),     command=self._do_edit)
        self._cleanup_btn = ttk.Button(tb, text=t('btn_cleanup'),  command=self._do_cleanup)

        for btn in (self._dump_btn, self._loadb_btn, self._saveb_btn, self._savet_btn,
                    self._upload_btn, self._verify_btn, self._csum_btn, self._edit_btn,
                    self._cleanup_btn):
            btn.pack(side='left', padx=2)

        ttk.Checkbutton(tb, text=t('chk_autoclean'),
                        variable=self._autoclean_var).pack(side='left', padx=(8, 2))

        # NMI debug eszközök — második sor
        tb2 = ttk.Frame(tab)
        tb2.pack(fill='x', pady=(0, 4))
        ttk.Label(tb2, text='NMI debug:', foreground='gray').pack(side='left', padx=(2, 4))
        self._nmi_test_btn  = ttk.Button(tb2, text=t('btn_nmi_test'),
                                         command=self._do_nmi_test)
        self._words_btn     = ttk.Button(tb2, text=t('btn_words_only'),
                                         command=self._do_upload_changed)
        self._chunked_btn   = ttk.Button(tb2, text=t('btn_chunked'),
                                         command=self._do_upload_chunked)
        for btn in (self._nmi_test_btn, self._words_btn, self._chunked_btn):
            btn.pack(side='left', padx=2)
            btn.config(state='disabled')
        ttk.Label(tb2, text=' │ ', foreground='gray').pack(side='left')
        self._rescue_btn = ttk.Button(tb2, text=t('btn_rescue'),
                                      command=self._do_install_rescue_defkey)
        self._rescue_btn.pack(side='left', padx=2)
        self._rescue_btn.config(state='disabled')

        # Adat nélkül / nincs kapcsolat → tiltott gombok
        for btn in (self._saveb_btn, self._savet_btn, self._upload_btn,
                    self._verify_btn, self._csum_btn, self._edit_btn, self._cleanup_btn):
            btn.config(state='disabled')

        # Treeview
        tree_f = ttk.Frame(tab)
        tree_f.pack(fill='both', expand=True)
        cols = ('offset', 'name', 'typ', 'value', 'mod')
        self._tree = ttk.Treeview(tree_f, columns=cols, show='headings',
                                   selectmode='browse', height=20)
        self._tree.heading('offset', text=t('col_offset'))
        self._tree.heading('name',   text=t('col_name'))
        self._tree.heading('typ',    text=t('col_type'))
        self._tree.heading('value',  text=t('col_value'))
        self._tree.heading('mod',    text=t('col_mod'))
        self._tree.column('offset', width=70,  stretch=False)
        self._tree.column('name',   width=260, stretch=True)
        self._tree.column('typ',    width=50,  stretch=False)
        self._tree.column('value',  width=220, stretch=True)
        self._tree.column('mod',    width=28,  stretch=False, anchor='center')
        vsb = ttk.Scrollbar(tree_f, orient='vertical',   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_f, orient='horizontal', command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_f.rowconfigure(0, weight=1); tree_f.columnconfigure(0, weight=1)

        self._tree.tag_configure('changed',  background='#FFE0A0')
        self._tree.tag_configure('checksum', background='#D0E8FF')
        self._tree.tag_configure('outside',  background='#E8D0FF')
        self._tree.bind('<Double-1>', self._on_tree_dblclick)

        # Checksum status bar
        cs_f = ttk.Frame(tab)
        cs_f.pack(fill='x', pady=(4, 0))
        ttk.Label(cs_f, text=t('csum_label')).pack(side='left', padx=4)
        self._csum_labels = {}
        for name in ('Cal_Sum0', 'Cal_Sum1', 'Cal_Sum2', 'Cal_Sum3'):
            lbl = ttk.Label(cs_f, text=f'{name}: —', width=22, relief='sunken',
                            anchor='center')
            lbl.pack(side='left', padx=3)
            self._csum_labels[name] = lbl

    def _build_settings_tab(self, nb):
        tab = ttk.Frame(nb, padding=4)
        nb.add(tab, text=t('tab_settings'))
        self._settings_tab = tab

        tb = ttk.Frame(tab)
        tb.pack(fill='x', pady=(0, 4))
        self._sdump32_btn = ttk.Button(tb, text=t('btn_dump_32k'), command=lambda: self._do_dump_settings(16384))
        self._sdump64_btn = ttk.Button(tb, text=t('btn_dump_64k'), command=lambda: self._do_dump_settings(32768))
        self._ssave_btn   = ttk.Button(tb, text=t('btn_save_set'), command=self._save_settings_bin)
        self._sdump32_btn.pack(side='left', padx=2)
        self._sdump64_btn.pack(side='left', padx=2)
        self._ssave_btn.pack(side='left', padx=2)
        self._ssave_btn.config(state='disabled')

        self._settings_txt = scrolledtext.ScrolledText(tab, width=90, height=25,
                                                        font=('Courier New', 9))
        self._settings_txt.pack(fill='both', expand=True)

    def _build_report_tab(self, nb):
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text=t('tab_report'))

        cs_f = ttk.LabelFrame(tab, text=t('lbl_calstr'), padding=6)
        cs_f.pack(fill='x', pady=(0, 8))
        self._calstr_var = tk.StringVar()
        ttk.Entry(cs_f, textvariable=self._calstr_var, width=82).pack(side='left', padx=4)
        self._wcstr_btn = ttk.Button(cs_f, text=t('btn_write_cstr'), command=self._write_calstr)
        self._wcstr_btn.pack(side='left', padx=4)

        btn_f = ttk.Frame(tab)
        btn_f.pack(fill='x', pady=(0, 4))
        ttk.Button(btn_f, text=t('btn_report_gen'),  command=self._gen_report).pack(side='left', padx=2)
        ttk.Button(btn_f, text=t('btn_report_save'), command=self._save_report).pack(side='left', padx=2)

        self._report_txt = scrolledtext.ScrolledText(tab, width=90, height=28,
                                                      font=('Courier New', 9))
        self._report_txt.pack(fill='both', expand=True)

    def _build_log_frame(self):
        lf = ttk.LabelFrame(self, text=t('tab_log'), padding=2)
        lf.pack(fill='x', padx=6, pady=(0, 4))
        ttk.Button(lf, text=t('btn_log_clear'),
                   command=lambda: self._log_txt.delete('1.0', tk.END)).pack(side='right')
        self._log_txt = scrolledtext.ScrolledText(lf, height=6, font=('Courier New', 9))
        self._log_txt.pack(fill='x')
        # Tkinter callback hibák elkapása → Log + fájl
        self.report_callback_exception = self._on_tk_exception

    def _on_tk_exception(self, exc, val, tb):
        import traceback
        text = ''.join(traceback.format_exception(exc, val, tb))
        self._log('HIBA: ' + text.strip())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}\n'
        self._log_txt.insert(tk.END, line)
        self._log_txt.see(tk.END)
        try:
            with LOG_FILE.open('a', encoding='utf-8') as f:
                f.write(line)
        except Exception:
            pass

    def _set_connected(self, ok: bool):
        state_inst = 'normal' if ok else 'disabled'
        state_conn = 'disabled' if ok else 'normal'
        self._btn_conn.config(state=state_conn)
        self._btn_disc.config(state=state_inst)
        self._btn_testid.config(state=state_inst)
        self._btn_clrbuf.config(state=state_inst)
        for btn in (self._dump_btn, self._wcstr_btn,
                    self._sdump32_btn, self._sdump64_btn):
            btn.config(state=state_inst)
        # upload/verify/cleanup csak ha adat is van betöltve
        if ok and self._codec is not None:
            self._upload_btn.config(state='normal')
            self._verify_btn.config(state='normal')
            self._cleanup_btn.config(state='normal')
            self._words_btn.config(state='normal')
            self._chunked_btn.config(state='normal')
        elif not ok:
            self._cleanup_btn.config(state='disabled')
            self._words_btn.config(state='disabled')
            self._chunked_btn.config(state='disabled')
        self._nmi_test_btn.config(state=state_inst)
        self._rescue_btn.config(state=state_inst)
        self._status_lbl.config(
            text=t('status_ok') if ok else t('status_none'),
            foreground='green' if ok else 'gray',
        )

    def _run_bg(self, fn, *args, done=None, err=None):
        """Háttérszálban futtat fn(*args), kész→done(result), hiba→err(str)."""
        def wrapper():
            try:
                result = fn(*args)
                if done: self.after(0, lambda: done(result))
            except Exception as exc:
                if err: self.after(0, lambda: err(str(exc)))
                else:   self.after(0, lambda: self._log(f'Hiba: {exc}'))
        threading.Thread(target=wrapper, daemon=True).start()

    def _save_prefs_now(self):
        self._prefs.update({
            'lang': _lang,
            'conn_type': self._conn_type.get(),
            'host': self._host_var.get(),
            'port': self._port_var.get(),
            'gpib': self._gpib_var.get(),
            'board': self._board_var.get(),
        })
        _save_prefs(self._prefs)

    # ── Kapcsolat ─────────────────────────────────────────────────────────────

    def _connect(self):
        errors = []
        is_tcp = (self._conn_type.get() == 'tcp')

        host = self._host_var.get().strip()
        if is_tcp and not host:
            errors.append('Host / IP nem lehet üres.')

        try:
            port = int(self._port_var.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            if is_tcp:
                errors.append('Port: 1–65535 közötti egész szám.')

        try:
            gpib = int(self._gpib_var.get().strip())
            if not (0 <= gpib <= 30):
                raise ValueError
        except ValueError:
            errors.append('GPIB cím: 0–30 közötti egész szám.')
            gpib = None

        if not is_tcp:
            try:
                board = int(self._board_var.get().strip())
                if board < 0:
                    raise ValueError
            except ValueError:
                errors.append('GPIB Board: 0 vagy nagyobb egész szám.')

        if errors:
            messagebox.showerror('Érvénytelen beállítás', '\n'.join(errors))
            return

        self._save_prefs_now()
        try:
            if is_tcp:
                self._conn = TCPConn(host, port, gpib)
            else:
                self._conn = NIConn(int(self._board_var.get()), gpib)
            self._instr = HP3458A(self._conn)
            self._log('Kapcsolódás... init folyamatban')
            self._instr.init()
            self._set_connected(True)
            self._log(f'Kapcsolódva ({self._conn_type.get().upper()}) · GPIB {gpib}')
            try:
                iid = self._instr.test_id()
                self._log(f'Műszer ID: {iid}')
            except Exception:
                pass
        except Exception as exc:
            self._conn = None; self._instr = None
            self._status_lbl.config(text=t('status_err'), foreground='red')
            self._log(f'Kapcsolódási hiba: {exc}')
            messagebox.showerror('Hiba', str(exc))

    def _disconnect(self):
        if self._conn:
            self._conn.close()
            self._conn = None; self._instr = None
        self._set_connected(False)
        self._log('Lecsatlakozva')

    def _test_id(self):
        try:
            resp = self._instr.test_id()
            self._log(f'ID?: {resp}')
            messagebox.showinfo('ID?', resp)
        except Exception as exc:
            self._log(f'ID? hiba: {exc}')

    def _do_gpib_clear(self):
        """GPIB SDC (Selected Device Clear) küldése — buffer törlés."""
        if not self._instr:
            return
        try:
            self._instr.gpib_clear()
            self._log('GPIB Clear (SDC) elküldve — műszer buffer törölve')
            time.sleep(0.5)
            resp = self._instr.test_id()
            self._log(f'ID? (clear után): {resp}')
        except Exception as exc:
            self._log(f'GPIB Clear hiba: {exc}')

    # ── Cal_RAM tábla ─────────────────────────────────────────────────────────

    def _refresh_tree(self):
        if not self._codec: return
        for item in self._tree.get_children():
            self._tree.delete(item)
        checksum_names = {'Cal_Sum0', 'Cal_Sum1', 'Cal_Sum2', 'Cal_Sum3'}
        outside_names  = {'Destructive Overloads', 'Defeats'}
        for f in self._codec.get_all_fields():
            if f['name'] in checksum_names:
                tag = 'checksum'
            elif f['name'] in outside_names:
                tag = 'outside'
            elif f['changed']:
                tag = 'changed'
            else:
                tag = ''
            val_display = f['value_str'][:60]
            self._tree.insert('', 'end',
                               iid=f'f_{f["offset"]}',
                               values=(f'0x{f["offset"]:04X}', f['name'], f['typ'],
                                       val_display, '✎' if f['changed'] else ''),
                               tags=(tag,))
        self._refresh_checksum_bar()

    def _refresh_checksum_bar(self):
        if not self._codec: return
        for name, off, stored, computed, ok in self._codec.verify_checksums():
            lbl = self._csum_labels.get(name)
            if lbl:
                status = '✓ OK' if ok else '✗ HIBA'
                lbl.config(text=f'{name}: {status}',
                            foreground='green' if ok else 'red')

    def _on_tree_dblclick(self, event):
        sel = self._tree.selection()
        if not sel or not self._codec: return
        iid = sel[0]
        off = int(iid.split('_')[1])
        fields = self._codec.get_all_fields()
        field  = next((f for f in fields if f['offset'] == off), None)
        if field:
            EditDialog(self, field, self._codec, self._on_field_saved)

    def _on_field_saved(self, name: str):
        self._log(f'Mező módosítva: {name}')
        self._refresh_tree()
        # CALSTR tab frissítése
        calstr = self._codec.get_field_value('Calstr')
        if calstr: self._calstr_var.set(str(calstr))

    # ── Cal_RAM DUMP ──────────────────────────────────────────────────────────

    def _do_dump_calram(self):
        passes  = self._passes_var.get()
        dlg     = ProgressDialog(self, t('prog_dump'), CAL_RAM_SIZE)
        stop    = threading.Event()
        results = []

        def do_passes():
            for p in range(passes):
                if stop.is_set():
                    break
                self.after(0, lambda p=p: self._log(f'Dump menet {p+1}/{passes}...'))

                def pcb(cur, total, msg, p=p):
                    # Cancellation propagation: ha a gomb meg lett nyomva, stop beállít
                    if dlg.is_cancelled():
                        stop.set()
                    self.after(0, lambda: dlg.update_progress(
                        cur, total, f'Pass {p+1}/{passes}: {msg}'))

                data = self._instr.dump_calram(progress_cb=pcb, stop_event=stop)
                if data is None or stop.is_set():
                    break
                md5 = hashlib.md5(data).hexdigest()
                results.append((data, md5))
                self.after(0, lambda m=md5, pp=p+1: self._log(f'Pass {pp} MD5: {m}'))

            if results and not stop.is_set():
                self.after(0, lambda: self._on_dump_done(results, dlg))
            else:
                self.after(0, dlg.close)
                self.after(0, lambda: self._log('Dump megszakítva'))

        threading.Thread(target=do_passes, daemon=True).start()

    def _on_dump_done(self, results: list, dlg: ProgressDialog):
        dlg.close()
        if not results:
            self._log('Dump megszakítva')
            return
        md5s = [md5 for _, md5 in results]
        all_match = len(set(md5s)) == 1
        if not all_match:
            self._log(f'FIGYELEM: Dump menetek NEM egyeznek! MD5-ök: {md5s}')
            messagebox.showwarning('Dump eltérés',
                                   'A dump menetek eltérnek! Az utolsó menet adatai kerülnek betöltésre.')
        else:
            self._log(f'Dump OK: {len(results)} menet egyezik · MD5: {md5s[0]}')

        data = results[-1][0]
        self._codec = CalRAMCodec(data)
        ts    = datetime.now().strftime('%Y%m%d_%H%M%S')
        bpath = DUMPS_DIR / f'calram_{ts}.bin'
        self._codec.to_file(bpath)
        self._log(f'Mentve: {bpath}')
        cs_summary = '  '.join(f'{n}: {"OK" if ok else "HIBA"}' for n, _, _, _, ok in self._codec.verify_checksums())
        self._log(f'Checksum: {cs_summary}')
        self._refresh_tree()
        calstr = self._codec.get_field_value('Calstr')
        if calstr: self._calstr_var.set(str(calstr))
        for btn in (self._saveb_btn, self._savet_btn, self._csum_btn, self._edit_btn,
                    self._upload_btn, self._verify_btn):
            btn.config(state='normal')
        if self._instr:
            self._words_btn.config(state='normal')
            self._chunked_btn.config(state='normal')

    # ── Cal_RAM Betöltés / Mentés ─────────────────────────────────────────────

    def _load_bin(self):
        path = filedialog.askopenfilename(
            initialdir=str(DUMPS_DIR), title='Cal_RAM .bin betöltése',
            filetypes=[('Binary', '*.bin'), ('All', '*.*')])
        if not path: return
        try:
            self._codec = CalRAMCodec.from_file(path)
            cs_summary = '  '.join(f'{n}: {"OK" if ok else "HIBA"}' for n, _, _, _, ok in self._codec.verify_checksums())
            self._log(f'Betöltve: {path}  MD5: {self._codec.md5()}')
            self._log(f'Checksum: {cs_summary}')
            self._refresh_tree()
            calstr = self._codec.get_field_value('Calstr')
            if calstr: self._calstr_var.set(str(calstr))
            for btn in (self._saveb_btn, self._savet_btn, self._csum_btn, self._edit_btn,
                        self._upload_btn, self._verify_btn):
                btn.config(state='normal')
            if self._instr:
                self._words_btn.config(state='normal')
                self._chunked_btn.config(state='normal')
        except Exception as exc:
            messagebox.showerror('Hiba', str(exc))

    def _save_bin(self):
        if not self._codec: return
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            initialdir=str(DUMPS_DIR), initialfile=f'calram_{ts}.bin',
            defaultextension='.bin', filetypes=[('Binary', '*.bin')])
        if not path: return
        self._codec.to_file(path)
        self._log(f'Mentve: {path}')

    def _save_txt(self):
        if not self._codec: return
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            initialdir=str(DUMPS_DIR), initialfile=f'calram_{ts}_decoded.txt',
            defaultextension='.txt', filetypes=[('Text', '*.txt')])
        if not path: return
        Path(path).write_text(self._codec.generate_report(_lang), encoding='utf-8')
        self._log(f'Decoded TXT mentve: {path}')

    # ── Cal_RAM Checksum ──────────────────────────────────────────────────────

    def _do_checksum(self):
        if not self._codec: return
        self._codec.recalculate_checksums()
        self._log('Checksum-ok újraszámolva')
        self._refresh_tree()

    # ── Cal_RAM Edit (toolbar gomb) ───────────────────────────────────────────

    def _do_edit(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo('Szerkesztés',
                                'Először jelölj ki egy sort a listában!')
            return
        self._on_tree_dblclick(None)

    # ── Cal_RAM UPLOAD ────────────────────────────────────────────────────────

    def _do_upload(self):
        if not self._codec:
            return
        if not self._instr:
            messagebox.showwarning('Nincs kapcsolat', 'Csatlakozz a műszerre a feltöltéshez!')
            return
        diffs = self._codec.diff_fields()
        if diffs:
            dlg = DiffDialog(self, diffs, None)
            self.wait_window(dlg)
            if not dlg._proceed: return

        if not self._codec.checksums_ok():
            ans = messagebox.askyesno(
                'Checksum hiba',
                'A checksum-ok nem helyesek!\nElőbb újraszámolod?\n\nIgen = újraszámol és folytat\nNem = folytat mindenképp')
            if ans:
                self._codec.recalculate_checksums()
                self._refresh_tree()

        dlg  = ProgressDialog(self, t('prog_upload'), 1044)
        stop = threading.Event()

        def do_upload():
            last_msg = ['']
            def pcb(cur, total, msg):
                last_msg[0] = msg
                self.after(0, lambda c=cur, t=total, m=msg: dlg.update_progress(c, t, m))
            data = self._codec.to_bytes()
            try:
                ok = self._instr.write_calram_bin_fast(data, progress_cb=pcb, stop_event=stop)
            except Exception as exc:
                import traceback
                self.after(0, lambda e=str(exc), tb=traceback.format_exc():
                           self._on_upload_done(False, data, dlg, e + '\n' + tb))
                return
            self.after(0, lambda: self._on_upload_done(ok, data, dlg, last_msg[0]))

        self._log(f'Feltöltés indítva: gyors blokkos mód · {len(self._codec.find_changed_words())} módosított szó')
        self._writing = True
        threading.Thread(target=do_upload, daemon=True).start()

    def _on_upload_done(self, ok: bool, data: bytes, dlg: ProgressDialog, detail: str = ''):
        self._writing = False
        dlg.close()
        if ok:
            self._log('Feltöltés sikeres. Verify indul 3s múlva...')
            self._codec.reset_original()
            self._refresh_tree()
            self._start_verify(data, auto_cleanup=True, pre_delay=3.0)
        else:
            self._log('Feltöltés HIBA! ' + detail)
            messagebox.showerror('Feltöltés', f'Feltöltési hiba!\n\n{detail}')

    # ── NMI Teszt ────────────────────────────────────────────────────────────

    def _do_nmi_test(self):
        """Visszaírja az első cal_ram word-öt (adatot nem változtat), NMI tesztelése."""
        if not self._instr:
            return
        dlg  = ProgressDialog(self, 'NMI Mechanizmus Teszt', 3)
        stop = threading.Event()

        def do_test():
            def pcb(cur, total, msg):
                self.after(0, lambda c=cur, t=total, m=msg: dlg.update_progress(c, t, m))
            try:
                ok, detail = self._instr.test_nmi_write(progress_cb=pcb)
            except Exception as exc:
                import traceback
                detail = str(exc) + '\n' + traceback.format_exc()
                self.after(0, lambda d=detail: (
                    dlg.close(),
                    self._log('NMI Teszt HIBA: ' + d),
                    messagebox.showerror('NMI Teszt', d[:400])
                ))
                return
            self.after(0, lambda o=ok, d=detail: (
                dlg.close(),
                self._log(f'NMI Teszt: {"OK ✓" if o else "HIBA ✗"} — {d}'),
                messagebox.showinfo('NMI Teszt', f'{"OK ✓" if o else "HIBA ✗"}\n\n{d}')
            ))

        threading.Thread(target=do_test, daemon=True).start()

    # ── Rescue DEFKEY telepítése ──────────────────────────────────────────────

    def _do_install_rescue_defkey(self):
        """DEFKEY F1 = 'PRESET NORM' eltárolása a műszer NVRAM-ban.
        GPIB lockup esetén helyreállítás: LOCAL gomb → F1 a frontpanelen."""
        if not self._instr:
            return
        if not messagebox.askyesno(
                'Rescue DEFKEY telepítése',
                'A DEFKEY F1 billentyűhöz az "END ALWAYS;PRESET NORM" parancsot rendeli.\n\n'
                'Ez a settings_RAM NVRAM-ban tárolódik és power cycle után is megmarad.\n\n'
                'Helyreállítás GPIB lockup esetén:\n'
                '  1. Nyomd meg a LOCAL gombot a frontpanelen\n'
                '  2. Nyomd meg az F1 funkciógombot → END ALWAYS + PRESET NORM lefut\n'
                '  3. Csatlakozz újra GPIB-en\n\n'
                'Telepíted?'):
            return
        try:
            self._instr.send('DEFKEY F1,"END ALWAYS;PRESET NORM"')
            import time as _time
            _time.sleep(0.4)
            resp = self._instr.errstr()
            if 'NO ERROR' in resp:
                self._log('Rescue DEFKEY: F1 = "END ALWAYS;PRESET NORM" sikeresen telepítve ✓')
                messagebox.showinfo('Rescue DEFKEY',
                                    'DEFKEY F1 = "END ALWAYS;PRESET NORM" sikeresen telepítve!\n\n'
                                    'GPIB lockup esetén: LOCAL → F1')
            else:
                self._log(f'Rescue DEFKEY hiba: {resp}')
                messagebox.showerror('Rescue DEFKEY', f'Hiba: {resp}')
        except Exception as exc:
            self._log(f'Rescue DEFKEY kivétel: {exc}')
            messagebox.showerror('Rescue DEFKEY', str(exc))

    # ── Módosított szavak egyenkénti írása ───────────────────────────────────

    def _do_upload_changed(self):
        """Csak a módosított wordöket írja cal_ram-ba, egyenként NMI-vel."""
        if not self._codec or not self._instr:
            return
        changed = self._codec.find_changed_words()
        if not changed:
            messagebox.showinfo('Módosított szavak',
                                'Nincs módosított word a betöltött adathoz képest.\n'
                                'Betölts egy friss dump-ot, majd módosítsd a mezőket.')
            return
        if not self._codec.checksums_ok():
            ans = messagebox.askyesno(
                'Checksum hiba',
                'A checksum-ok nem helyesek!\nElőbb újraszámolod?\n\n'
                'Igen = újraszámol és folytat\nNem = folytat mindenképp (hibás checksum-mal!)')
            if ans:
                self._codec.recalculate_checksums()
                self._refresh_tree()
        word_list = [(phys, word) for _, phys, word in changed]
        if not messagebox.askyesno('Módosított szavak',
                                   f'{len(word_list)} módosított word írása egyenként NMI-vel.\n'
                                   f'Becsült idő: ~{len(word_list) * 3}s\n\nFolytatod?'):
            return

        dlg  = ProgressDialog(self, 'Módosított szavak írása', len(word_list))
        stop = threading.Event()
        data = self._codec.to_bytes()

        def do_words():
            last_msg = ['']
            def pcb(cur, total, msg):
                last_msg[0] = msg
                if dlg.is_cancelled():
                    stop.set()
                self.after(0, lambda c=cur, t=total, m=msg: dlg.update_progress(c, t, m))
            try:
                ok = self._instr.write_calram_words_list(word_list, progress_cb=pcb,
                                                         stop_event=stop)
            except Exception as exc:
                import traceback
                detail = str(exc) + '\n' + traceback.format_exc()
                self.after(0, lambda d=detail: (
                    dlg.close(),
                    self._log('Módosított írás HIBA: ' + d),
                    messagebox.showerror('Szóírás', d[:400])
                ))
                return
            self.after(0, lambda: self._on_upload_done(ok, data, dlg, last_msg[0]))

        self._log(f'Feltöltés indítva: módosított szavak mód · {len(word_list)} szó')
        self._writing = True
        threading.Thread(target=do_words, daemon=True).start()

    # ── JSR Újrapróbálás (meglevő DATA_BASE tartalommal) ─────────────────────

    # ── Szavankénti feltöltés, egyenkénti NMI (BIZTOS, de ~1 óra) ─────────────

    def _do_upload_chunked(self):
        """Teljes cal_ram feltöltés egyenként, 1 szó/NMI (write_calram_words_list).

        A korábbi "csoportos"/"10k unrolled" megközelítés (write_calram_bin_chunked,
        a régi _write_loop_callback streaming mintával) ki van véve — az
        dokumentáltan instabil (RAM-olvasás a /WE ablak alatt, lásd
        feedback-bulk-callback-unsafe memória). Helyette ugyanaz a biztos,
        szóról szóra haladó mechanizmus fut, mint a "Módosított szavak"
        gombnál, csak a TELJES 1024 szóra, nem csak a változottakra.

        ~2-3s/szó × 1024 szó ≈ 35-50 perc — biztonsági ráhagyással ~1 óra.
        """
        if not self._codec or not self._instr:
            return
        if not self._codec.checksums_ok():
            ans = messagebox.askyesno(
                'Checksum hiba',
                'A checksum-ok nem helyesek!\nElőbb újraszámolod?\n\n'
                'Igen = újraszámol és folytat\nNem = folytat mindenképp')
            if ans:
                self._codec.recalculate_checksums()
                self._refresh_tree()

        if not messagebox.askyesno(
                'Szavankénti feltöltés',
                'Az ÖSSZES 1024 Cal_RAM szót egyenként, 1 szó/NMI-vel írja fel\n'
                '(ugyanaz a biztos mechanizmus, mint a "Módosított szavak" gombnál).\n\n'
                'Becsült idő: kb. 1 óra.\n\n'
                'Folytatod?'):
            return

        dlg  = ProgressDialog(self, 'Szavankénti feltöltés (~1 óra)', 1024)
        stop = threading.Event()
        data = self._codec.to_bytes()

        def do_full_slow():
            last_msg = ['']
            def pcb(cur, total, msg):
                last_msg[0] = msg
                if dlg.winfo_exists() and dlg.is_cancelled():
                    stop.set()
                if dlg.winfo_exists():
                    self.after(0, lambda c=cur, t=total, m=msg:
                               dlg.update_progress(c, t, m) if dlg.winfo_exists() else None)
            try:
                # write_calram_bin_safe: ugyanaz a mechanizmus, mint
                # write_calram_words_list, de a checksum szavakat a
                # végére hagyja — nincs köztes checksum-mismatch ablak.
                ok = self._instr.write_calram_bin_safe(
                    data, progress_cb=pcb, stop_event=stop)
            except Exception as exc:
                import traceback
                detail = str(exc) + '\n' + traceback.format_exc()
                self.after(0, lambda d=detail: (
                    dlg.close(),
                    self._log('Teljes lassú felt. HIBA: ' + d),
                    messagebox.showerror('Teljes lassú felt.', d[:400])
                ))
                return
            self.after(0, lambda: self._on_upload_done(ok, data, dlg, last_msg[0]))

        self._log('Feltöltés indítva: szavankénti biztonságos mód · 1024 szó')
        self._writing = True
        threading.Thread(target=do_full_slow, daemon=True).start()

    # ── Cal_RAM VERIFY ────────────────────────────────────────────────────────

    def _do_verify(self):
        if not self._codec:
            return
        if not self._instr:
            messagebox.showwarning('Nincs kapcsolat', 'Csatlakozz a műszerre a verify-hoz!')
            return
        self._start_verify(self._codec.to_bytes(), auto_cleanup=False)

    def _start_verify(self, expected: bytes, auto_cleanup: bool = False,
                      pre_delay: float = 0.0):
        dlg  = ProgressDialog(self, t('prog_verify'), CAL_RAM_SIZE)
        stop = threading.Event()

        def do_verify():
            if pre_delay > 0:
                time.sleep(pre_delay)
            def pcb(cur, total, msg):
                if dlg.is_cancelled(): stop.set()
                self.after(0, lambda c=cur, t=total, m=msg: dlg.update_progress(c, t, m))
            try:
                ok, diffs = self._instr.verify_calram(expected, progress_cb=pcb,
                                                      stop_event=stop)
            except Exception as exc:
                import traceback
                detail = str(exc) + '\n' + traceback.format_exc()
                self.after(0, lambda d=detail: (
                    dlg.close(),
                    self._log('Verify HIBA: ' + d),
                    messagebox.showerror('Verify', 'Verify kivétel:\n\n' + d[:400])
                ))
                return
            self.after(0, lambda: self._on_verify_done(ok, diffs, dlg, auto_cleanup))

        threading.Thread(target=do_verify, daemon=True).start()

    def _on_verify_done(self, ok: bool, diffs: list, dlg: ProgressDialog,
                        auto_cleanup: bool = False):
        dlg.close()
        if ok:
            self._log('Verify: OK ✓ — minden byte egyezik')
            if auto_cleanup and self._autoclean_var.get():
                self._log('Auto-cleanup: settings_RAM törlés indul...')
                self._do_cleanup()
            else:
                messagebox.showinfo('Verify', 'Verify OK ✓\nMinden byte egyezik a műszerben.')
        else:
            self._log(f'Verify: HIBÁS — {len(diffs)} byte eltér!')
            detail = '\n'.join(f'  offset 0x{off:04X}: várt 0x{exp:02X}, kapott 0x{got:02X}'
                               for off, exp, got in diffs[:20])
            if len(diffs) > 20: detail += f'\n  ... és még {len(diffs)-20} eltérés'
            messagebox.showerror('Verify HIBA', f'{len(diffs)} byte eltér!\n\n{detail}')

    # ── Settings_RAM cleanup ──────────────────────────────────────────────────

    def _do_cleanup(self):
        """Nullázza a settings_ram injektált területeit (CODE/CB/DATA/magic)."""
        if not self._instr:
            messagebox.showwarning('Nincs kapcsolat', 'Csatlakozz a műszerre!')
            return
        # 1024 word DATA + 64 word CODE + 7 word CB + 12 misc = ~1107 word
        dlg  = ProgressDialog(self, t('prog_cleanup'), 1107)
        stop = threading.Event()

        def do_clean():
            def pcb(cur, total, msg):
                if dlg.is_cancelled(): stop.set()
                self.after(0, lambda: dlg.update_progress(cur, total, msg))
            n = self._instr.cleanup_injected(
                include_data=True, progress_cb=pcb, stop_event=stop)
            self.after(0, lambda: self._on_cleanup_done(n, dlg))

        threading.Thread(target=do_clean, daemon=True).start()

    def _on_cleanup_done(self, n: int, dlg: ProgressDialog):
        dlg.close()
        msg = t('cleanup_ok').format(n)
        self._log(msg)
        messagebox.showinfo('Cleanup', msg)

    # ── Settings RAM ──────────────────────────────────────────────────────────

    def _do_dump_settings(self, word_count: int):
        dlg  = ProgressDialog(self, t('prog_settings'), word_count)
        stop = threading.Event()

        def do_dump():
            def pcb(cur, total, msg):
                self.after(0, lambda: dlg.update_progress(cur, total, msg))
            data = self._instr.dump_settings(word_count, progress_cb=pcb, stop_event=stop)
            self.after(0, lambda: self._on_settings_done(data, dlg))

        threading.Thread(target=do_dump, daemon=True).start()

    def _on_settings_done(self, data, dlg: ProgressDialog):
        dlg.close()
        if data is None:
            self._log('Settings dump megszakítva')
            return
        self._set_data = data
        ts    = datetime.now().strftime('%Y%m%d_%H%M%S')
        bpath = DUMPS_DIR / f'settings_{ts}.bin'
        bpath.write_bytes(data)
        self._log(f'Settings dump: {len(data)} byte → {bpath}')
        self._ssave_btn.config(state='normal')
        # Alap dekódolt nézet megjelenítése
        self._show_settings_decode(data)

    def _show_settings_decode(self, data: bytes):
        self._settings_txt.delete('1.0', tk.END)
        base = 0x120000

        def rd16(off):
            if off + 1 < len(data): return (data[off] << 8) | data[off + 1]
            return 0

        def rd_ascii(off, n):
            chunk = data[off:off + n]
            return chunk.decode('ascii', errors='replace').rstrip('\x00 ')

        lines = [f'Settings RAM dekódolás  (alap: 0x{base:06X}, méret: {len(data)} byte)',
                 '=' * 70, '']

        # Header / crash log
        lines.append(f'[0x12000C] Crash log: {rd_ascii(0x000C, 32)}')
        lines.append(f'[0x120DAE] Utolsó mérés: {rd_ascii(0x0DAE, 24)}')
        lines.append(f'[0x120E38] RMEM 1: {rd_ascii(0x0E38, 24)}')

        # Magic words
        lines.append('\nMagic word-ök (NMI biztonsági ellenőrzés):')
        for addr, name in [(0x1780, 'magic1 DEAF'), (0x0C90, 'magic2 BAD1'),
                           (0x1782, 'magic3 0ACE'), (0x0C92, 'magic4 BEAD')]:
            if addr + 1 < len(data):
                lines.append(f'  [0x{base+addr:06X}] {name}: 0x{rd16(addr):04X}')

        # Callback, success flag, /WE close
        lines.append('\nNMI callback terület:')
        for addr, name in [(0x1852, 'callback ptr HI'), (0x1854, 'callback ptr LO'),
                           (0x1856, 'success flag'), (0x185A, '/WE close val')]:
            if addr + 1 < len(data):
                lines.append(f'  [0x{base+addr:06X}] {name}: 0x{rd16(addr):04X}')

        # DEFKEY F0-F9
        lines.append('\nDEFKEY F0-F9:')
        for i in range(10):
            off = 0x1B10 + i * 0x1A
            if off + 0x1A < len(data):
                s = rd_ascii(off, 0x1A)
                if s: lines.append(f'  F{i}: {s}')

        self._settings_txt.insert('1.0', '\n'.join(lines))

    def _save_settings_bin(self):
        if not self._set_data: return
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            initialdir=str(DUMPS_DIR), initialfile=f'settings_{ts}.bin',
            defaultextension='.bin', filetypes=[('Binary', '*.bin')])
        if path:
            Path(path).write_bytes(self._set_data)
            self._log(f'Settings .bin mentve: {path}')

    # ── Cal Report + CALSTR ───────────────────────────────────────────────────

    def _write_calstr(self):
        if not self._instr: return
        txt = self._calstr_var.get()[:80]
        if not txt: return
        resp = self._instr.write_calstr(txt)
        self._log(f'CALSTR írás → {resp}')
        if 'NO ERROR' in resp:
            messagebox.showinfo('CALSTR', 'CALSTR sikeresen írva a műszerre.')
        else:
            messagebox.showerror('CALSTR hiba', resp)

    def _gen_report(self):
        if not self._codec:
            messagebox.showwarning('Riport', 'Nincs betöltött Cal_RAM!')
            return
        report = self._codec.generate_report(_lang)
        self._report_txt.delete('1.0', tk.END)
        self._report_txt.insert('1.0', report)
        self._log('Kalibrációs riport generálva')

    def _save_report(self):
        content = self._report_txt.get('1.0', tk.END).strip()
        if not content: return
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            initialdir=str(DUMPS_DIR), initialfile=f'calreport_{ts}.txt',
            defaultextension='.txt', filetypes=[('Text', '*.txt')])
        if path:
            Path(path).write_text(content, encoding='utf-8')
            self._log(f'Riport mentve: {path}')

    # ── Nyelv váltás ──────────────────────────────────────────────────────────

    def _switch_lang(self, lang: str):
        global _lang
        if _lang == lang: return
        _lang = lang
        self._prefs['lang'] = lang
        _save_prefs(self._prefs)
        messagebox.showinfo(
            'Language / Nyelv',
            'A nyelv módosításhoz indítsd újra a programot.\n'
            'Please restart the application to apply the language change.'
        )

    # ── Névjegy ───────────────────────────────────────────────────────────────

    def _show_about(self):
        messagebox.showinfo(t('menu_about'), t('about_text'))


# ── Belépési pont ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = App()
    app.mainloop()
