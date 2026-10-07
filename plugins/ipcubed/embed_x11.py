"""Linux / X11: KiCad PCB duzenleyicisinin uzerine 3D gorunumu bindirme (python-xlib).

Wayland oturumunda baska bir istemcinin penceresinin konumu okunamaz ve pencere o istemcinin uzerine yerlestirilemez; orada
`make_embedder` NotImplementedError verir ve kabuk bagimsiz pencereye duser (hotkey yerine `python -m ipcubed.ctl toggle`).
NOT: Bu dosya Windows makinesinde yazildi; gercek bir X11 oturumunda henuz denenmedi.

Pencere/tuval bulma Windows uyarlayicisiyla ayni mantik: KiCad sinifli (WM_CLASS) pencerelerin icinde buyuk bir alt pencere
(wxGLCanvas'in X penceresi) aranir; en buyugu tuvaldir.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets


class X11Embedder:
    MIN_CANVAS = (300, 200)

    def __init__(self):
        from Xlib import X, XK, display
        self.X = X
        self.d = display.Display()
        self.root = self.d.screen().root
        a = self.d.intern_atom
        self.A_CLIENT_LIST, self.A_ACTIVE = a("_NET_CLIENT_LIST"), a("_NET_ACTIVE_WINDOW")
        self.A_NAME, self.A_UTF8 = a("_NET_WM_NAME"), a("UTF8_STRING")
        self.kc3 = self.d.keysym_to_keycode(XK.XK_3)
        self.mod_kcs = [self.d.keysym_to_keycode(getattr(XK, n)) for n in
                        ("XK_Shift_L", "XK_Shift_R", "XK_Control_L", "XK_Control_R", "XK_Alt_L", "XK_Alt_R", "XK_Super_L", "XK_Super_R")]
        self.top = None                 # PCB duzenleyici ust-duzey pencere (Xlib penceresi)
        self.canvas = None              # tuval alt penceresi
        self.last = {}
        self.hint = ""
        self._foreign = None            # Qt'de sahip pencere sarmalayicisi (referans tutulmali)
        self._key_down = False

    # ---------------------------------------------------------------- Xlib yardimcilari
    def _safe(self, fn, default=None):
        try:
            return fn()
        except Exception:  # noqa: BLE001  (BadWindow: pencere kapanmis)
            return default

    def _title(self, win) -> str:
        p = self._safe(lambda: win.get_full_property(self.A_NAME, self.A_UTF8))
        if p is not None and p.value:
            v = p.value
            return v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)
        return self._safe(lambda: win.get_wm_name(), "") or ""

    def _rect(self, win):
        """Pencerenin ekrandaki mutlak (x, y, w, h) fiziksel pikseli."""
        g = self._safe(lambda: win.get_geometry())
        c = self._safe(lambda: win.translate_coords(self.root, 0, 0))
        if g is None or c is None:
            return None
        return (-c.x, -c.y, g.width, g.height)

    def _viewable(self, win) -> bool:
        at = self._safe(lambda: win.get_attributes())
        return at is not None and at.map_state == self.X.IsViewable

    def _clients(self):
        p = self._safe(lambda: self.root.get_full_property(self.A_CLIENT_LIST, self.X.AnyPropertyType))
        ids = list(p.value) if p is not None else []
        return [self.d.create_resource_object("window", i) for i in ids]

    def _canvas_of(self, top):
        """Ust-duzey pencerenin en buyuk gorunur alt penceresi (>= MIN_CANVAS). -> (pencere, rect) | None"""
        best = None
        top_r = self._rect(top)
        if not top_r:
            return None
        stack, seen = [top], 0
        while stack and seen < 600:
            w = stack.pop()
            seen += 1
            tree = self._safe(lambda: w.query_tree())
            if tree is None:
                continue
            for ch in tree.children:
                if not self._viewable(ch):
                    continue
                r = self._rect(ch)
                if not r:
                    continue
                if r[2] >= self.MIN_CANVAS[0] and r[3] >= self.MIN_CANVAS[1] and r[2] * r[3] < top_r[2] * top_r[3] * 0.985:
                    if best is None or r[2] * r[3] > best[1][2] * best[1][3]:
                        best = (ch, r)
                stack.append(ch)
        return best

    # ---------------------------------------------------------------- bulma
    def _find_editor(self):
        cands = []
        for w in self._clients():
            cls = self._safe(lambda: w.get_wm_class())
            if not cls or not any(k in (cls[0] + " " + cls[1]).lower() for k in ("kicad", "pcbnew")):
                continue
            if not self._viewable(w):
                continue
            r = self._rect(w)
            if not r or r[2] < 400 or r[3] < 300:
                continue
            cv = self._canvas_of(w)
            if cv is None:                                  # proje yoneticisi vb.: buyuk GL tuvali yok
                continue
            t = self._title(w).lower()
            score = (1 if (self.hint and self.hint.lower() in t) else 0, 1 if "pcb" in t else 0, r[2] * r[3])
            cands.append((score, w, cv))
        if not cands:
            return None
        cands.sort(key=lambda c: c[0], reverse=True)
        return cands[0][1], cands[0][2]

    def editor_present(self) -> bool:
        return self._find_editor() is not None

    def _locate(self):
        """-> {'canvas': (x, y, w, h)} mantiksal piksel | None"""
        if self.top is not None and not (self._viewable(self.top) and self.canvas is not None and self._viewable(self.canvas[0])):
            self.top = self.canvas = None
        if self.top is None:
            found = self._find_editor()
            if not found:
                return None
            self.top, self.canvas = found
        r = self._rect(self.canvas[0])
        if not r:
            self.top = self.canvas = None
            return None
        ratio = QtGui.QGuiApplication.primaryScreen().devicePixelRatio() or 1.0       # Qt mantiksal piksel
        return {"canvas": tuple(int(round(v / ratio)) for v in r)}

    # ---------------------------------------------------------------- kisayol / odak
    def canvas_focused(self) -> bool:
        """PCB duzenleyici etkin pencere mi? (X11'de wx/GTK alt pencere odagi ayirt edilemez; etkin pencereye bakilir.)"""
        found = self.top or (self._find_editor() or (None,))[0]
        if found is None:
            return False
        p = self._safe(lambda: self.root.get_full_property(self.A_ACTIVE, self.X.AnyPropertyType))
        return bool(p is not None and p.value and int(p.value[0]) == found.id)

    def hotkey_pressed(self) -> bool:
        """'3' yeni basildi, Shift/Ctrl/Alt/Super yok ve editor etkinse True."""
        keys = self._safe(lambda: self.d.query_keymap())
        if keys is None:
            return False

        def down(kc):
            return bool(keys[kc // 8] & (1 << (kc % 8)))

        is_down = down(self.kc3)
        edge = is_down and not self._key_down
        self._key_down = is_down
        if not edge or any(down(k) for k in self.mod_kcs):
            return False
        return self.canvas_focused()

    def focus(self, w: QtWidgets.QWidget):
        w.raise_()
        w.activateWindow()
        w.setFocus()

    # ---------------------------------------------------------------- arayuz (WinEmbedder ile ayni)
    def prepare(self, w: QtWidgets.QWidget):
        w.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)

    def own(self, w: QtWidgets.QWidget):
        """KiCad'in 'transient' penceresi yap: KiCad'in ustunde kalir, o kuculunce kuculur."""
        if self.top is None or w.windowHandle() is None:
            return
        self._foreign = QtGui.QWindow.fromWinId(self.top.id)
        w.windowHandle().setTransientParent(self._foreign)

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
        loc = self._locate()
        if not loc:
            return False
        if loc != self.last:
            x, y, w, h = loc["canvas"]
            canvas.setGeometry(QtCore.QRect(x, y, w, h))
            self.last = loc
        return True

    def canvas_rect(self):
        return self.last.get("canvas") if self.last else None

    def release(self, canvas):
        pass

    def make_external(self, w: QtWidgets.QWidget, title: str):
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        cw = min(1500, int(screen.width() * 0.8)); ch = min(950, int(screen.height() * 0.82))
        w.setWindowTitle(title)
        wh = w.windowHandle()
        wh.setTransientParent(None)
        wh.setFlags(QtCore.Qt.Window | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowSystemMenuHint
                    | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        w.setGeometry(QtCore.QRect(screen.x() + (screen.width() - cw) // 2, screen.y() + (screen.height() - ch) // 2, cw, ch))
        w.show()
        self.last = {}

    def make_embedded(self, w: QtWidgets.QWidget):
        w.windowHandle().setFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        w.show()


def available() -> bool:
    """X11 uzerinde miyiz ve python-xlib var mi?"""
    if not os.environ.get("DISPLAY"):
        return False
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and os.environ.get("GDK_BACKEND", "").lower() != "x11":
        return False                # KiCad (GTK) Wayland'de yerel Wayland istemcisi: X11 yoluyla gorunmez
    try:
        import Xlib  # noqa: F401
    except ImportError:
        return False
    return True
