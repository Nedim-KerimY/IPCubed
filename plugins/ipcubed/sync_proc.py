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


def _parent_alive(ppid: int) -> bool:
    import os
    if os.name != "nt" and os.getppid() != ppid:       # POSIX: ebeveyn olunce init/subreaper'a devredilir
        return False
    try:
        import psutil
        return psutil.pid_exists(ppid)
    except Exception:  # noqa: BLE001
        return True


def _sync_main(cmd_q, out_q, ppid=None):
    import os
    import queue
    from .sync import SyncThread
    try:                              # onceki oturumlardan kalan veri dosyalari (ayni anda calisan baska viewer'inkiler kalir)
        import psutil
        from .paths import cache_dir
        for p in (cache_dir().parent / "snap").glob("*.pkl"):
            try:
                owner = int(p.stem.split("_")[0])
            except ValueError:
                owner = -1
            if owner != os.getpid() and not psutil.pid_exists(owner):
                p.unlink()
    except (OSError, ImportError):
        pass
    t = SyncThread(out_q)
    t.ship_files = True
    t.visible = False                 # vekil (SyncProcess) gizli varsayar; gorunurluk komutla gelir
    t.start()
    out_q.cancel_join_thread()        # cikista okunmayan mesajlar yuzunden takilma
    while True:
        try:
            cmd = cmd_q.get(timeout=2.0)
        except queue.Empty:
            if ppid is not None and not _parent_alive(ppid):
                os._exit(0)           # ana surec coktu/olduruldu: yetim kalip KiCad'i yoklamaya devam etme
            continue
        except (EOFError, OSError):
            break
        name = cmd[0]
        if name == "visible":
            t.visible = bool(cmd[1])
        elif name == "full":
            t.request_full.set()
        elif name == "check":
            t.check_now.set()
        elif name == "park":
            t.park()
        elif name == "resume":
            t.resume()
        elif name in ("hl2d", "hlclear"):          # KiCad 2D vurgusu: ayri baglanti, sync thread'ini bekletmez
            from .kicad_actions import clear_highlight, highlight_nets
            fn, args = (highlight_nets, (cmd[1],)) if name == "hl2d" else (clear_highlight, ())
            threading.Thread(target=fn, args=args, daemon=True).start()
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
        import os
        self._p = ctx.Process(target=_sync_main, args=(self._cmd, self.out, os.getpid()), daemon=True, name="ipcubed-sync")
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

    def park(self):
        self._send(("park",))

    def resume(self):
        self._send(("resume",))

    def is_alive(self) -> bool:
        return self._p.is_alive()

    def stop(self):
        self._send(("stop",))
        self._p.join(1.5)
        if self._p.is_alive():
            self._p.terminate()
