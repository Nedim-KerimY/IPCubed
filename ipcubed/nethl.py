"""Net Highlighter: fare altindaki net mavi yanip soner; secilen net(ler) normal isikla one cikar, kartin kalani kararir.

Geometri yeniden uretilmez: bakir mesh'lerinin vertex etiketlerinde (alt 16 bit = net) net zaten var. Her bakir mesh'inden
o netin ucgenleri ayiklanir ve AYNI vertex tamponlarini paylasan kucuk mesh'ler yapilir (birkac ms).

Cizim (ana sahneden sonra, ayni kare):
  secim varsa: ekran boyu yari saydam siyah (karartma) -> derinlik temizlenir -> secili netler kendi malzemeleriyle
               (karartilmis nesneler secili netin onunu kapatmaz; secili netler kendi aralarinda dogru ortulur)
  fare altinda net varsa: mavi, derinlik testi YOK (kartin arkasindaki bakir da gorunur), opaklik zamanla gidip gelir
"""
from __future__ import annotations

import math
import time

import numpy as np
import pygfx as gfx

NET_MASK = 0xFFFF
HOVER_COLOR = "#2f8cff"
PULSE_S = 1.1            # yanip sonme periyodu (sn)
DIM = 0.9                # karartma (lineer renk uzayinda: 0.9 ~ ekranda belirgin kararma); 0 = yok, 1 = siyah


def pair_name(name: str) -> str | None:
    """Diff pair esinin adi (KiCad: son karakter +/- ya da P/N; ornek USB_D+ / USB_D-, TX_P / TX_N)."""
    if not name:
        return None
    sw = {"+": "-", "-": "+", "P": "N", "N": "P", "p": "n", "n": "p"}
    c = name[-1]
    if c not in sw or len(name) < 2:
        return None
    return name[:-1] + sw[c]


