"""Sag altta kucuk performans yazisi: FPS, kare suresi, CPU, RAM, GPU. Secenege bagli (sag tik menusu), kapaliyken maliyeti sifir."""
from __future__ import annotations

import subprocess
import sys
import threading

import numpy as np
from PySide6 import QtCore, QtGui

from . import theme

W, H = 450, 22               # mantiksal px
MARGIN = 8


class StatsSampler(threading.Thread):
    """Saniyede bir: bu surec + isci surecleri (CPU toplam %, RAM MB), GPU (nvidia-smi varsa; arka planda, pencere acmaz)."""

    def __init__(self):
        super().__init__(daemon=True, name="ipcubed-stats")
        self._halt = threading.Event()
        self.cpu = 0.0
        self.ram_mb = 0.0
        self.gpu: float | None = None
        self.vram_mb: float | None = None
        self._gpu_fail = 0

    def stop(self):
        self._halt.set()

    def _read_gpu(self):
        if self._gpu_fail >= 3:
            return
        try:
            kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=3, **kw)
            util, mem = (float(x) for x in r.stdout.strip().splitlines()[0].split(","))
            self.gpu, self.vram_mb, self._gpu_fail = util, mem, 0
        except Exception:  # noqa: BLE001
            self._gpu_fail += 1
            self.gpu = self.vram_mb = None

    def run(self):
        try:
            import psutil
        except Exception:  # noqa: BLE001
            return
        me = psutil.Process()
        ncpu = psutil.cpu_count() or 1
        known: dict[int, "psutil.Process"] = {me.pid: me}
        me.cpu_percent(None)
        tick = 0
        while not self._halt.wait(1.0):
            try:
                alive = {me.pid: me}
                for ch in me.children(recursive=True):
                    alive[ch.pid] = known.get(ch.pid) or ch          # kalici nesne: cpu_percent ilk cagrida 0 doner
                known = alive
                cpu = ram = 0.0
                for p in list(known.values()):
                    try:
                        cpu += p.cpu_percent(None)
                        ram += p.memory_info().rss
                    except Exception:  # noqa: BLE001
                        pass
                self.cpu, self.ram_mb = cpu / ncpu, ram / 2**20
            except Exception:  # noqa: BLE001
                pass
            if tick % 2 == 0:
                self._read_gpu()
            tick += 1


class StatsOverlay:
    def __init__(self):
        self._font = theme.make_font(12, mono=True)

    @staticmethod
    def text(fps: float, ms: float, s: StatsSampler, loading: int = 0) -> str:
        gpu = f"{s.gpu:.0f}%" if s.gpu is not None else "n/a"
        vram = f" {s.vram_mb / 1024:.1f}G" if s.vram_mb is not None else ""
        # "idle" = cizilen kare yok; arka planda model/katman isleri surerken bunu gostermek yaniltici (bitmis sanilir)
        fps_t = f"load {min(loading, 99):2d}" if loading else (f"{fps:3.0f} FPS" if fps > 0 else "idle")
        return f"{fps_t} | {ms:4.1f} ms | CPU {s.cpu:4.1f}% | RAM {s.ram_mb:5.0f} MB | GPU {gpu}{vram}"

    def render(self, text: str, ratio: float = 1.0) -> np.ndarray:
        pw, ph = max(1, int(round(W * ratio))), max(1, int(round(H * ratio)))
        img = QtGui.QImage(pw, ph, QtGui.QImage.Format_RGBA8888_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        p.scale(pw / W, ph / H)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(24, 24, 24, 190))
        p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, W - 1, H - 1), 4, 4)
        p.setFont(self._font)
        p.setPen(QtGui.QColor("#e6e8ec"))
        p.drawText(QtCore.QRectF(8, 0, W - 16, H), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, text)
        p.end()
        arr = np.frombuffer(img.constBits(), np.uint8).reshape(ph, pw, 4).copy()
        a = arr[..., 3:4].astype(np.float32)
        arr[..., :3] = np.where(a > 0, np.minimum(255.0, arr[..., :3].astype(np.float32) * 255.0 / np.maximum(a, 1.0)), 0).astype(np.uint8)
        return arr
