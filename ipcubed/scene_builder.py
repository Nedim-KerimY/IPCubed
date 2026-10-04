"""pygfx sahnesi: tum stackup (dielektrik, bakir, maske, silk) + instanced footprint modelleri."""
from __future__ import annotations

import os
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import compat  # noqa: F401  (pygfx'ten once)
import pygfx as gfx

import dataclasses

from .geometry import model_matrix, outline_to_polygon
from .kicad_source import BoardSnapshot, FootprintData
from .model_loader import MeshData, load_model
from .paths import resolve_model_path
from .settings import Settings

DRILL_COLOR = "#0b0b0b"


def _solid(mat):
    """Opak malzeme: pygfx 'solid' alfa modu -> once-arkaya siralanir, karistirma yok (daha az fazla boyama)."""
    try:
        mat.alpha_mode = "solid"
    except Exception:  # noqa: BLE001
        pass
    return mat


def _pick(mat):
    """Bakir: fare altindaki ucgen GPU'dan okunabilsin (Net Highlighter)."""
    mat.pick_write = True
    return mat


def _natural(s: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _hex(c: str, a: float = 1.0):
    c = c.lstrip("#")
    return (int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255, a)


from .workers import (_warm_imports, _body_tiles_cuts, _body_worker, _cu_worker, _cuts_worker, _via_worker, _zone_worker, _extras_worker, _load_worker, _mask_worker,  # noqa: E402  (pygfx icermeyen hafif modul)
                      _silk_worker, _track_worker)


def free_memory_gb() -> float | None:
    """Bos RAM (GB); bilinmiyorsa None."""
    try:
        import psutil
        return psutil.virtual_memory().available / 2**30
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in
                                                                              ("tp", "ap", "tpf", "apf", "tv", "av", "ae")]
            ms = MS(); ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return ms.ap / 2**30
        except Exception:
            return None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable"):
                    return int(line.split()[1]) / 2**20
    except OSError:
        pass
    return None


def make_pool(n: int) -> ProcessPoolExecutor:
    """Isci havuzu (her platformda spawn). Not: max_tasks_per_child spawn ile burada kilitlenir, kullanilmaz."""
    import multiprocessing
    # Linux/macOS: varsayilan fork, Qt/wgpu thread'leri varken guvensiz; her yerde spawn kullan (Windows zaten spawn)
    return ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("spawn"))


def auto_workers() -> int:
    """Isci sayisi: CPU cekirdegi ve BOS BELLEGE gore (buyuk kartta isci basina ~1 GB; bellek bitince isci olur ve her sey durur)."""
    n = max(2, min(6, (os.cpu_count() or 4) - 2))
    free = free_memory_gb()
    if free is not None:
        n = min(n, max(2, int(free / 1.2)))
    return n


class ModelGroup:
    """Ayni model dosyasi + ayni yuz -> tek InstancedMesh."""

    def __init__(self, path: Path, bottom: bool):
        self.path, self.bottom = path, bottom
        self.mesh: gfx.InstancedMesh | None = None          # opak parcalar
        self.mesh_t: gfx.InstancedMesh | None = None        # yari saydam parcalar (lens, cam)
        self.slots: list[tuple[str, int]] = []
        self.slot_of: dict[tuple[str, int], int] = {}
        self.matrices: list[np.ndarray] = []

    @property
    def meshes(self) -> list:
        return [m for m in (self.mesh, self.mesh_t) if m is not None]


