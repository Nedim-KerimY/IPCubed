"""KiCad senkronunu AYRI SURECTE calistirir.

Neden: KiCad IPC cevaplarinin cozumlenmesi (protobuf -> Python nesneleri, pad/iz/zone donusumleri) saf Python isidir ve GIL'i
tutar. Ayni surecteki bir thread'de calisinca render thread'i takilir (olculdu: 2 sn'lik cekim sirasinda kare suresi 8 ms'den
~780 ms'ye cikiyor). Ayri surecte calisinca render hic beklemez; sonuclar kucuk/pickle edilebilir mesajlar olarak gelir.

`SyncProcess`, `app.SyncThread` ile ayni arayuzu sunar: .out (kuyruk), .visible, .request_full.set(), .check_now.set(),
.is_alive(), .stop().
"""
from __future__ import annotations

import multiprocessing as mp
import threading


def _sync_main(cmd_q, out_q):
    from .sync import SyncThread
    try:                              # onceki oturumlardan kalan veri dosyalari
        from .paths import cache_dir
        for p in (cache_dir().parent / "snap").glob("*.pkl"):
            p.unlink()
    except OSError:
        pass
    t = SyncThread(out_q)
    t.ship_files = True
    t.visible = False                 # vekil (SyncProcess) gizli varsayar; gorunurluk komutla gelir
    t.start()
    while True:
        try:
            cmd = cmd_q.get()
        except (EOFError, OSError):
            break
        name = cmd[0]
        if name == "visible":
            t.visible = bool(cmd[1])
        elif name == "full":
            t.request_full.set()
        elif name == "check":
            t.check_now.set()
        elif name == "stop":
            t.stop()
            break


class _Flag:
    """Event benzeri: .set() karsi surece komut gonderir."""

    def __init__(self, send, name):
        self._send, self._name = send, name

    def set(self):
        self._send((self._name,))


class SyncProcess:
    def __init__(self):
        ctx = mp.get_context("spawn")
        self._cmd = ctx.Queue()
        self.out = ctx.Queue()
        self._p = ctx.Process(target=_sync_main, args=(self._cmd, self.out), daemon=True, name="ipcubed-sync")
        self._visible = False
        self.request_full = _Flag(self._send, "full")
        self.check_now = _Flag(self._send, "check")
        self._lock = threading.Lock()

    def _send(self, msg):
        try:
            self._cmd.put(msg)
        except Exception:  # noqa: BLE001
            pass

    def start(self):
        self._p.start()

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, v: bool):
        v = bool(v)
        if v != self._visible:
            self._visible = v
            self._send(("visible", v))

    def is_alive(self) -> bool:
        return self._p.is_alive()

    def stop(self):
        self._send(("stop",))
        self._p.join(1.5)
        if self._p.is_alive():
            self._p.terminate()
