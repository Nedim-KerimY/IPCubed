"""ViewCube: sag ustte kamera acisini gosteren, yuz / kenar / kosesine tiklayinca o yone donduren kup (CAD programlarindaki gibi).

Qt (QPainter) ile ekranin piksel yogunluguna gore keskin bir dokuya cizilir; pygfx'te ekran koordinatli ikinci bir sahnede
(ScreenCoordsCamera) bindirilir. Kup, 3D gorunumle tutarli olmasi icin perspektifle cizilir.
Her yuz 3x3 hucreye bolunur: orta = yuz, kenar serit = ayrit (iki yuz), kose = kose (uc yuz). Tiklanan hucrenin yonu = hucrenin
bakis vektoru; ayni yone giden tum hucreler birlikte vurgulanir.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6 import QtCore, QtGui

from . import theme
from .camera_rig import basis

S = 148                      # bolgenin kenari (mantiksal px)
MARGIN = 12
BTN = 26                     # kose dugmeleri
K = 30.0                     # kup yari kenari (px)
DIST = 7.5                   # perspektif kamera mesafesi (kup yari kenari birimi)
CX, CY = S / 2, S / 2 + 10   # kup merkezi
CELL = 0.52                  # orta hucrenin yari genisligi (yuz yari kenari = 1)

# yuz: (ad, dis normal, yazi sagi B, yazi yukarisi C, etiket). B x C = normal (yazi aynalanmaz)
FACES = [
    ("top", (0, 0, 1), (1, 0, 0), (0, 1, 0), "TOP"),
    ("bottom", (0, 0, -1), (1, 0, 0), (0, -1, 0), "BOTTOM"),
    ("front", (0, -1, 0), (1, 0, 0), (0, 0, 1), "FRONT"),
    ("back", (0, 1, 0), (-1, 0, 0), (0, 0, 1), "BACK"),
    ("right", (1, 0, 0), (0, 1, 0), (0, 0, 1), "RIGHT"),
    ("left", (-1, 0, 0), (0, -1, 0), (0, 0, 1), "LEFT"),
]
LIGHT = np.array([0.35, -0.55, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
RANGES = {-1: (-1.0, -CELL), 0: (-CELL, CELL), 1: (CELL, 1.0)}

C_CENTER, C_EDGE, C_CORNER = QtGui.QColor("#dfe3e8"), QtGui.QColor("#c6ccd4"), QtGui.QColor("#b0b7c1")
C_LINE = QtGui.QColor("#5d646e")
C_TEXT = QtGui.QColor("#262a31")


def region(w: int, h: int):
    """Bolgenin sol-ust kosesi (tuval mantiksal px, y asagi)."""
    return w - MARGIN - S, MARGIN


def dir_angles(v):
    """Bakis yonu (kameranin bulundugu yon vektoru) -> (yaw derece | None, pitch derece)."""
    v = np.asarray(v, float)
    v = v / np.linalg.norm(v)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))
    if abs(v[0]) + abs(v[1]) < 1e-6:
        return None, pitch
    return math.degrees(math.atan2(v[0], -v[1])), pitch


class ViewCube:
    def __init__(self):
        self.hover = None            # ("dir", (x,y,z)) | "home" | "toggle" | None
        self._font = theme.make_font(100, weight=QtGui.QFont.DemiBold)

    # ------------------------------------------------------------------ geometri (perspektif)
    @staticmethod
    def _projector(yaw, pitch):
        d, f, r, u = basis(yaw, pitch)

        def p(v):
            v = np.asarray(v, float)
            depth = DIST - float(v @ d)
            sc = DIST / max(depth, 0.2)
            return QtCore.QPointF(CX + float(v @ r) * sc * K, CY - float(v @ u) * sc * K)
        return d, p

    def _cells(self, yaw, pitch):
        """Gorunur yuzlerin hucreleri: [(derinlik, ad, normal, B, C, etiket, (i, j), poligon, yon)] arkadan one."""
        d, p = self._projector(yaw, pitch)
        out = []
        for name, n, B, C, label in FACES:
            n, B, C = np.array(n, float), np.array(B, float), np.array(C, float)
            nd = float(n @ d)
            if DIST * nd - 1.0 <= 0.02:
                continue
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    s0, s1 = RANGES[i]
                    t0, t1 = RANGES[j]
                    quad = [n + s0 * B + t0 * C, n + s1 * B + t0 * C, n + s1 * B + t1 * C, n + s0 * B + t1 * C]
                    poly = QtGui.QPolygonF([p(q) for q in quad])
                    direction = tuple(int(round(x)) for x in (n + i * B + j * C))
                    out.append((nd, name, n, B, C, label, (i, j), poly, direction))
        out.sort(key=lambda t: t[0])
        return out, p

    # ------------------------------------------------------------------ cizim
    def render(self, yaw: float, pitch: float, visible: bool, ratio: float = 1.0) -> np.ndarray:
        px = max(1, int(round(S * ratio)))
        img = QtGui.QImage(px, px, QtGui.QImage.Format_RGBA8888_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing | QtGui.QPainter.SmoothPixmapTransform)
        p.scale(px / S, px / S)
        if visible:
            self._draw_cube(p, yaw, pitch)
            self._draw_btn(p, QtCore.QRectF(0, 0, BTN, BTN), "home", self.hover == "home")
        self._draw_btn(p, QtCore.QRectF(S - BTN, 0, BTN, BTN), "toggle_on" if visible else "toggle_off", self.hover == "toggle")
        p.end()
        arr = np.frombuffer(img.constBits(), np.uint8).reshape(px, px, 4).copy()
        a = arr[..., 3:4].astype(np.float32)                 # premultiplied -> duz alfa
        arr[..., :3] = np.where(a > 0, np.minimum(255.0, arr[..., :3].astype(np.float32) * 255.0 / np.maximum(a, 1.0)), 0).astype(np.uint8)
        return arr

    def _draw_cube(self, p: QtGui.QPainter, yaw, pitch):
        cells, proj = self._cells(yaw, pitch)
        hov = self.hover[1] if isinstance(self.hover, tuple) else None
        for nd, name, n, B, C, label, (i, j), poly, direction in cells:
            hovered = hov is not None and direction == hov
            kind = 0 if (i == 0 and j == 0) else 1 if (i == 0 or j == 0) else 2
            base = QtGui.QColor(theme.ACCENT) if hovered else (C_CENTER, C_EDGE, C_CORNER)[kind]
            shade = 1.0 if hovered else 0.86 + 0.20 * max(0.0, float(n @ LIGHT))        # yuz egimine gore hafif golgeleme
            col = QtGui.QColor(min(255, int(base.red() * shade)), min(255, int(base.green() * shade)), min(255, int(base.blue() * shade)))
            p.setPen(QtGui.QPen(C_LINE, 0.9, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            p.setBrush(col)
            p.drawPolygon(poly)
        # etiketler (orta hucreler), yuz duzlemine oturur
        for nd, name, n, B, C, label, (i, j), poly, direction in cells:
            if (i, j) != (0, 0):
                continue
            hovered = hov is not None and direction == hov
            o, px_, py_ = proj(n), proj(n + B), proj(n + C)
            X = (px_.x() - o.x(), px_.y() - o.y())
            Y = (py_.x() - o.x(), py_.y() - o.y())
            t = QtGui.QTransform(X[0], X[1], -Y[0], -Y[1], o.x(), o.y())
            path = QtGui.QPainterPath()
            path.addText(0, 0, self._font, label)
            br = path.boundingRect()
            sc = min(0.94 * CELL * 2 / max(br.width(), 1), 0.34 / max(br.height(), 1))
            t.scale(sc, sc)
            t.translate(-br.center().x(), -br.center().y())
            p.save()
            p.setTransform(t, True)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#ffffff") if hovered else C_TEXT)
            p.drawPath(path)
            p.restore()

    def _draw_btn(self, p: QtGui.QPainter, r: QtCore.QRectF, kind: str, hover: bool):
        rr = r.adjusted(1, 1, -1, -1)
        p.setPen(QtGui.QPen(QtGui.QColor(theme.ACCENT if hover else "#7a7f87"), 1.0))
        p.setBrush(QtGui.QColor(theme.ACCENT if hover else "#2b2b2b"))
        p.drawRoundedRect(rr, 5, 5)
        c = r.center()
        pen = QtGui.QPen(QtGui.QColor("#ffffff" if hover else "#e6e8ec"), 1.7, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        if kind == "home":                                   # ev
            p.drawPolyline([QtCore.QPointF(c.x() - 7, c.y() + 0.5), QtCore.QPointF(c.x(), c.y() - 6.5), QtCore.QPointF(c.x() + 7, c.y() + 0.5)])
            p.drawPolyline([QtCore.QPointF(c.x() - 4.8, c.y() - 1.0), QtCore.QPointF(c.x() - 4.8, c.y() + 6.2),
                            QtCore.QPointF(c.x() + 4.8, c.y() + 6.2), QtCore.QPointF(c.x() + 4.8, c.y() - 1.0)])
        elif kind == "toggle_on":                            # gizle: x
            p.drawLine(QtCore.QPointF(c.x() - 4.5, c.y() - 4.5), QtCore.QPointF(c.x() + 4.5, c.y() + 4.5))
            p.drawLine(QtCore.QPointF(c.x() - 4.5, c.y() + 4.5), QtCore.QPointF(c.x() + 4.5, c.y() - 4.5))
        else:                                                # goster: kucuk kup
            hx = QtGui.QPolygonF([QtCore.QPointF(c.x() + 7 * math.cos(math.radians(60 * i + 30)),
                                                 c.y() + 7 * math.sin(math.radians(60 * i + 30))) for i in range(6)])
            p.drawPolygon(hx)
            p.drawLine(c, QtCore.QPointF(c.x(), c.y() - 7))
            p.drawLine(c, QtCore.QPointF(c.x() + 6.1, c.y() + 3.5))
            p.drawLine(c, QtCore.QPointF(c.x() - 6.1, c.y() + 3.5))

    # ------------------------------------------------------------------ vurus
    def hit(self, x: float, y: float, yaw: float, pitch: float, visible: bool):
        """(x, y): bolgeye gore mantiksal px. -> ("dir", (x,y,z)) | "home" | "toggle" | None"""
        if S - BTN <= x <= S and 0 <= y <= BTN:
            return "toggle"
        if not visible:
            return None
        if 0 <= x <= BTN and 0 <= y <= BTN:
            return "home"
        pt = QtCore.QPointF(x, y)
        cells, _ = self._cells(yaw, pitch)
        for nd, name, n, B, C, label, ij, poly, direction in reversed(cells):          # en yakin yuz once
            if poly.containsPoint(pt, QtCore.Qt.OddEvenFill):
                return ("dir", direction)
        return None