class ViewerScene:
    def __init__(self, settings: Settings | None = None, workers: int | None = None):
        self.cfg = settings or Settings()
        self.scene = gfx.Scene()
        self.root = gfx.Group()
        self.scene.add(self.root)
        # Aydinlatma: dusuk ortam + ana isik + dolgu; asil kalite proseduel studyo ortam haritasindan (yansima + yumusak isik)
        self.ambient = gfx.AmbientLight(intensity=0.50)
        self.sun = gfx.DirectionalLight(intensity=1.75)
        self.sun.local.position = (0.35, -0.55, 1.0)
        self.fill = gfx.DirectionalLight(intensity=0.60)
        self.fill.local.position = (-0.65, 0.3, 0.55)
        for l in (self.ambient, self.sun, self.fill):
            self.scene.add(l)
        from .lighting import make_environment
        self.scene.environment = make_environment()
        self.background = gfx.Background.from_color(self.cfg.bg_top, self.cfg.bg_bottom)
        self.scene.add(self.background)

        self.thickness = 1.6
        self.stack = None
        self._snap: BoardSnapshot | None = None
        self.board_bounds = None
        self.layer_meshes: dict[str, gfx.Mesh] = {}
        self.mask_haze: dict[str, tuple] = {}          # maske anahtari -> (renk tonu mesh, yansima mesh)
        self.layer_tags: dict[str, np.ndarray] = {}          # vertex basina ag id'si (ileride vurgulama)
        self.layer_futures: list[Future] = []
        self._tri: dict[str, tuple] = {}                 # pad iceren taban mesh'lerin (indeks, vertex etiketi) -> canli tasimada ucgen ayiklama
        self._tri_gen = 0
        self._base_fp: dict = {}                         # taban mesh'lerin uretildigi andaki footprint konumlari
        self._batch: dict | None = None                  # ayni kart yenilemesi: sonuclar hepsi bitince TEK SEFERDE uygulanir
        self._batch_poses: dict = {}
        self._tiles: dict = {}                           # karo grubu -> {karo: mesh}
        self._tile_dirty: set = set()
        self._pending_plan: dict | None = None           # kismi yenileme: henuz uygulanmamis birlesik plan
        self._dyn_sig = None
        self._pad_sync_needed = False
        self._mask_fut = None                            # canli pad tasima: yalniz maske levhasi hizli yeniden uretimi (~1.5 sn)
        self._mask_sig = None                            # gonderilen isin (taban nesli, tasinan footprint konumlari)
        self._mask_shown = None                          # ekrandaki maske mesh'inin karsiligi olan imza
        self._mask_gen = 0
        self._mask_tiles_live: set = set()               # canli maske guncellemesinin dokundugu karolar (taban yenilenince sifirlanir)
        self._mask_cuts = None
        self._fast_pool = None                           # TEK iscili kalici havuz: canli kucuk isler (iz/zone/maske); kirpma onbellegi isinir
        self._fast_idle = None
        self._warm_key = None
        self._warm_futs: list = []
        self._ex: dict = {}                              # exploded view: bakir layer_id -> ek z (mm); bos = normal
        self.ex_hide_diel = False                        # exploded view'da dielektrik gizli mi
        self._tube_base: dict = {}                       # tup mesh'leri: (pozisyon tamponu, ozgun z, son ofset imzasi)
        self.keep_pool = False                           # 3D acikken is havuzu uzun sure acik kalir (anlik maske guncellemesi)
        self._pad_clip = None
        self._inner: dict[int, str] = {}                 # ic bakir katmani -> 'pending' | 'done' (yalniz GORUNUR olanlar uretilir)
        self._inner_fut: dict = {}
        self._diel_key: dict[str, tuple] = {}            # dielektrik vertex renkleri: son uygulanan (renk, kenar rengi)
        self.groups: dict[tuple[Path, bool], ModelGroup] = {}
        self.mesh_data: dict[Path, MeshData] = {}
        self.loading: dict[Path, Future] = {}
        self.fps: dict[str, FootprintData] = {}
        self.hidden: set[tuple[str, int]] = set()          # gizlenen model ornekleri (footprint kiid, model index)
        self.missing: set[str] = set()
        self._workers = workers or auto_workers()
        self._pool = None                      # isci havuzu is gelince kurulur, bosta kalinca kapatilir (RAM)
        self._idle_since = None
        self._recoveries = 0
        self.apply_settings()

    # ------------------------------------------------------------------ ayarlar
    def _kind(self, key: str) -> str:
        k = key.split(":")[0]
        # cut: izler, cuz: zone dolgusu, via: via halkasi (bakir); viaf: maske acik via (kaplama); viab: via tupu
        return {"cut": "cu", "cuz": "cu", "via": "cu", "viaf": "finish", "viab": "barrel", "viabc": "cu"}.get(k, k)   # viabc: kapali via tupu (bakir)            # cut:<id> = o bakir katmaninin izleri (cu ile ayni malzeme/gorunurluk)

    def _make_material(self, key: str):
        c = self.cfg
        k = self._kind(key)
        if k == "cu":
            return _pick(_solid(gfx.MeshStandardMaterial(color=c.copper_color, roughness=0.36, metalness=0.9, env_map_intensity=2.0, side="both")))
        if k == "finish" or k == "barrel":      # plated delik ici (varil) = yuzey kaplama ile ayni renk/malzeme
            return _pick(_solid(gfx.MeshStandardMaterial(color=self.finish_color(), roughness=0.28, metalness=0.55, env_map_intensity=3.2, side="both")))
        if k == "drill":
            return gfx.MeshBasicMaterial(color=DRILL_COLOR, side="both")
        if k == "diel":
            # kapaklar koyu (maske altinda gorunur), yan duvarlar (kart kesiti) acik FR4 rengi: vertex rengi
            return gfx.MeshStandardMaterial(color_mode="vertex", roughness=0.85, metalness=0.0)
        if k == "mask":
            return self._mask_filter_material()
        return _solid(gfx.MeshStandardMaterial(color=c.silk_color, roughness=0.62, metalness=0.0, side="both"))

    def finish_color(self) -> str:
        """Acikta kalan bakirin yuzey kaplama rengi: kullanici secimi, yoksa kartin kaplama turu."""
        from .stackup import finish_color
        if self.cfg.pad_color:
            return self.cfg.pad_color
        return finish_color(self.stack.finish if self.stack is not None else "")

    # --- lehim maskesi: renk kaydirma (altindaki bakiri yesile boyar) ---------------
    def _filter_color(self):
        """Maske renginden coklu filtre rengi: beyaz ile mask_color*1.35 arasi, yogunluga gore."""
        r, g, b, _ = _hex(self.cfg.effective_mask_color())
        f = [min(1.0, v * 1.35) for v in (r, g, b)]
        d = self.cfg.mask_density
        return tuple(1.0 + (v - 1.0) * d for v in f)

    def _mask_filter_material(self):
        m = gfx.MeshBasicMaterial(color=self._filter_color())
        try:   # hedef rengi kaynakla CARP: altta ne varsa mask rengiyle filtrelenir
            m.alpha_config = {"mode": "blend", "method": "blended", "color_op": "add", "alpha_op": "add",
                              "color_src": "dst", "color_dst": "zero", "alpha_src": "zero", "alpha_dst": "one"}
            m.depth_write = False
        except Exception:
            m.opacity = 0.85
        return m

    def _mask_haze_material(self):
        """Maske rengi: yari saydam, isikla (mat) boyanan katman."""
        m = gfx.MeshStandardMaterial(color=self.cfg.effective_mask_color(), roughness=0.5, metalness=0.0, opacity=self.cfg.mask_haze)
        m.depth_write = False
        return m

    def _mask_gloss_material(self):
        """Parlak lake yansimasi: siyah taban + ortam yansimasi, mevcut goruntuye EKLENIR (additive)."""
        m = gfx.MeshStandardMaterial(color="#000000", roughness=0.16, metalness=0.0, env_map_intensity=3.0 * self.cfg.mask_gloss * self.cfg.env_intensity)
        try:
            m.alpha_config = {"mode": "blend", "method": "blended", "color_op": "add", "alpha_op": "add",
                              "color_src": "one", "color_dst": "one", "alpha_src": "zero", "alpha_dst": "one"}
        except Exception:
            m.opacity = 0.0
        m.depth_write = False
        return m

    def _dielectric_colors(self, normals: np.ndarray) -> np.ndarray:
        """Kapaklar: maske altindaki koyu dielektrik; yan duvarlar: kart kesiti FR4 rengi."""
        cap, edge = _hex(self.cfg.substrate_color), _hex(self.cfg.edge_color)
        col = np.tile(np.array(cap, np.float32), (len(normals), 1))
        col[np.abs(normals[:, 2]) < 0.5] = edge
        return col

    def apply_settings(self):
        c = self.cfg
        self.ambient.intensity = c.ambient_level * c.light_intensity
        self.sun.intensity = c.key_level * c.light_intensity
        self.fill.intensity = c.fill_level * c.light_intensity
        if hasattr(self.background.material, "set_colors"):
            self.background.material.set_colors(c.bg_top, c.bg_bottom)
        if self.stack is not None and not self._diel_merged():
            self._ensure_slabs()                   # katman katman gorunum gerekiyor (gizli katman / saydam govde)
        for key, m in self.layer_meshes.items():
            k = self._kind(key)
            base = key[:-4] if key.endswith(":dyn") else key
            for pre in ("cut:", "cuz:", "via:"):
                if base.startswith(pre):
                    base = "cu:" + base[len(pre):]
            if base.startswith("mask:") and base.count(":") == 2:
                base = base.rsplit(":", 1)[0]                # mask:top:t5 -> mask:top
            vis = c.visible(base)
            if k == "finish":
                side = key.split(":")[1]
                vis = c.show_pads and c.visible("cu:3" if side == "top" else "cu:34")
            elif k in ("drill", "barrel") or key.startswith("viab"):
                vis = c.show_pads
            elif key.startswith("diel:"):
                merged = self._diel_merged()
                vis = merged if key == "diel:all" else (not merged and c.visible(key))
                if self._ex and self.ex_hide_diel:
                    vis = False                              # exploded view: sag tik "Show Dielectric" kapali
            m.visible = vis
            mat = m.material
            if k == "cu":
                mat.color = c.copper_color
                mat.env_map_intensity = 2.0 * c.env_intensity
            elif k == "finish" or k == "barrel":
                mat.color = self.finish_color()
                mat.env_map_intensity = 3.2 * c.env_intensity
            elif k == "diel":
                op = c.substrate_opacity * (0.5 if self._ex else 1.0)    # exploded view: dielektrik ayarin yarisi kadar opak
                mat.opacity = op
                want = "solid" if op >= 0.999 else "blend"
                if getattr(mat, "alpha_mode", None) != want:
                    mat.alpha_mode = want
                ckey = (c.substrate_color, c.edge_color)
                if self._diel_key.get(key) != ckey:             # milyonlarca vertex: kaydirici hareketinde bosuna yeniden yukleme yok
                    self._diel_key[key] = ckey
                    geo = m.geometry
                    geo.colors.data[:] = self._dielectric_colors(geo.normals.data)
                    geo.colors.update_full()
            elif k == "mask":
                mat.color = self._filter_color()
                ex = self.mask_haze.get(key)
                if ex is not None:
                    tint, gloss = ex
                    tint.visible = gloss.visible = vis
                    tint.material.color = c.effective_mask_color()
                    tint.material.opacity = c.mask_haze
                    gloss.material.env_map_intensity = 3.0 * c.mask_gloss * c.env_intensity
            elif k == "silk":
                mat.color = c.silk_color
        for g in self.groups.values():
            vib = (round(c.model_saturation, 3), round(c.model_contrast, 3))
            for m in g.meshes:
                m.visible = c.show_comp_bottom if g.bottom else c.show_comp_top
                m.material.env_map_intensity = (1.2 if m is g.mesh_t else 0.8) * c.env_intensity
            if g.meshes and getattr(g, "vib", None) != vib and g.path in self.mesh_data:        # model rengi canli guncelle
                g.vib = vib
                col = self._vibrant(self.mesh_data[g.path].colors, vib[0], vib[1])
                for m in g.meshes:
                    m.geometry.colors.data[:] = col
                    m.geometry.colors.update_full()
        self._ensure_inner()
        if self._ex or self._tube_base:
            self._apply_explode()

    # ------------------------------------------------------------------ exploded view
    def set_explode(self, offs: dict | None):
        """offs: bakir layer_id -> ek z (mm), None/bos = normal gorunum. Geometri yeniden uretilmez: katman mesh'leri kaydirilir,
        via/pad tupleri (katmanlar arasi) z'de esnetilir, dielektrik levhalari iki bakirin arasini dolduracak sekilde z'de olceklenir."""
        was = bool(self._ex)
        self._ex = {k: float(v) for k, v in (offs or {}).items() if abs(v) > 1e-6}
        if bool(self._ex) != was:
            self.apply_settings()                  # tek govde <-> katman levhalari; apply_settings kaydirmayi da uygular
        else:
            self._apply_explode()

    def _ex_maps(self):
        cu = self.stack.copper()
        slab, above, pending = {}, None, []
        for l in self.stack.layers:                # ustten alta: her dielektrik, ustundeki ve altindaki bakirin arasini doldurur
            if l.kind == "copper":
                for d in pending:
                    slab[d.key] = (d, above, l)
                pending = []
                above = l
            elif l.kind == "dielectric":
                pending.append(l)
        return cu[0].layer_id, cu[-1].layer_id, slab

    def _ex_dz(self, key: str, maps) -> float:
        top, bot, slab = maps
        p = key.split(":")
        k = p[0]
        if len(p) > 1 and p[1].isdigit():
            if k in ("cu", "cut", "cuz", "via"):
                return self._ex.get(int(p[1]), 0.0)
        if len(p) > 1 and p[1] in ("top", "bottom"):
            return self._ex.get(top if p[1] == "top" else bot, 0.0)
        return 0.0

    def _apply_explode(self):
        if self.stack is None or not self.stack.copper():
            return
        maps = self._ex_maps()
        cu = self.stack.copper()
        zc = np.array([(l.z0 + l.z1) / 2 for l in cu])[::-1]                 # artan z
        oc = np.array([self._ex.get(l.layer_id, 0.0) for l in cu])[::-1]
        sig = tuple(np.round(oc, 5))
        for key, m in self.layer_meshes.items():
            if key.split(":")[0] in ("viab", "viabc", "barrel"):
                self._remap_tube(key, m, zc, oc, sig)
                continue
            ent = maps[2].get(key)
            if ent is not None and ent[1] is not None and ent[2] is not None:
                # dielektrik levha: ustteki bakirin altindan alttaki bakirin ustune kadar ESNER (z olcegi; geometri ayni)
                d, up, lo = ent
                top = up.z0 + self._ex.get(up.layer_id, 0.0)
                bot = lo.z1 + self._ex.get(lo.layer_id, 0.0)
                eps = min(0.04, max(0.0, (top - bot) - (d.z1 - d.z0)) * 0.1)    # bakir yuzeyiyle ayni duzlem olmasin (z-fighting)
                top, bot = top - eps, bot + eps
                sz =max(top - bot, 1e-6) / max(d.z1 - d.z0, 1e-9)
                m.local.scale = (1.0, 1.0, sz)
                m.local.position = (0.0, 0.0, bot - d.z0 * sz)
                continue
            pos = (0.0, 0.0, self._ex_dz(key, maps))
            m.local.position = pos
            for x in self.mask_haze.get(key, ()):
                x.local.position = pos
        top, bot, _ = maps
        for g in self.groups.values():
            pos = (0.0, 0.0, self._ex.get(bot if g.bottom else top, 0.0))
            for m in g.meshes:
                m.local.position = pos
        for key in [k for k in self._tube_base if k not in self.layer_meshes]:
            del self._tube_base[key]

    def _remap_tube(self, key, m, zc, oc, sig):
        """Tup: her vertex'in z'si, iki komsu bakir katmaninin ofsetleri arasinda dogrusal kaydirilir (tup esner)."""
        buf = m.geometry.positions
        ent = self._tube_base.get(key)
        if ent is None or ent[0] is not buf:
            if not self._ex:
                return
            ent = (buf, buf.data[:, 2].copy(), None)
        if ent[2] == sig:
            return
        z0 = ent[1]
        buf.data[:, 2] = z0 + np.interp(z0, zc, oc) if self._ex else z0
        buf.update_full()
        if self._ex:
            self._tube_base[key] = (buf, z0, sig)
        else:
            self._tube_base.pop(key, None)

    def layer_keys(self) -> list[str]:
        return list(self.layer_meshes)

    # ------------------------------------------------------------------ yukleme
    def load_snapshot(self, snap: BoardSnapshot):
        same_board = self._snap is not None and self._snap.name == snap.name
        self._snap = snap
        self.thickness = snap.thickness
        self.stack = snap.stack
        self.fps = {f.kiid: f for f in snap.footprints}
        poses = self._poses_of(snap)
        self._pending_plan = None
        if same_board:
            self._cancel_layers()           # ayni kart yeniden yuklenirken eski katmanlar yenileri gelene dek gorunur kalir
            self._batch, self._batch_poses = {}, poses
        else:
            self._clear_layers()
            self._batch = None
            self._base_fp = poses
            self._mask_gen += 1
            self._mask_shown = (self._mask_gen, ())          # ilk yukleme: maske taban konumlarla uretilir
        self._pad_clip = None
        poly = outline_to_polygon(snap.outline_lines)
        self.board_bounds = poly.bounds if poly is not None else None
        self._embedded = snap.embedded
        self._rebuild_groups(snap.project_dir)          # once modeller (cache'ten hizli gelir)
        self._submit_layers(snap)
        self.apply_settings()

    def _sub(self, fn, *args):
        """Isci havuzuna is gonder; havuz coktuyse (bellek yetersizligi) daha az iscili yenisini kur."""
        from concurrent.futures.process import BrokenProcessPool
        self._idle_since = None
        if self._pool is None:
            self._pool = make_pool(self._workers)
        try:
            return self._pool.submit(fn, *args)
        except BrokenProcessPool:
            self._new_pool()
            return self._pool.submit(fn, *args)

    def _sub_fast(self, fn, *args):
        """Canli kucuk isler hep AYNI isciye gider: o iscinin iz kirpma / delik / kontur onbellekleri sicak kalir (~30-100 ms)."""
        from concurrent.futures.process import BrokenProcessPool
        if self._fast_pool is None:
            self._fast_pool = make_pool(1)
        self._fast_idle = None
        try:
            return self._fast_pool.submit(fn, *args)
        except BrokenProcessPool:
            self._fast_pool = make_pool(1)
            return self._fast_pool.submit(fn, *args)

    def _warm_fast(self):
        """Tam derleme bitince hizli isciyi dis katman izleriyle isit (sonuc atilir): ilk canli iz duzenlemesi de hizli olsun."""
        snap = self._snap
        if snap is None or snap.stack is None or snap.copper is None or self._warm_key == (snap.data_path or id(snap.copper)):
            return
        self._warm_key = snap.data_path or id(snap.copper)
        cd = snap.data_path or snap.copper
        sdx = snap.data_path or snap.silk                     # maske katmani yazi/logo kesimleri de onceden (ilk tasima hizli olsun)
        key = snap.data_path or id(snap.silk)
        if sdx is not None and (self._mask_cuts is None or self._mask_cuts[0] != key):
            self._mask_cuts = (key, self._sub_fast(_cuts_worker, sdx))
        for l in snap.stack.copper():
            if l.side:
                self._warm_futs.append(self._sub_fast(_track_worker, cd, l.layer_id, l.z0, l.z1, snap.outline_lines, l.side))

    def _new_pool(self):
        self._workers = max(2, self._workers // 2)
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass
        self._pool = make_pool(self._workers)
        print(f"isci havuzu yenilendi: {self._workers} isci")

    def _recover_pool(self):
        """Isci havuzu cokerse (genelde bellek): havuzu kucultup bekleyen tum isleri yeniden gonder."""
        if self._recoveries >= 3:
            return
        self._recoveries += 1
        self._new_pool()
        self.loading.clear()
        self.layer_futures.clear()
        for g in self.groups.values():
            if g.path not in self.mesh_data and g.path not in self.loading:
                self.loading[g.path] = self._sub(_load_worker, str(g.path))
        if self._snap is not None:
            self._submit_layers(self._snap)

    def _cancel_layers(self):
        for f in self.layer_futures:
            f.cancel()
        self.layer_futures.clear()
        self._inner_fut.clear()
        self._inner = {k: v for k, v in self._inner.items() if v == "done"}

    def _inner_job(self, snap: BoardSnapshot, l):
        tent = self.cfg.tent_vias
        fut = self._sub(_cu_worker, snap.data_path or snap.copper, l.layer_id, l.z0, l.z1, l.side, snap.data_path or snap.silk, tent, snap.outline_lines)
        self._inner[l.layer_id] = "pending"
        self._inner_fut[fut] = l.layer_id
        return fut

    def _ensure_inner(self):
        """Ic bakir katmanlari yalniz gorunur olunca uretilir (varsayilan gizli): acilis suresi ve RAM belirgin duser."""
        snap = self._snap
        if snap is None or snap.copper is None or snap.stack is None:
            return
        for l in snap.stack.copper():
            if l.side or l.layer_id in self._inner:
                continue
            if self.cfg.visible(f"cu:{l.layer_id}"):
                self.layer_futures.append(self._inner_job(snap, l))

    def _prebuild_inner(self):
        """Bostayken gizli ic bakir katmanlarini arka planda TEK TEK hazirla: katman acilinca beklemeden gorunur, duzenlemelerde
        hizli yoldan (iz/zone isi) guncel tutulur. Gorunur katmanlarin isi yokken ve 3D kullanilirken calisir."""
        snap = self._snap
        if snap is None or snap.copper is None or snap.stack is None:
            return
        if any(v == "pending" for v in self._inner.values()):
            return
        for l in snap.stack.copper():
            if not l.side and l.layer_id not in self._inner:
                self.layer_futures.append(self._inner_job(snap, l))
                return

    def _drop_inner_meshes(self, lid: int):
        self._tri.pop(f"cu:{lid}", None)
        for k in (f"cu:{lid}", f"cut:{lid}", f"cuz:{lid}", f"cu:{lid}:dyn"):
            m = self.layer_meshes.pop(k, None)
            if m is not None:
                self.root.remove(m)
            self.layer_tags.pop(k, None)

    def update_tracks(self, snap: BoardSnapshot, layers):
        """Yalniz izler degisti: yalniz o katmanlarin iz mesh'lerini uret (zone/pad/maske/silk dokunulmaz)."""
        self._snap = snap
        zmap = {l.layer_id: l for l in snap.stack.copper()}
        for lid in layers:
            l = zmap.get(lid)
            if l is not None and (l.side or self._inner.get(lid) == "done"):
                self.layer_futures.append(self._sub(_track_worker, snap.data_path or snap.copper, lid, l.z0, l.z1, snap.outline_lines, l.side))

    def update_partial(self, snap: BoardSnapshot, plan: dict):
        """Yalniz plan'daki katmanlari yeniden uret (iz degisti -> o katmanin iz mesh'i; zone -> o katman; via/pad -> bakir + govde...).
        Bekleyen onceki kismi planla birlestirilir (iptal edilen isler kaybolmasin); sonuclar tek seferde uygulanir."""
        if plan.get("full") or snap.stack is None or snap.copper is None:
            return self.update_geometry(snap)
        if plan.get("stack"):
            self.stack = snap.stack                        # yuzey kaplama turu vb.: yalniz renk -> aninda
            if not any(plan.get(k) for k in ("cu", "tracks", "zones", "body", "body_tiles", "vias", "barrel", "silk", "pads")):
                self._snap = snap
                return                                     # yeniden uretilecek geometri yok: bekleyen isleri iptal etme
        prev = self._pending_plan or {"cu": set(), "tracks": set(), "zones": set(), "body": False, "body_tiles": set(), "vias": False,
                                      "barrel": False, "silk": False, "pads": False}
        m = {"cu": set(prev["cu"]) | set(plan["cu"]), "tracks": set(prev["tracks"]) | set(plan["tracks"]),
             "zones": set(prev.get("zones", ())) | set(plan.get("zones", ())),
             "track_data": {**prev.get("track_data", {}), **plan.get("track_data", {})},
             "zone_data": {**prev.get("zone_data", {}), **plan.get("zone_data", {})},
             "body_tiles": set(prev.get("body_tiles", ())) | set(plan.get("body_tiles", ()))}
        for k in ("body", "barrel", "silk", "pads", "vias"):
            m[k] = bool(prev.get(k)) or bool(plan.get(k))
        self._snap = snap
        self._cancel_layers()
        self._pending_plan = m
        self._batch = {}
        self._batch_poses = self._poses_of(snap) if m["pads"] else dict(self._base_fp)
        self._pad_clip = None
        cd = snap.data_path or snap.copper
        sd = snap.data_path or snap.silk
        st = snap.stack
        exp = self.cfg.mask_expansion if self.cfg.mask_expansion is not None else snap.mask_expansion
        tent = self.cfg.tent_vias
        jobs = []
        if m["body"]:
            jobs.append(self._sub(_body_worker, snap.outline_lines, st, cd, exp, tent, sd))
        elif m["body_tiles"]:                                   # yalniz dokunulan govde/maske karolari (~0.2 sn)
            cuts = self._mask_cuts[1] if self._mask_cuts is not None and not isinstance(self._mask_cuts[1], Future) else None
            jobs.append(self._sub(_body_worker, snap.outline_lines, st, cd, exp, tent, None if cuts is not None else sd,
                                       sorted(m["body_tiles"])) if cuts is None else
                        self._sub(_body_tiles_cuts, snap.outline_lines, st, cd, exp, tent, cuts, sorted(m["body_tiles"])))      # paralel: via isi hizli iscide
        if m["vias"]:
            jobs.append(self._sub_fast(_via_worker, cd, [(l.layer_id, l.z0, l.z1, l.side) for l in st.copper()],
                                       {l.layer_id: (l.z0, l.z1) for l in st.copper()}, tent))
        if m["silk"] and sd is not None:
            jobs.append(self._sub(_silk_worker, sd, st, snap.outline_lines))
        if m["barrel"]:
            jobs.append(self._sub(_extras_worker, cd, st))
        self.layer_futures = jobs
        for l in st.copper():
            lid = l.layer_id
            inner_ok = bool(l.side) or self._inner.get(lid) == "done"
            if lid in m["cu"]:
                if l.side:
                    self.layer_futures.append(self._sub(_cu_worker, cd, lid, l.z0, l.z1, l.side, sd, tent, snap.outline_lines))
                elif self.cfg.visible(f"cu:{lid}") or self._inner.get(lid) == "done":
                    self.layer_futures.append(self._inner_job(snap, l))      # gizli ama hazirlanmis ic katman da guncel tutulur
                else:
                    self._drop_inner_meshes(lid)
                    self._inner.pop(lid, None)
                continue
            if (lid in m["tracks"] or lid in m["zones"]) and not inner_ok:
                self._drop_inner_meshes(lid)                   # gizli ic katman: gorunur olunca taze uretilir
                self._inner.pop(lid, None)
                continue
            if lid in m["tracks"]:
                src = self._light_cd(snap, tracks={lid: m["track_data"][lid]}) if lid in m["track_data"] else cd
                self.layer_futures.append(self._sub_fast(_track_worker, src, lid, l.z0, l.z1, snap.outline_lines, l.side))
            if lid in m["zones"]:
                src = self._light_cd(snap, zones={lid: m["zone_data"][lid]}) if lid in m["zone_data"] else cd
                self.layer_futures.append(self._sub_fast(_zone_worker, src, lid, l.z0, l.z1, l.side, snap.outline_lines))

    def _light_cd(self, snap: BoardSnapshot, tracks=None, zones=None):
        """Iz/zone isi icin cok kucuk bakir verisi: pad'lerin yalniz delik bilgisi (poligonsuz) + via'lar + o katmanin izi/zone'u.
        Isci 12 MB'lik dosyayi okumadan ~ms icinde baslar."""
        base = getattr(self, "_holes_cd", None)
        if base is None or base[0] is not snap.copper:
            cd = snap.copper
            pads = [dataclasses.replace(p, front=None, back=None, inner=None) for p in cd.pads]
            self._holes_cd = (cd, dataclasses.replace(cd, pads=pads, tracks={}, zones={}))
        out = self._holes_cd[1]
        return dataclasses.replace(out, tracks={k: v for k, v in (tracks or {}).items() if v is not None},
                                   zones=dict(zones or {}))

    def update_geometry(self, snap: BoardSnapshot):
        """Bakir/silk/kontur degisti (footprint ve modellere dokunmaz): katmanlari arka planda yeniden uret, bitenleri yerinde degistir."""
        self._snap = snap
        poly = outline_to_polygon(snap.outline_lines)
        self.board_bounds = poly.bounds if poly is not None else self.board_bounds
        self._cancel_layers()
        self._pending_plan = None
        self._batch, self._batch_poses = {}, self._poses_of(snap)
        self._pad_clip = None
        self._submit_layers(snap)

    def _clear_layers(self):
        self._cancel_layers()
        for m in list(self.layer_meshes.values()) + [x for ex in self.mask_haze.values() for x in ex]:
            self.root.remove(m)
        self.layer_meshes.clear()
        self.mask_haze.clear()
        self.layer_tags.clear()
        self._tri.clear()
        self._dyn_sig = None
        self._tiles.clear(); self._tile_dirty.clear()
        self._slab_keys = []; self._slab_src = None

    def _submit_layers(self, snap: BoardSnapshot):
        if snap.copper is None or snap.stack is None:
            return
        st = snap.stack
        cd = snap.data_path or snap.copper          # dosya yolu: isci okur (ana surec buyuk pickle yapmaz)
        exp = self.cfg.mask_expansion if self.cfg.mask_expansion is not None else snap.mask_expansion
        sub = self._sub
        sd = snap.data_path or snap.silk
        jobs = [sub(_body_worker, snap.outline_lines, st, cd, exp, self.cfg.tent_vias, sd)]
        if sd is not None:
            jobs.append(sub(_silk_worker, sd, st, snap.outline_lines))
        outer = [l for l in st.copper() if l.side]
        inner = [l for l in st.copper() if not l.side]
        tent = self.cfg.tent_vias
        for l in outer:
            jobs.append(sub(_cu_worker, cd, l.layer_id, l.z0, l.z1, l.side, sd, tent, snap.outline_lines))
        jobs.append(sub(_extras_worker, cd, st))
        jobs.append(sub(_via_worker, cd, [(l.layer_id, l.z0, l.z1, l.side) for l in st.copper()],
                        {l.layer_id: (l.z0, l.z1) for l in st.copper()}, tent))
        self._inner.clear()
        self._inner_fut.clear()
        for l in inner:
            if self.cfg.visible(f"cu:{l.layer_id}"):
                jobs.append(self._inner_job(snap, l))
            else:
                self._drop_inner_meshes(l.layer_id)           # gizli ic katman eskimis olabilir: gorunur olunca taze uretilir
        self.layer_futures = jobs

    def rebuild_mask(self):
        """Mask genisletmesi / via tenting degisince yalniz govdeyi (maske+dielektrik) yeniden uret."""
        snap = self._snap
        if snap is None or snap.copper is None:
            return
        for k in [k for k in self.layer_meshes if k.startswith("mask:") or k.startswith("diel:")]:
            self.root.remove(self.layer_meshes.pop(k))
            for x in self.mask_haze.pop(k, ()):
                self.root.remove(x)
        exp = self.cfg.mask_expansion if self.cfg.mask_expansion is not None else snap.mask_expansion
        self.layer_futures.append(self._sub(_body_worker, snap.outline_lines, snap.stack, snap.data_path or snap.copper, exp, self.cfg.tent_vias, snap.data_path or snap.silk))
        self.layer_futures.append(self._sub(_via_worker, snap.data_path or snap.copper, [(l.layer_id, l.z0, l.z1, l.side) for l in snap.stack.copper()],
                                            {l.layer_id: (l.z0, l.z1) for l in snap.stack.copper()}, self.cfg.tent_vias))
        # via kaplama (tenting) degisimi dis katmanlarin yuzey kaplamasini da etkiler
        for l in (l for l in snap.stack.copper() if l.side):
            self.layer_futures.append(self._sub(_cu_worker, snap.data_path or snap.copper, l.layer_id, l.z0, l.z1, l.side, snap.data_path or snap.silk, self.cfg.tent_vias, snap.outline_lines))

    def _rebuild_groups(self, project_dir):
        for g in self.groups.values():
            for m in g.meshes:
                self.root.remove(m)
        self.groups.clear()
        self.missing.clear()
        for fp in self.fps.values():
            for mi, mref in enumerate(fp.models):
                path = resolve_model_path(mref.raw_path, project_dir, embedded=getattr(self, "_embedded", None))
                if path is None:
                    self.missing.add(mref.raw_path)
                    continue
                key = (path, fp.bottom)
                g = self.groups.get(key)
                if g is None:
                    g = self.groups[key] = ModelGroup(path, fp.bottom)
                    if path not in self.mesh_data and path not in self.loading:
                        self.loading[path] = self._sub(_load_worker, str(path))
                g.slot_of[(fp.kiid, mi)] = len(g.slots)
                g.slots.append((fp.kiid, mi))
                g.matrices.append(model_matrix(fp, mref, self.thickness))
        for g in self.groups.values():          # tam yenilemede onceden yuklenmis modeller aninda yeniden kurulur
            if g.path in self.mesh_data and not g.meshes:
                self._build_group_mesh(g)

    # ------------------------------------------------------------------ model gorunurlugu (ornek bazinda)
    _ZERO = np.diag([0.0, 0.0, 0.0, 1.0])               # sifir olcek: ornek gorunmez

    def _slot_matrix(self, g: ModelGroup, slot: int) -> np.ndarray:
        return self._ZERO if g.slots[slot] in self.hidden else g.matrices[slot]

    def model_index(self) -> list[dict]:
        """Arayuz agaci icin: model dosyasi -> ornekler [(kiid, model_index, referans, alt_yuz)]. Cozulemeyenler ayri."""
        by_path: dict[Path, list] = {}
        for g in self.groups.values():
            for (kiid, mi) in g.slots:
                fp = self.fps.get(kiid)
                by_path.setdefault(g.path, []).append((kiid, mi, fp.reference if fp else kiid[:8], g.bottom))
        out = [dict(name=p.name, path=str(p), items=sorted(v, key=lambda t: _natural(t[2]))) for p, v in by_path.items()]
        out.sort(key=lambda d: (-len(d["items"]), d["name"].lower()))
        return out

    def set_hidden(self, hidden: set):
        self.hidden = set(hidden)
        for g in self.groups.values():
            for m in g.meshes:
                for i in range(len(g.slots)):
                    m.set_matrix_at(i, self._slot_matrix(g, i))

    @staticmethod
    def _vibrant(colors_u8: np.ndarray, sat: float = 1.35, contrast: float = 1.12) -> np.ndarray:
        """Model renklerini canlandir: doygunluk + kontrast (gri/soluk STEP renkleri canli gorunsun)."""
        c = colors_u8.astype(np.float32) / 255.0
        rgb = c[:, :3]
        lum = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[:, None]
        rgb = lum + (rgb - lum) * sat                      # doygunluk
        rgb = (rgb - 0.5) * contrast + 0.5                 # kontrast
        c[:, :3] = np.clip(rgb, 0.0, 1.0)
        return c

    def _build_group_mesh(self, g: ModelGroup):
        d = self.mesh_data[g.path]
        col = self._vibrant(d.colors, self.cfg.model_saturation, self.cfg.model_contrast)
        g.vib = (round(self.cfg.model_saturation, 3), round(self.cfg.model_contrast, 3))
        # yari saydam ucgenler (STEP/WRL alfa < 1: LED lensi, cam) ayri mesh: alfa karisimli, derinlik yazmaz
        tri_a = d.colors[:, 3][d.indices].min(axis=1)
        trans = tri_a < 250
        for is_t in (False, True):
            sel = trans if is_t else ~trans
            if not sel.any():
                continue
            geo = gfx.Geometry(positions=d.positions, normals=d.normals, colors=col.copy(), indices=d.indices[sel])
            if is_t:
                mat = gfx.MeshStandardMaterial(color_mode="vertex", roughness=0.18, metalness=0.0, env_map_intensity=1.2, side="both")
                mat.alpha_mode = "blend"
                mat.depth_write = False
            else:
                # bilesen modelleri: ortam yansimasi kisik, aksi halde acik renkli plastikler patlar
                mat = _solid(gfx.MeshStandardMaterial(color_mode="vertex", roughness=0.58, metalness=0.04, env_map_intensity=0.8))
            m = gfx.InstancedMesh(geo, mat, max(1, len(g.slots)))
            if is_t:
                m.render_order = 5
            for i in range(len(g.matrices)):
                m.set_matrix_at(i, self._slot_matrix(g, i))
            self.root.add(m)
            if is_t:
                g.mesh_t = m
            else:
                g.mesh = m

    # ------------------------------------------------------------------ dongu
    _TILE = __import__("re").compile(r"^(diel|mask:top|mask:bottom):t(\d+)$")

    def _add_layer(self, key: str, mesh):
        """Govde/maske karolari tek tek cizilmez (100+ cizim cagrisi FPS'i dusuruyordu): karo sakla, sonra birlestir."""
        m = self._TILE.match(key)
        if m or key == "diel:walls":
            group = m.group(1) if m else "diel"
            tile = int(m.group(2)) if m else -1
            self._tiles.setdefault(group, {})[tile] = mesh
            self._tile_dirty.add(group)
            return
        self._add_layer_real(key, mesh)

    def _compose_tiles(self):
        """Degisen karo gruplarini tek mesh'e birlestir: diel:all, mask:top, mask:bottom (karo basina yeniden uretim korunur)."""
        if not self._tile_dirty:
            return
        from .prism import merge
        for group in sorted(self._tile_dirty):
            tiles = self._tiles.get(group, {})
            mesh = merge([tiles[k] for k in sorted(tiles)])
            self._add_layer_real("diel:all" if group == "diel" else group, mesh)
            if group == "diel":
                self._drop_slabs()
        self._tile_dirty.clear()

    # --- dielektrik: varsayilan TEK govde (hizli); bir katman gizlenince ya da govde saydamken katman katman levhalar ---------
    def _diel_merged(self) -> bool:
        c = self.cfg
        ds = [l.key for l in self.stack.layers if l.kind == "dielectric"] if self.stack is not None else []
        return all(c.visible(d) for d in ds) and c.substrate_opacity >= 0.999 and not self._ex

    def _drop_slabs(self):
        for k in list(getattr(self, "_slab_keys", ())):
            m = self.layer_meshes.pop(k, None)
            if m is not None:
                self.root.remove(m)
        self._slab_keys = []
        self._slab_src = None

    def _ensure_slabs(self):
        """Tek govdeden her dielektrik (core/prepreg) icin ayri levha: ayni ucgenler, z araligi o katmana olceklenir (ucgenleme yok)."""
        m = self.layer_meshes.get("diel:all")
        if m is None or self.stack is None or getattr(self, "_slab_src", None) is m:
            return
        self._drop_slabs()
        geo = m.geometry
        P = geo.positions.data
        N = geo.normals.data
        T = geo.indices.data
        G = self.layer_tags.get("diel:all")
        z0, z1 = float(P[:, 2].min()), float(P[:, 2].max())
        span = max(z1 - z0, 1e-9)
        keys = []
        for l in self.stack.layers:
            if l.kind != "dielectric":
                continue
            P2 = P.copy()
            P2[:, 2] = l.z0 + (P[:, 2] - z0) / span * (l.z1 - l.z0)
            self._add_layer_real(l.key, (P2, N, T, G if G is not None else np.zeros(len(P2), np.int32)))
            keys.append(l.key)
        self._slab_keys = keys
        self._slab_src = m

    def _add_layer_real(self, key: str, mesh):
        P, N, T, G = mesh
        self._diel_key.pop(key, None)
        if len(T) == 0:
            old = self.layer_meshes.pop(key, None)       # katman bosaldiysa eski mesh de kalkar
            if old is not None:
                self.root.remove(old)
            return
        old = self.layer_meshes.pop(key, None)
        if old is not None:
            self.root.remove(old)
        kw = {}
        if self._kind(key) == "diel":
            kw["colors"] = self._dielectric_colors(N)
        geo = gfx.Geometry(positions=P, normals=N, indices=T, **kw)
        m = gfx.Mesh(geo, self._make_material(key))
        if self._kind(key) == "mask":
            m.render_order = 10
            for x in self.mask_haze.pop(key, ()):
                self.root.remove(x)
            tint = gfx.Mesh(geo, self._mask_haze_material())       # ayni geometri: renk tonu (mat)
            gloss = gfx.Mesh(geo, self._mask_gloss_material())     # ayni geometri: lake yansimasi
            tint.render_order, gloss.render_order = 11, 12
            self.root.add(tint); self.root.add(gloss)
            self.mask_haze[key] = (tint, gloss)
        self.root.add(m)
        self.layer_meshes[key] = m
        self.layer_tags[key] = G
        if self._kind(key) in ("cu", "finish", "barrel") and not key.startswith(("cut:", "cuz:", "via:", "viaf:", "viab", "viabc")):
            self._tri[key] = (T, G)
            dyn = self.layer_meshes.pop(key + ":dyn", None)       # taban yenilendi: bu anahtarin gecici pad mesh'i artik gerekmez
            if dyn is not None:
                self.root.remove(dyn)
            self._tri_gen += 1

    def poll_loading(self) -> bool:
        changed = False
        for fut in list(self.layer_futures):
            if not fut.done():
                continue
            self.layer_futures.remove(fut)
            lid_inner = self._inner_fut.pop(fut, None)
            if lid_inner is not None:
                self._inner[lid_inner] = "done"                 # basarisiz olsa da: surekli yeniden denenmesin
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                from concurrent.futures.process import BrokenProcessPool
                if isinstance(e, BrokenProcessPool):
                    print("havuz coktu:", repr(e)[:200])
                    self._recover_pool()
                    return True
                import traceback
                print("katman hatasi:", e)
                traceback.print_exc()
                continue
            for key, mesh in res.items():
                if mesh is not None:
                    if self._batch is not None:
                        self._batch[key] = mesh
                    else:
                        self._add_layer(key, mesh)
            changed = True
        if self._poll_mask():
            changed = True
        if self._batch is not None and not self.layer_futures:      # ayni kart yenilemesi tamam: katmanlar tutarli, hepsi birden
            batch, self._batch = self._batch, None
            self._pending_plan = None
            # yenileme verisi cekildikten sonra footprint tasindiysa hizli maske zaten daha guncel: eski maskeyi uzerine yazma
            stale_mask = self._batch_poses != self._poses_now()
            for key, mesh in batch.items():
                if stale_mask and key.startswith("mask:"):
                    continue
                self._add_layer(key, mesh)
            self._base_fp = self._batch_poses
            if not stale_mask:
                self._mask_gen += 1
                self._mask_shown = (self._mask_gen, ())
                if any(k.startswith("mask:") for k in batch):
                    self._mask_tiles_live = set()
            else:
                self._mask_gen += 1                                # taban degisti: imza yeniden hesaplanir, hizli maske tekrar atilir
                self._mask_shown = None
            self._pad_sync_needed = True
            changed = True
        for path, fut in list(self.loading.items()):
            if not fut.done():
                continue
            del self.loading[path]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                from concurrent.futures.process import BrokenProcessPool
                if isinstance(e, BrokenProcessPool):
                    print("havuz coktu:", repr(e)[:200])
                    self._recover_pool()
                    return True
                print("model hatasi:", path.name, e)
                continue
            if res is None:
                print("model okunamadi:", path.name)
                continue
            self.mesh_data[path] = MeshData(*res)
            for g in self.groups.values():
                if g.path == path and not g.meshes:
                    self._build_group_mesh(g)
            changed = True
        if self._tile_dirty:
            self._compose_tiles()
            changed = True
        if self._pad_sync_needed:
            self._pad_sync_needed = False
            self._sync_pads()
        self._warm_futs = [f for f in self._warm_futs if not f.done()]
        if not self.layer_futures and self._batch is None and self.keep_pool:
            self._warm_fast()
            self._prebuild_inner()
        if changed:
            self.apply_settings()
        self.release_idle_pool()
        return changed

    def release_idle_pool(self, after: float = 8.0):
        """Is yokken (after sn) isci surecleri kapatilir: bosta her biri ~70 MB tutar. Sonraki is yeniden kurar."""
        import time
        if self._pool is None or self.pending():
            self._idle_since = None
            return
        now = time.monotonic()
        if self._idle_since is None:
            self._idle_since = now
        elif now - self._idle_since > (120.0 if self.keep_pool else after):
            try:
                self._pool.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
            self._pool = None
            self._idle_since = None

    def pending(self) -> int:
        return len(self.loading) + len(self.layer_futures)

    def apply_footprint_updates(self, updated: list[FootprintData]) -> bool:
        for fp in updated:
            old = self.fps.get(fp.kiid)
            if old is None or [m.raw_path for m in old.models] != [m.raw_path for m in fp.models] or old.bottom != fp.bottom:
                return False
        for fp in updated:
            self.fps[fp.kiid] = fp
            for mi, mref in enumerate(fp.models):
                g = next((g for g in self.groups.values() if (fp.kiid, mi) in g.slot_of and g.bottom == fp.bottom), None)
                if g is None:
                    continue
                slot = g.slot_of[(fp.kiid, mi)]
                m = model_matrix(fp, mref, self.thickness)
                g.matrices[slot] = m
                for gm in g.meshes:
                    gm.set_matrix_at(slot, self._slot_matrix(g, slot))
        try:
            self._sync_pads()
        except Exception as e:  # noqa: BLE001
            import traceback
            print("pad tasima hatasi:", e)
            traceback.print_exc()
        return True

    # ------------------------------------------------------------------ canli pad tasima (model gibi aninda)
    @staticmethod
    def _poses_of(snap: BoardSnapshot) -> dict:
        if snap.poses:
            return dict(snap.poses)
        return {f.kiid: (f.x, f.y, f.angle, f.bottom) for f in snap.footprints}

    def _moved_pads(self, dirty: list):
        """Tasinan footprint'lerin pad kayitlarini taban konumdan guncel konuma rijit donusturur (kayma + donme)."""
        import math
        cd = self._snap.copper
        index = getattr(self, "_pads_by_fp", None)
        if index is None or self._pads_by_fp_cd is not cd:
            index = {}
            for p in cd.pads:
                index.setdefault(p.fp, []).append(p)
            self._pads_by_fp, self._pads_by_fp_cd = index, cd
        out = []
        for kiid in dirty:
            x0, y0, a0, _ = self._base_fp[kiid]
            f = self.fps[kiid]
            d = math.radians(f.angle - a0)
            c, s = math.cos(d), math.sin(d)

            def mv(arr):
                if arr is None:
                    return None
                rel = arr - np.array([x0, y0])
                return np.c_[rel[:, 0] * c + rel[:, 1] * s, -rel[:, 0] * s + rel[:, 1] * c] + np.array([f.x, f.y])

            for p in index.get(kiid, ()):
                nx, ny = mv(np.array([[p.x, p.y]]))[0]
                out.append(dataclasses.replace(p, x=float(nx), y=float(ny), angle=p.angle + (f.angle - a0),
                                               front=mv(p.front), back=mv(p.back), inner=mv(p.inner)))
        return out

    def _dirty_list(self) -> list:
        """Taban mesh'lerin uretildigi konumdan farkli konuma tasinmis footprint'ler."""
        cd = self._snap.copper
        dirty = []
        for kiid, f in self.fps.items():
            b = self._base_fp.get(kiid)
            if b is None or b[3] != f.bottom or kiid not in cd.fp_index:
                continue
            if abs(f.x - b[0]) + abs(f.y - b[1]) > 1e-4 or abs((f.angle - b[2] + 180.0) % 360.0 - 180.0) > 1e-3:
                dirty.append(kiid)
        dirty.sort()
        return dirty

    def _poses_now(self) -> dict:
        return {k: (f.x, f.y, f.angle, f.bottom) for k, f in self.fps.items()}

    def _maybe_kick_mask(self, dirty: list):
        """Tasimadan sonra lehim maskesi acikliklarini hizla yenile: yalniz maske levhalari, tam yenilemeyi beklemeden (~1.5 sn)."""
        snap = self._snap
        if snap is None or snap.copper is None or snap.stack is None:
            return
        sig = (self._mask_gen, tuple((k, round(self.fps[k].x, 4), round(self.fps[k].y, 4), round(self.fps[k].angle, 3)) for k in dirty))
        if sig == self._mask_shown or sig == self._mask_sig:
            return
        if self._mask_fut is not None:
            return                                           # biri calisiyor: bitince guncel konumla yeniden denenir
        cd = snap.copper
        moved = {p.kiid: p for p in self._moved_pads(dirty)} if dirty else {}
        pads = [moved.get(p.kiid, p) if moved else p for p in cd.pads]
        small = dataclasses.replace(cd, pads=pads, tracks={}, zones={})          # isciye gidecek veri kucuk: yalniz pad + via
        # yalniz dokunulan maske karolari: tasinan pad'lerin eski (taban) ve yeni yerleri + daha once canli guncellenen karolar
        from .body import _pad_circle, tiles_for
        dset = set(dirty)
        pts = [_pad_circle(p) for p in cd.pads if p.fp in dset] + [_pad_circle(p) for p in moved.values()]
        tiles = tiles_for(self.board_bounds, pts) | self._mask_tiles_live if self.board_bounds else None
        # maske katmani yazi/logo cutout'lari: ana surecte DEGIL (0.3 sn takilma), bir isci bir kez hesaplar
        sdx = snap.data_path or snap.silk
        key = snap.data_path or id(snap.silk)
        cuts, sd = None, sdx
        mc = self._mask_cuts
        if mc is not None and mc[0] == key and not isinstance(mc[1], Future):
            cuts, sd = mc[1], None
        elif mc is not None and mc[0] == key and mc[1].done():
            try:
                cuts, sd = mc[1].result(), None
                self._mask_cuts = (key, cuts)
            except Exception:  # noqa: BLE001
                self._mask_cuts = None
        elif (mc is None or mc[0] != key) and sdx is not None:
            self._mask_cuts = (key, self._sub_fast(_cuts_worker, sdx))
        exp = self.cfg.mask_expansion if self.cfg.mask_expansion is not None else snap.mask_expansion
        self._mask_fut = self._sub_fast(_mask_worker, snap.outline_lines, snap.stack, small, exp, self.cfg.tent_vias, cuts, sd,
                                        sorted(tiles) if tiles is not None else None)
        if tiles:
            self._mask_tiles_live |= tiles
        self._mask_sig = sig

    def _poll_mask(self) -> bool:
        fut = self._mask_fut
        if fut is None or not fut.done():
            return False
        self._mask_fut = None
        sig, self._mask_sig = self._mask_sig, None
        try:
            res = fut.result()
        except Exception as e:  # noqa: BLE001
            print("maske hatasi:", e)
            return False
        if sig is None or sig[0] != self._mask_gen:
            return False                                      # arada taban yenilendi: eski sonuc gecersiz
        for key, mesh in res.items():
            if mesh is not None:
                self._add_layer(key, mesh)
        self._mask_shown = sig
        if self._snap is not None and self._snap.copper is not None:
            self._maybe_kick_mask(self._dirty_list())         # bu arada yeniden tasindiysa guncel konumla tekrar
        return True

    def _sync_pads(self):
        """Footprint tasininca pad bakiri / yuzey kaplamasi / tup (varil) taban mesh'lerden AYIKLANIR ve yeni konumda kucuk bir
        gecici mesh olarak cizilir: tasima modeller gibi aninda gorunur. Maske/dielektrik delikleri ve zone dolgusu, arka plandaki
        tam yenileme gelene dek eski yerinde kalir (birkac saniye)."""
        snap = self._snap
        if snap is None or snap.copper is None or snap.stack is None or not self._base_fp or not self._tri:
            return
        cd = snap.copper
        dirty = self._dirty_list()
        self._maybe_kick_mask(dirty)
        sig = (self._tri_gen, tuple((k, round(self.fps[k].x, 4), round(self.fps[k].y, 4), round(self.fps[k].angle, 3)) for k in dirty))
        if sig == self._dyn_sig:
            return
        self._dyn_sig = sig
        # onceki gecici mesh'leri kaldir
        for k in [k for k in self.layer_meshes if k.endswith(":dyn")]:
            self.root.remove(self.layer_meshes.pop(k))
        owners = np.array([cd.fp_index[k] for k in dirty], np.int64) if dirty else np.zeros(0, np.int64)
        for key, (T, G) in self._tri.items():              # taban mesh'lerde tasinan footprint'lerin ucgenlerini gizle / geri getir
            m = self.layer_meshes.get(key)
            if m is None:
                continue
            if len(owners):
                own = (G[T[:, 0]].astype(np.int64) >> 16) - 1
                keep = T[~np.isin(own, owners)]
            else:
                keep = T
            m.geometry.indices = gfx.Buffer(np.ascontiguousarray(keep, dtype=np.uint32))
        if not dirty:
            return
        from .copper import build_pad_dynamic, make_board_clip
        if self._pad_clip is None:
            self._pad_clip = make_board_clip(snap.outline_lines)
        layers = [(l.layer_id, l.z0, l.z1, l.side) for l in snap.stack.copper() if l.side or self._inner.get(l.layer_id) == "done"]
        zmap = {l.layer_id: (l.z0, l.z1) for l in snap.stack.copper()}
        parts = build_pad_dynamic(cd, self._moved_pads(dirty), layers, zmap, self._pad_clip)
        for key, mesh in parts.items():
            P, N, T2, G2 = mesh
            if len(T2) == 0:
                continue
            m = gfx.Mesh(gfx.Geometry(positions=P, normals=N, indices=T2), self._make_material(key))
            self.root.add(m)
            self.layer_meshes[key + ":dyn"] = m
            self.layer_tags[key + ":dyn"] = G2
        self.apply_settings()

    def close(self):
        if self._fast_pool is not None:
            self._fast_pool.shutdown(wait=False, cancel_futures=True)
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
