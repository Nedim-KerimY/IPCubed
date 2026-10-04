"""Exploded board view: kartin sag alt kosesinde 3D katman araligi cubugu (gizmo).

Dikey bir ray; her bakir katmaninin YUKSEKLIGINDE bir buyuk mavi kup (surukle -> katman araligi), her buyuk kupe kisa bir cubukla
bagli kucuk kup (yesil = gorunur, kirmizi = gizli; tik = ac/kapat, surukleme = buyuk kup gibi).
Kupler sahnenin parcasidir: kartla birlikte doner, katmanlar ayrildikca kendi katmaniyla birlikte hareket eder.

Gorunum: saf kirmizi/yesil/mavi, sahne isigindan etkilenmez (MeshBasic); bicim sabit yuz tonlariyla okunur (ust yuz saf renk,
yanlar koyu). Hafif saydam ama TEK PARCA gibi: once tum gizmo yalniz derinlige yazilir, sonra yalniz en ondeki yuzey renklenir
(icteki cubuk / arka yuzler gorunmez).
"""
from __future__ import annotations

import numpy as np
import pygfx as gfx

from .nethl import HOVER_COLOR as BLUE        # Net Highlighter mavisiyle ayni
BLUE_HOVER = "#8cc0ff"
GREEN = "#00ff00"
RED = "#ff0000"
OPACITY = 0.82                  # hafif saydam: arkasindaki kart gorunur


def _rgb(hexs: str):
    h = hexs.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def _tone(normals: np.ndarray) -> np.ndarray:
    """Sabit yuz tonu (isiktan bagimsiz): ust/alt 1.0, x yuzleri 0.78, y yuzleri 0.62; silindir: yana gore arada."""
    n = np.abs(normals)
    return np.where(n[:, 2] > 0.5, 1.0, 0.62 + 0.16 * n[:, 0]).astype(np.float32)


def _paint(mesh: gfx.Mesh, color: str):
    geo = mesh.geometry
    col = np.ones((len(geo.positions.data), 4), np.float32)
    c = _tone(geo.normals.data)[:, None] * _rgb(color)[None]           # sRGB (malzeme rengi gibi)
    col[:, :3] = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)   # vertex rengi lineer yorumlanir
    if getattr(geo, "colors", None) is None:
        geo.colors = gfx.Buffer(col)
    else:
        geo.colors.data[:] = col
        geo.colors.update_full()


def _part(geo, color: str) -> gfx.Mesh:
    m = gfx.MeshBasicMaterial(color_mode="vertex", opacity=OPACITY)
    m.alpha_mode = "blend"
    m.depth_compare = "<="               # yalniz derinlik on-gecisinin biraktigi (en ondeki) yuzey
    m.depth_write = False
    m.pick_write = True
    mesh = gfx.Mesh(geo, m)
    mesh.render_order = 21
    _paint(mesh, color)
    return mesh


def _depth(geo) -> gfx.Mesh:
    """Gorunmez, yalniz derinlik yazan kopya (renk gecisinden once)."""
    m = gfx.MeshBasicMaterial(color="#000000", opacity=0.0)
    m.alpha_mode = "blend"
    m.depth_write = True
    mesh = gfx.Mesh(geo, m)
    mesh.render_order = 20
    return mesh


class ExploderGizmo:
    """layers: [(anahtar, ad, gorunur)] ustten alta. Boyutlar karta gore olceklenir."""

    def __init__(self):
        self.group = gfx.Group()
        self.big: list[gfx.Mesh] = []
        self.small: list[gfx.Mesh] = []
        self.sticks: list[gfx.Mesh] = []
        self._depth: list[tuple] = []        # (renkli parca, derinlik kopyasi): ayni konum
        self.rail = None
        self.layers: list = []
        self.hover = None                    # ('big'|'small', i)
        self.size = 2.0                      # buyuk kup kenari (mm)

    def _add(self, geo, color):
        p, d = _part(geo, color), _depth(geo)
        self.group.add(d); self.group.add(p)
        self._depth.append((p, d))
        return p

    def build(self, layers, corner, board_size: float):
        """corner: (x, y) kartin sag alt kosesinin biraz disi. board_size: kartin kosegeni (mm) -> kup boyutu."""
        for ch in list(self.group.children):
            self.group.remove(ch)
        self._depth = []
        self.layers = list(layers)
        self.size = max(1.0, min(3.0, board_size * 0.0095))
        s = self.size
        self.corner = corner
        self.big, self.small, self.sticks = [], [], []
        for _, _, vis in self.layers:
            self.big.append(self._add(gfx.box_geometry(s, s, s), BLUE))
            self.sticks.append(self._add(gfx.box_geometry(s * 0.9, s * 0.14, s * 0.14), BLUE))
            self.small.append(self._add(gfx.box_geometry(s * 0.5, s * 0.5, s * 0.5), GREEN if vis else RED))
        self.rail = self._add(gfx.cylinder_geometry(s * 0.09, s * 0.09, 1.0, radial_segments=16), BLUE)

    def place(self, zs):
        """Kuplari katman yuksekliklerine koy (animasyon / surukleme her karede cagirabilir)."""
        x, y = self.corner
        s = self.size
        for b, st, sm, z in zip(self.big, self.sticks, self.small, zs):
            b.local.position = (x, y, z)
            st.local.position = (x + s * 0.95, y, z)        # cubuk kartin disina dogru (+x)
            sm.local.position = (x + s * 1.65, y, z)
        if self.rail is not None and len(zs):
            z0, z1 = min(zs), max(zs)
            self.rail.local.scale = (1, 1, max(z1 - z0, 1e-3))
            self.rail.local.position = (x, y, (z0 + z1) / 2)
        for p, d in self._depth:
            d.local.position = p.local.position
            d.local.scale = p.local.scale

    def set_visible_flags(self, flags):
        for sm, v in zip(self.small, flags):
            _paint(sm, GREEN if v else RED)

    def set_hover(self, hit):
        if hit == self.hover:
            return False
        old, self.hover = self.hover, hit
        for h in (old, hit):
            if h is not None and h[0] == "big":
                _paint(self.big[h[1]], BLUE_HOVER if h == hit else BLUE)
        return True

    def hit_object(self, wo):
        """Picking sonucu -> ('big'|'small', i) | None (cubuk = kucuk kup)."""
        for i, (b, st, sm) in enumerate(zip(self.big, self.sticks, self.small)):
            if wo is b:
                return ("big", i)
            if wo is sm or wo is st:
                return ("small", i)
        return None
