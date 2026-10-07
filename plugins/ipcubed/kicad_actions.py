"""KiCad 2D editorunde net vurgulama (sync surecinde, kendi IPC baglantisiyla calisir).

KiCad API'sinde dogrudan "neti vurgula" komutu yok: her netten bir oge secilir ve KiCad'in kendi
"Highlight Net" aksiyonu (secimdeki netler) calistirilir. `run_action` kipy'de kararsiz (unstable) olarak isaretli.
"""
from __future__ import annotations

from .log import _log

ACT_HIGHLIGHT = "pcbnew.EditorControl.highlightNetSelection"
ACT_CLEAR = "pcbnew.EditorControl.clearHighlight"


def _connect():
    from kipy import KiCad
    k = KiCad(timeout_ms=4000)
    return k, k.get_board()


def highlight_nets(names: list):
    try:
        k, b = _connect()
        want = set(names)
        pick: dict = {}
        for getter in (b.get_pads, b.get_tracks, b.get_vias):
            for it in getter():
                try:
                    n = it.net.name
                except Exception:  # noqa: BLE001
                    continue
                if n in want and n not in pick:
                    pick[n] = it
            if len(pick) == len(want):
                break
        if not pick:
            _log(f"2D vurgu: ogeler bulunamadi {names}")
            return
        b.clear_selection()
        b.add_to_selection(list(pick.values()))
        r = k.run_action(ACT_HIGHLIGHT)
        b.clear_selection()
        _log(f"2D vurgu {sorted(pick)} -> {r}")
    except Exception as e:  # noqa: BLE001
        _log(f"2D vurgu hatasi: {e!r}")


def clear_highlight():
    try:
        k, _ = _connect()
        r = k.run_action(ACT_CLEAR)
        _log(f"2D vurgu temizlendi -> {r}")
    except Exception as e:  # noqa: BLE001
        _log(f"2D vurgu temizleme hatasi: {e!r}")
