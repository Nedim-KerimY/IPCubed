"""KiCad PCB duzenleyici penceresinin ustune 3D gorunumu bindirme (isletim sistemine ozgu ince katman).

Windows: pcbnew penceresine "owned window" olarak baglanir (her zaman pcbnew'in ustunde, o kuculunce kuculur).
Diger platformlar: `make_embedder` hata verir, kabuk bagimsiz pencereye duser (cekirdek/panel ayni).
"""
from __future__ import annotations

import sys

from PySide6 import QtCore, QtGui, QtWidgets

from .log import _log


def make_embedder():
    e = _make_embedder()
    from .ctl import kicad_pid
    e.owner_pid = kicad_pid()                 # yalniz bu KiCad'in penceresine bindir (ayni anda iki KiCad acik olabilir)
    return e


def _make_embedder():
    if sys.platform == "win32":
        return WinEmbedder()
    if sys.platform.startswith("linux"):
        from . import embed_x11
        if embed_x11.available():
            return embed_x11.X11Embedder()
        raise NotImplementedError("Linux: X11 + python-xlib yok (ya da Wayland oturumu): bagimsiz pencere kullanilir")
    raise NotImplementedError(f"{sys.platform} icin gomme henuz yok")


class WinEmbedder:
    owner_pid = None
    GWLP_HWNDPARENT = -8
    SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x4, 0x10, 0x40
    TCM_GETCURSEL = 0x130B

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.u = ctypes.windll.user32
        self.u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self.u.SetWindowLongPtrW.restype = ctypes.c_void_p
        self.u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.u.SendMessageW.restype = ctypes.c_ssize_t
        self.u.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT,
                                               wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        self.u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        H = wintypes.HWND                         # 64 bit HWND'ler int'e sigmayabilir: imzalar acikca
        for fn in ("IsWindow", "IsWindowVisible", "IsIconic"):
            getattr(self.u, fn).argtypes = [H]
        self.u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
        self.u.GetForegroundWindow.restype = H
        self.u.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.u.GetClassNameW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        self.u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        self.top = self.canvas_hwnd = self.tab_hwnd = self.content_hwnd = None
        self.last = {}
        self.tab_widget: QtWidgets.QLabel | None = None
        self.panel_on = True
        self.sel0 = None
        self._tab_off = 170

    # ---------------------------------------------------------------- yardimcilar
    def _rect(self, h):
        r = self.wt.RECT()
        if not self.u.GetWindowRect(h, self.ct.byref(r)):
            return None
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def _cls(self, h):
        b = self.ct.create_unicode_buffer(128)
        self.u.GetClassNameW(h, b, 128)
        return b.value

    def _children(self, h):
        out = []

        @self.ct.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)
        def cb(c, _):
            if self.u.IsWindowVisible(c):
                out.append(c)
            return True

        self.u.EnumChildWindows(h, cb, 0)
        return out

    hint = ""          # kart dosya adi (baslikta aranir)

    def _title(self, h):
        b = self.ct.create_unicode_buffer(512)
        self.u.GetWindowTextW(h, b, 512)
        return b.value

    def _is_pcb_editor(self, h) -> bool:
        """PCB duzenleyici: cizim alani + 3 sekmeli Gorsellestirme paneli (KiCad 10'da kicad.exe icinde de olabilir).
        Panel gizlenmisse: cizim alani + baslikta kart adi."""
        kids = self._children(h)
        if self._canvas_in(h, kids) is None:
            return False
        for c in kids:
            if self._cls(c) == "_wx_SysTabCtl32":
                if self._send_timeout(c, 0x1304) == 3:              # TCM_GETITEMCOUNT
                    return True
        return bool(self.hint) and self.hint.lower() in self._title(h).lower()

    def _canvas_in(self, top, kids=None):
        """PCB cizim alani. OpenGL ile: wxGLCanvas. OpenGL yoksa (sanal makine, Uzak Masaustu, eski surucu ya da KiCad'de
        "yedek grafik"): KiCad yazilim (Cairo) cizimine gecer ve wxGLCanvas olmaz -> cocugu olmayan en buyuk alt pencere."""
        kids = self._children(top) if kids is None else kids
        gl = [c for c in kids if self._cls(c) == "wxGLCanvas"]
        if gl:
            return max(gl, key=lambda c: self._area(self._rect(c)))
        cairo = [c for c in kids if self._title(c) == "CairoCanvas"]       # KiCad'in yazilim cizim alaninin pencere adi
        if cairo:
            return max(cairo, key=lambda c: self._area(self._rect(c)))
        tr = self._rect(top)
        if not tr:
            return None
        big = sorted((c for c in kids if self._cls(c).startswith("wx")), key=lambda c: -self._area(self._rect(c)))
        for c in big[:8]:
            a = self._area(self._rect(c))
            if a < 0.2 * tr[2] * tr[3]:
                break
            if not self._children(c):                             # yaprak: kap/panel degil, cizim yuzeyi
                return c
        return None

    @staticmethod
    def _area(r) -> int:
        return r[2] * r[3] if r else 0

    def _send_timeout(self, h, msg, wp=0, lp=0, ms=50):
        """KiCad'in pencerelerine mesaj: KiCad UI thread'i mesgulken (buyuk kartta IPC istegi) 3D cizim dongusu beklemesin."""
        res = self.ct.c_size_t(0)
        if not self.u.SendMessageTimeoutW(h, msg, wp, lp, 0x0002, ms, self.ct.byref(res)):     # SMTO_ABORTIFHUNG
            return None
        return res.value

    def _find_pcbnew(self):
        import psutil
        names = {}
        for p in psutil.process_iter(["name"]):
            n = (p.info["name"] or "").lower()
            if (n.startswith("pcbnew") or n.startswith("kicad")) and "cli" not in n:
                names[p.pid] = n
        if self.owner_pid is not None:
            names = {k: v for k, v in names.items() if k == self.owner_pid}
        if not names:
            return None
        cands = []

        @self.ct.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)
        def cb(h, _):
            pid = self.wt.DWORD()
            self.u.GetWindowThreadProcessId(h, self.ct.byref(pid))
            if pid.value in names and self.u.IsWindowVisible(h) and not self.u.IsIconic(h):
                r = self._rect(h)
                if r and r[2] > 400 and r[3] > 300 and self._is_pcb_editor(h):
                    t = self._title(h).lower()
                    match = 1 if (self.hint and self.hint.lower() in t) else 0
                    cands.append((match, r[2] * r[3], h))
            return True

        self.u.EnumWindows(cb, 0)
        return max(cands)[2] if cands else None

    def _locate(self):
        """-> dict(canvas=rect, content=rect, tab=rect) | None. HWND'leri onbellege alir."""
        if not self.top or not self.u.IsWindow(self.top) or not self.u.IsWindowVisible(self.top) or self.u.IsIconic(self.top):
            self.top = self._find_pcbnew()
            self.canvas_hwnd = self.tab_hwnd = self.content_hwnd = None
        if not self.top:
            return None
        if not (self.canvas_hwnd and self.u.IsWindow(self.canvas_hwnd) and self.u.IsWindowVisible(self.canvas_hwnd)):
            kids = self._children(self.top)
            tabs = [c for c in kids if self._cls(c) == "_wx_SysTabCtl32" and self._rect(c)]
            self.canvas_hwnd = self._canvas_in(self.top, kids)
            if not self.canvas_hwnd:
                return None
            self.tab_hwnd = self.content_hwnd = None
            if tabs:
                # Gorunum (Appearance) paneli: sagdaki en buyuk sekme kontrolu
                self.tab_hwnd = max(tabs, key=lambda c: self._rect(c)[3])
                tr = self._rect(self.tab_hwnd)
                inner = []
                for c in kids:
                    r = self._rect(c)
                    if r and self._cls(c) == "wxWindowNR" and self._inside(r, tr) and tr[1] + 8 < r[1] < tr[1] + 60:
                        inner.append((self._area(r), c))
                self.content_hwnd = max(inner)[1] if inner else None
        cr = self._rect(self.canvas_hwnd)
        if not cr:
            self.canvas_hwnd = None
            return None
        out = {"canvas": cr}
        if self.tab_hwnd:
            out["tab"] = self._rect(self.tab_hwnd)
            cr = self._rect(self.content_hwnd) if self.content_hwnd else None
            out["content"] = cr or (out["tab"][0], out["tab"][1] + 24, out["tab"][2], out["tab"][3] - 24)
        return out

    @staticmethod
    def _inside(r, outer):
        return r[0] >= outer[0] - 2 and r[1] >= outer[1] - 2 and r[0] + r[2] <= outer[0] + outer[2] + 2 and r[1] + r[3] <= outer[1] + outer[3] + 2

    def _hwnd(self, w):
        return int(w.winId())

    def _move(self, w, rect):
        h = self._hwnd(w)
        self.u.SetWindowPos(h, None, rect[0], rect[1], max(1, rect[2]), max(1, rect[3]),
                            self.SWP_NOZORDER | self.SWP_NOACTIVATE | self.SWP_SHOWWINDOW)
        self._moved_at = __import__("time").monotonic()

    _moved_at = 0.0

    # ---------------------------------------------------------------- kisayol / odak
    def _top_ok(self) -> bool:
        return bool(self.top and self.u.IsWindow(self.top) and self.u.IsWindowVisible(self.top) and not self.u.IsIconic(self.top))

    def editor_present(self) -> bool:
        if self._top_ok():                   # bulunan editor penceresi hala yerinde: tum pencereleri yeniden tarama
            return True
        self.top = self._find_pcbnew()
        self.canvas_hwnd = self.tab_hwnd = self.content_hwnd = None
        return self.top is not None

    def pid_has_windows(self, pid: int):
        """Surecin gorunur ust-duzey penceresi var mi (simge durumundakiler dahil)?"""
        found = []

        @self.ct.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)
        def cb(h, _):
            p = self.wt.DWORD()
            self.u.GetWindowThreadProcessId(h, self.ct.byref(p))
            if p.value == pid and self.u.IsWindowVisible(h):
                found.append(h)
                return False
            return True

        self.u.EnumWindows(cb, 0)
        return bool(found)

    def canvas_focused(self) -> bool:
        """PCB duzenleyicinin canvas'i klavye odaginda mi? (Metin kutularinda '3' yazarken tetiklenmesin.)"""
        ct, wt = self.ct, self.wt

        class GUITHREADINFO(ct.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                        ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                        ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]

        top = self.top if self._top_ok() else self._find_pcbnew()
        if not top:
            return False
        tid = self.u.GetWindowThreadProcessId(top, None)
        info = GUITHREADINFO()
        info.cbSize = ct.sizeof(GUITHREADINFO)
        if not self.u.GetGUIThreadInfo(tid, ct.byref(info)):
            return False
        gl = self.canvas_hwnd
        if not (gl and self.u.IsWindow(gl)):
            self._locate()
            gl = self.canvas_hwnd
        f = info.hwndFocus
        if not f or not gl:
            return False
        if f == gl:
            return True
        # wx, canvas'i saran bir panele odaklanir: dikdortgeni canvas'la ortusuyorsa canvas odaktadir
        rf, rc = self._rect(f), self._rect(gl)
        return bool(rf and rc and all(abs(a - b) <= 6 for a, b in zip(rf, rc)))

    _key_down = False

    def hotkey_pressed(self, vk: int = 0x33) -> bool:
        """'3' (ust sira) yeni basildi, Shift/Ctrl/Alt yok ve canvas odakta ise True (kenar algilama)."""
        g = self.u.GetAsyncKeyState
        st = g(vk)
        down = bool(st & 0x8000)
        # bit 0: son sorgudan beri basildi. Dongumuz gecikirse (or. KiCad'in arayuz thread'i baska bir eklenti yuzunden mesgul)
        # kisa bir basis iki sorgu arasinda baslayip bitebilir: o da sayilir
        edge = not self._key_down and (down or bool(st & 1))
        self._key_down = down
        if not edge:
            return False
        if any(g(m) & 0x8000 for m in (0x10, 0x11, 0x12, 0x5B, 0x5C)):       # shift ctrl alt win
            _log("tus 3: degistirici tusla -> yok sayildi")
            return False
        if not self._kicad_foreground():          # '3' bindirmenin kendisinde: Qt kisayolu zaten isledi (cift gecis olmasin)
            _log("tus 3: on planda KiCad yok -> yok sayildi")
            return False
        if not self.canvas_focused():
            _log("tus 3: PCB tuvali odakta degil -> yok sayildi")
            return False
        return True

    def _kicad_foreground(self) -> bool:
        fg = self.u.GetForegroundWindow()
        if not fg or not self.top:
            return True                            # bilinmiyor: eski davranis
        pid, top_pid = self.wt.DWORD(), self.wt.DWORD()
        self.u.GetWindowThreadProcessId(fg, self.ct.byref(pid))
        self.u.GetWindowThreadProcessId(self.top, self.ct.byref(top_pid))
        return pid.value == top_pid.value

    def focus(self, w: QtWidgets.QWidget):
        """Yeni acilan pencereye klavye odagi ver (arka plan sureci oldugumuz icin Alt hilesi gerekir)."""
        h = self._hwnd(w)
        self.u.keybd_event(0x12, 0, 0, 0)
        self.u.keybd_event(0x12, 0, 2, 0)
        self.u.SetForegroundWindow(h)
        w.setFocus()

    # ---------------------------------------------------------------- arayuz
    def prepare(self, w: QtWidgets.QWidget):
        w.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)

    def own(self, w: QtWidgets.QWidget):
        """Pencereyi KiCad'e bagla (KiCad'in ustunde kalir, o kuculunce kuculur)."""
        if self.top:
            self.u.SetWindowLongPtrW(self._hwnd(w), self.GWLP_HWNDPARENT, self.top)

    def place(self, canvas: QtWidgets.QWidget) -> bool:
        loc = self._locate()
        if not loc:
            return False
        canvas.show()
        self.own(canvas)
        self.last = {}
        self.follow(canvas)
        self.focus(canvas)
        return True

    def follow(self, canvas) -> bool:
        """Bindirmeyi canvas'in uzerinde tut. Kapali dongu: KiCad'in dikdortgeni degismese de bindirmenin GERCEK dikdortgeni
        hedeften saparsa (Qt kendi minimum boyutuna dondurdu, farkli DPI'li monitore gecis -> WM_DPICHANGED...) duzeltilir."""
        import time
        loc = self._locate()
        if not loc:
            return False
        if loc != self.last:
            self._move(canvas, loc["canvas"])
            self.last = loc
        elif time.monotonic() - self._moved_at > 0.25:           # duzeltme dongusu: en fazla 4/sn (Qt ile kavga etmesin)
            actual = self._rect(self._hwnd(canvas))
            target = tuple(loc["canvas"])
            mins = canvas.minimumSize() * self._dpr(canvas)
            fits = target[2] >= mins.width() and target[3] >= mins.height()   # canvas Qt minimumundan kucukse Qt zaten buyutur
            if actual and actual != target and fits:
                self._move(canvas, target)
        return True

    @staticmethod
    def _dpr(w) -> float:
        try:
            return float(w.devicePixelRatioF()) or 1.0
        except Exception:  # noqa: BLE001
            return 1.0

    def canvas_rect(self):
        return self.last.get("canvas") if self.last else None

    def release(self, canvas):
        pass

    # --- harici pencere: Qt bayraklari degistirilmez (HWND yeniden yaratilirsa wgpu yuzeyi gecersiz olur); Win32 stili degisir
    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_OVERLAPPEDWINDOW, WS_POPUP, WS_VISIBLE = 0x00CF0000, 0x80000000, 0x10000000
    WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
    SWP_FRAMECHANGED = 0x20

    def _restyle(self, w, style, add_ex, del_ex, rect, owner):
        h = self._hwnd(w)
        self.u.GetWindowLongPtrW.argtypes = [self.wt.HWND, self.ct.c_int]
        self.u.GetWindowLongPtrW.restype = self.ct.c_ssize_t
        ex = (self.u.GetWindowLongPtrW(h, self.GWL_EXSTYLE) | add_ex) & ~del_ex
        self.u.SetWindowLongPtrW(h, self.GWLP_HWNDPARENT, owner)
        self.u.SetWindowLongPtrW(h, self.GWL_STYLE, style | self.WS_VISIBLE)
        self.u.SetWindowLongPtrW(h, self.GWL_EXSTYLE, ex)
        self.u.SetWindowPos(h, None, rect[0], rect[1], rect[2], rect[3], self.SWP_NOZORDER | self.SWP_FRAMECHANGED | self.SWP_SHOWWINDOW)

    def make_external(self, w: QtWidgets.QWidget, title: str):
        """KiCad'e bagli bindirmeyi birak: baslik cubuklu, boyutlandirilabilir, gorev cubugunda normal pencere.
        Bayraklar QWindow uzerinden degistirilir (HWND yeniden yaratilmaz; wgpu yuzeyi bozulmaz)."""
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        cw = min(1500, int(screen.width() * 0.8)); ch = min(950, int(screen.height() * 0.82))
        rect = QtCore.QRect(screen.x() + (screen.width() - cw) // 2, screen.y() + (screen.height() - ch) // 2, cw, ch)
        w.setWindowTitle(title)
        self.u.SetWindowLongPtrW(self._hwnd(w), self.GWLP_HWNDPARENT, None)       # KiCad sahipligini birak
        wh = w.windowHandle()
        wh.setFlags(QtCore.Qt.Window | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowSystemMenuHint
                    | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        w.setGeometry(rect)
        w.show()
        self.last = {}

    def make_embedded(self, w: QtWidgets.QWidget):
        """Harici pencereden KiCad bindirmesine don (place() sonra konumlandirir)."""
        wh = w.windowHandle()
        wh.setFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        w.show()