class NetHighlighter:
    def __init__(self, vs):
        self.vs = vs
        self.selected: set[int] = set()
        self.hover: set[int] = set()
        self._sig = None
        self._idx: dict = {}                 # anahtar -> (sirali ucgenler, sirali netler)
        self._built: dict = {}               # ('sel'|'hov', nets) -> imza (yeniden kurmamak icin)
        self._owner: dict[int, str] = {}     # vurgulama mesh id -> kaynak katman anahtari (picking)
        self.sel_scene = gfx.Scene()
        self.hov_scene = gfx.Scene()
        self._sel_group = gfx.Group(); self.sel_scene.add(self._sel_group)
        self._hov_group = gfx.Group(); self.hov_scene.add(self._hov_group)
        self.ambient = gfx.AmbientLight(); self.sun = gfx.DirectionalLight(); self.fill = gfx.DirectionalLight()
        for l in (self.ambient, self.sun, self.fill):
            self.sel_scene.add(l)
        self.dim_scene = gfx.Scene()
        dm = gfx.MeshBasicMaterial(color="#000000", opacity=DIM)
        dm.alpha_mode = "blend"
        dm.depth_test = False
        dm.depth_write = False
        self._dim = gfx.Mesh(gfx.plane_geometry(1, 1), dm)
        self.dim_scene.add(self._dim)
        self._screen_cam = gfx.ScreenCoordsCamera()
        hm = gfx.MeshBasicMaterial(color=HOVER_COLOR, opacity=0.0, side="both")
        hm.alpha_mode = "blend"
        hm.depth_test = False
        hm.depth_write = False
        self._hov_mat = hm

    # ------------------------------------------------------------------ durum
    @property
    def active(self) -> bool:
        return bool(self.selected or self.hover)

    def pulsing(self) -> bool:
        return bool(self.hover)

    def clear(self):
        self.selected = set()
        self.hover = set()

    # ------------------------------------------------------------------ geometri
    def _copper_keys(self):
        vs = self.vs
        polys = vs.cfg.highlight_polygons
        for key, m in vs.layer_meshes.items():
            if key.startswith("cuz:") and not polys:
                continue                                   # Highlight Polygons: False -> pour'lar vurgulanmaz / secilmez
            if vs._kind(key) in ("cu", "finish", "barrel") and vs.layer_tags.get(key) is not None:
                yield key, m

    def _signature(self):
        return tuple((k, id(m), id(m.geometry.indices)) for k, m in self._copper_keys())

    def _refresh_index(self):
        """Bakir mesh'leri degistiyse (canli duzenleme, pad tasima, ic katman yuklendi) ucgen->net dizinini yenile."""
        sig = self._signature()
        if sig == self._sig:
            return False
        self._sig = sig
        old, self._idx = self._idx, {}
        for key, m in self._copper_keys():
            ent = old.get(key)
            ind = m.geometry.indices
            if ent is not None and ent[0] is ind:
                self._idx[key] = ent
                continue
            T = np.asarray(ind.data).reshape(-1, 3)
            G = self.vs.layer_tags[key]
            if len(G) == 0 or len(T) == 0:
                continue
            net = (G[T[:, 0]].astype(np.int64) & NET_MASK).astype(np.int32)
            order = np.argsort(net, kind="stable")
            self._idx[key] = (ind, T[order], net[order])
        self._built.clear()
        return True

    def _tris_for(self, key, nets):
        _, T, net = self._idx[key]
        parts = []
        for n in nets:
            a, b = np.searchsorted(net, n, "left"), np.searchsorted(net, n, "right")
            if b > a:
                parts.append(T[a:b])
        if not parts:
            return None
        return np.ascontiguousarray(np.concatenate(parts), dtype=np.uint32)

    def _rebuild(self, which: str, nets: set, group: gfx.Group):
        want = (which, tuple(sorted(nets)))
        if self._built.get(which) == (want, self._sig):
            return
        self._built[which] = (want, self._sig)
        for ch in list(group.children):
            self._owner.pop(id(ch), None)
            group.remove(ch)
        if not nets:
            return
        for key, m in self._copper_keys():
            if key not in self._idx:
                continue
            T = self._tris_for(key, nets)
            if T is None:
                continue
            g = m.geometry
            geo = gfx.Geometry(positions=g.positions, normals=g.normals, indices=gfx.Buffer(T))
            mat = m.material if which == "sel" else self._hov_mat       # secim: kendi malzemesi (normal isik)
            hm = gfx.Mesh(geo, mat)
            group.add(hm)
            self._owner[id(hm)] = key

    def sync(self):
        self._refresh_index()
        self._rebuild("sel", self.selected, self._sel_group)
        self._rebuild("hov", self.hover, self._hov_group)

    # ------------------------------------------------------------------ picking
    def net_at(self, info: dict) -> int | None:
        """renderer.get_pick_info sonucundan net id (0 = netsiz -> None)."""
        wo = info.get("world_object") if info else None
        fi = info.get("face_index") if info else None
        if wo is None or fi is None:
            return None
        key = self._owner.get(id(wo))
        if key is None:
            for k, m in self.vs.layer_meshes.items():
                if m is wo:
                    key = k
                    break
        G = self.vs.layer_tags.get(key) if key is not None else None
        if G is None:
            return None
        T = np.asarray(wo.geometry.indices.data).reshape(-1, 3)
        if not (0 <= fi < len(T)):
            return None
        n = int(G[T[fi, 0]]) & NET_MASK
        return n or None

    # ------------------------------------------------------------------ cizim
    def _sync_lights(self):
        vs = self.vs
        self.sel_scene.environment = vs.scene.environment
        for dst, src in ((self.ambient, vs.ambient), (self.sun, vs.sun), (self.fill, vs.fill)):
            dst.intensity = src.intensity
            dst.local.position = src.local.position

    def render(self, renderer, camera, w, h):
        if not self.active:
            return
        self.sync()
        for grp in (self._sel_group, self._hov_group):               # exploded view: kaynak katmanla ayni kayma
            for ch in grp.children:
                src = self.vs.layer_meshes.get(self._owner.get(id(ch)))
                if src is not None:
                    ch.local.position = src.local.position
        if self.selected:
            self._dim.local.scale = (w, h, 1)
            self._dim.local.position = (w / 2, h / 2, 0)
            renderer.render(self.dim_scene, self._screen_cam, flush=False)
            renderer.clear(depth=True)
            self._sync_lights()
            renderer.render(self.sel_scene, camera, flush=False)
        if self.hover:
            s = 0.5 - 0.5 * math.cos(2 * math.pi * (time.perf_counter() % PULSE_S) / PULSE_S)
            self._hov_mat.opacity = 0.15 + 0.7 * s
            renderer.render(self.hov_scene, camera, flush=False)
