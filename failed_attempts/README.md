# Failed attempts

Cal_ram-írási megközelítések, amiket kipróbáltunk a fejlesztés során, de
amik **nem váltak be** — instabilak voltak, vagy egy később talált jobb
megoldás (`program/hp3458a_instr.py` jelenlegi `write_calram_word` /
`write_calram_words_list` / `write_calram_bin_safe` / `write_calram_bin_fast`
függvényei) feleslegessé tette őket.

| Fájl | Mit tartalmaz |
|---|---|
| `archive_unused_calram_methods.py` | `write_calram_bin()` (kísérleti, instabil egy-JSR-es bulk írás), `write_calram_bin_chunked()` (a régi streaming-callback alapú "csoportos feltöltés"), `retry_calram_bulk_jsr()`, és a közös, kockázatos `_write_loop_callback()` segédjük — kommentált Python kódblokkokként, mindegyiknél indoklással, hogy miért bukott el. |

**A közös gyökérok**, amiért ezek mind kockázatosak voltak: a Level7 NMI
handler által hívott callback-en BELÜL futtattak egy ciklust, ami
`MOVE.W (A1)+,D2`-vel a /WE (write-enable) ablak alatt olvasott
settings_RAM-ból. Ez buszkonfliktust / CPU crash-t okozhat. A működő
megoldások (lásd `program/`) soha nem olvasnak forrás-RAM-ot a /WE alatt —
az adat mindig előre be van töltve egy regiszterbe, mielőtt az NMI elsül.
