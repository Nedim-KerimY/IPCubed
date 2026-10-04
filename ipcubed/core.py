"""ViewerCore: sahne + kamera + giris + KiCad senkronu. Pencere sistemi (Qt) bilmez."""
from __future__ import annotations

import queue
import time

from . import compat  # noqa: F401
import pygfx as gfx

from .camera_rig import CameraRig
from . import statsoverlay
from .viewcube import S as CUBE_S, ViewCube, dir_angles, region as cube_region
from .scene_builder import ViewerScene
from .settings import Settings


class ViewerCore:
    def __init__(self, canvas, settings: Settings | None = None):
        from .sync import SyncThread

        self.cfg = settings or Settings.load()
        self.canvas = canvas
        self.vs = ViewerScene(self.cfg)
        self.renderer = gfx.WgpuRenderer(canvas)
        self._quality_scale = None                 # bostayken pixel_scale (SSAA); hareket ederken 1
        self._interact_t = 0.0
        self.camera = gfx.PerspectiveCamera(self.cfg.fov_3d, 1.6)
        self.rig = CameraRig(self.camera)
        self.rig.on_change = self.request_draw
        self.visible = False
        self.loaded = False
        self.status = "Connecting to KiCad..."
        self.q: queue.Queue = queue.Queue()
        self.sync = None                     # KiCad PCB duzenleyicisi belirince baslatilir
        self.board_name = ""
        self._drag = None
        self._last_pointer = (0, 0)
        self._need_draw = True
        self.on_loaded = lambda: None
        self.on_status = lambda s: None
        self.on_snapshot = lambda snap: None
        self.travel = 0.0
        self.renderer.add_event_handler(self._on_event, "pointer_down", "pointer_move", "pointer_up", "pointer_leave", "wheel")
        self._init_cube()
        self._init_stats()
        from .nethl import NetHighlighter
        self.hl = NetHighlighter(self.vs)
        self.picker = False                  # Net Highlighter modu (sag tik menusu)
        self._pick_pos = None                # bekleyen hover picking konumu
        self._shift = False
        self._hl2d = False                   # 2D'de KiCad vurgusu yapildi mi
        self.renderer.add_event_handler(self._on_key, "key_down", "key_up")
        self._init_explode()
        canvas.request_draw(self._draw)

    # ---------------------------------------------------------------- KiCad senkronu
    def start_sync(self):
        if self.sync is not None and self.sync.is_alive():
            return
        # KiCad IPC + protobuf cozumleme ayri SURECTE: GIL'i tutan bu is render karelerini takiltmasin
        from .sync_proc import SyncProcess
        self.sync = SyncProcess()
        self.q = self.sync.out
        self.sync.start()
        self.sync.visible = self.visible

    def stop_sync(self):
        if self.sync is not None:
            self.sync.stop()
            self.sync = None

    def set_polling_fast(self, fast: bool):
        if self.sync is not None:
            was = self.sync.visible
            self.sync.visible = fast
            self.vs.keep_pool = fast                   # 3D acikken isci havuzu sicak kalir: tasima sonrasi maske ~1.5 sn'de yenilenir
            if fast and not was:
                self.sync.check_now.set()          # 3D acilirken: gizliyken yapilan iz/bakir degisikliklerini hemen yakala

    def refresh_all(self):
        """Tam yenileme (footprint metni/silk gibi otomatik izlenmeyen degisiklikler icin)."""
        if self.sync is not None:
            self.sync.request_full.set()

    # ---------------------------------------------------------------- cizim
    def _draw(self):
        w, h = self.canvas.get_logical_size()
        if h > 0:
            self.rig.set_aspect(w / h)
        t0 = time.perf_counter()
        self.renderer.render(self.vs.scene, self.camera, flush=False)
        self.hl.render(self.renderer, self.camera, w, h)
        self._update_stats(w, h)
        self._update_ex_label(w, h)
        self._draw_cube(w, h)                 # kup + performans yazisi: tek bindirme gecisi
        self._record_frame(t0)

    # ---------------------------------------------------------------- performans yazisi (sag alt)
    def _init_stats(self):
        import collections
        import numpy as np
        self.stats = statsoverlay.StatsOverlay()
        self._sampler = None
        self._frames = collections.deque(maxlen=512)
        self._frame_ms = 0.0
        self._stats_text = None
        self._stats_t = 0.0
        self._stats_forced = False
        self._stats_tex = gfx.Texture(np.zeros((statsoverlay.H, statsoverlay.W, 4), np.uint8), dim=2)
        mat = gfx.MeshBasicMaterial(map=self._stats_tex)
        mat.alpha_mode = "blend"
        self._stats_quad = gfx.Mesh(gfx.plane_geometry(statsoverlay.W, statsoverlay.H), mat)
        self._stats_quad.visible = False
        self._cube_scene.add(self._stats_quad)
        if self.cfg.show_stats:
            self._start_sampler()

    def _start_sampler(self):
        if self._sampler is None:
            self._sampler = statsoverlay.StatsSampler()
            self._sampler.start()

    def toggle_stats(self, on=None):
        self.cfg.show_stats = (not self.cfg.show_stats) if on is None else bool(on)
        self.cfg.save()
        if self.cfg.show_stats:
            self._start_sampler()
        elif self._sampler is not None:
            self._sampler.stop()
            self._sampler = None
        self._stats_text = None
        self.request_draw()

    def _record_frame(self, t0):
        now = time.perf_counter()
        forced, self._stats_forced = self._stats_forced, False
        if not forced:                                  # yalniz gercek cizimler FPS'e sayilir (yazi tazeleme cizimleri sayilmaz)
            self._frames.append(now)
            ms = (now - t0) * 1000.0
            self._frame_ms = ms if self._frame_ms == 0 else 0.8 * self._frame_ms + 0.2 * ms

    def _update_stats(self, w, h):
        now = time.perf_counter()
        on = self.cfg.show_stats and self._sampler is not None
        self._stats_quad.visible = on
        if not on:
            return
        while self._frames and now - self._frames[0] > 1.0:
            self._frames.popleft()
        fps = float(len(self._frames)) if self._frames else 0.0
        text = self.stats.text(fps if len(self._frames) > 1 else 0.0, self._frame_ms, self._sampler)
        try:
            ratio = float(self.canvas.get_pixel_ratio())
        except Exception:  # noqa: BLE001
            ratio = 1.0
        if (text, ratio) != self._stats_text:
            self._stats_text = (text, ratio)
            arr = self.stats.render(text, ratio)
            if arr.shape != self._stats_tex.data.shape:
                self._stats_tex = gfx.Texture(arr, dim=2)
                self._stats_quad.material.map = self._stats_tex
            else:
                self._stats_tex.data[:] = arr
                self._stats_tex.update_full()
        self._stats_quad.local.position = (w - statsoverlay.MARGIN - statsoverlay.W / 2, statsoverlay.MARGIN + statsoverlay.H / 2, 0)

    # ---------------------------------------------------------------- ViewCube (sag ust)
    def _init_cube(self):
        import numpy as np
        self.cube = ViewCube()
        self._cube_key = None
        self._cube_press = None
        self.on_cube_toggled = lambda v: None
        self._cube_tex = gfx.Texture(np.zeros((CUBE_S, CUBE_S, 4), np.uint8), dim=2)
        mat = gfx.MeshBasicMaterial(map=self._cube_tex)
        mat.alpha_mode = "blend"
        self._cube_quad = gfx.Mesh(gfx.plane_geometry(CUBE_S, CUBE_S), mat)
        self._cube_scene = gfx.Scene()
        self._cube_scene.add(self._cube_quad)
        self._cube_cam = gfx.ScreenCoordsCamera()

    def _draw_cube(self, w, h):
        x0, y0 = cube_region(w, h)
        self._cube_quad.local.position = (x0 + CUBE_S / 2, h - y0 - CUBE_S / 2, 0)      # ScreenCoordsCamera: y yukari
        s = self.rig.s
        vis = self.cfg.show_view_cube
        try:
            ratio = float(self.canvas.get_pixel_ratio())      # yuksek DPI'da doku da buyur: keskin kup
        except Exception:  # noqa: BLE001
            ratio = 1.0
        key = (round(s.yaw, 1), round(s.pitch, 1), self.cube.hover, vis, ratio)
        if key != self._cube_key:
            self._cube_key = key
            arr = self.cube.render(s.yaw, min(s.pitch, 90.0), vis, ratio)
            if arr.shape != self._cube_tex.data.shape:
                self._cube_tex = gfx.Texture(arr, dim=2)
                self._cube_quad.material.map = self._cube_tex
            else:
                self._cube_tex.data[:] = arr
                self._cube_tex.update_full()
        self.renderer.render(self._cube_scene, self._cube_cam)

    def _cube_hit(self, ex, ey):
        w, h = self.canvas.get_logical_size()
        x0, y0 = cube_region(w, h)
        x, y = ex - x0, ey - y0
        if not (0 <= x <= CUBE_S and 0 <= y <= CUBE_S):
            return None
        s = self.rig.s
        return self.cube.hit(x, y, s.yaw, min(s.pitch, 90.0), self.cfg.show_view_cube)

    def toggle_cube(self, on=None):
        self.cfg.show_view_cube = (not self.cfg.show_view_cube) if on is None else bool(on)
        self.cfg.save()
        self.on_cube_toggled(self.cfg.show_view_cube)
        self.request_draw()

    def _cube_action(self, hit):
        if hit == "toggle":
            self.toggle_cube()
        elif hit == "home":
            self.rig.go("3d", self.cfg.anim_ms)
        elif isinstance(hit, tuple) and hit[0] == "dir":
            yaw, pitch = dir_angles(hit[1])                # yuz / kenar / kose: o yone bak
            self.rig.goto(yaw, pitch, 450)

    def _interacting(self):
        """Dondurme/kaydirma/yakinlastirma/animasyon: dahili cozunurlugu ekrana esitle (SSAA 4x piksel maliyeti yok).
        Kenar yumusatma ppaa ile surer; hareket bitince 250 ms sonra SSAA ile yeniden cizilir."""
        if self._quality_scale is None:
            self._quality_scale = self.renderer.pixel_scale
        self._interact_t = time.perf_counter()
        if self.renderer.pixel_scale != 1:
            self.renderer.pixel_scale = 1

    def request_draw(self):
        self._need_draw = True

    # ---------------------------------------------------------------- girdi
    def _on_event(self, e):
        if e.type in ("pointer_move", "wheel") and (self._drag or e.type == "wheel"):
            self._interacting()
        t = e.type
        w, h = self.canvas.get_logical_size()
        if t == "pointer_move":
            self._last_pointer = (e.x, e.y)
        if t == "pointer_leave":
            if self.hl.hover:
                self.hl.hover = set()
                self.request_draw()
            if self.cube.hover is not None:
                self.cube.hover = None
                self.request_draw()
            return
        if t in ("pointer_move", "pointer_down", "pointer_up"):
            self._shift = "Shift" in tuple(e.modifiers)
        if t == "pointer_move" and not self._drag:
            if self.picking():
                self._pick_pos = (e.x, e.y)
            elif self.hl.hover:
                self.hl.hover = set()
                self.request_draw()
            hov = self._cube_hit(e.x, e.y)
            if hov != self.cube.hover:
                self.cube.hover = hov
                self.request_draw()
        if self._ex_event(e):
            return
        if t == "pointer_down":
            hit = self._cube_hit(e.x, e.y) if e.button == 1 else None
            if hit is not None:
                self._cube_press = hit          # kup uzerinde tik: eylem pointer_up'ta, surukleme baslamaz
                return
            self._drag = (e.button, e.x, e.y, tuple(e.modifiers))
            self.travel = 0.0
        elif t == "pointer_up":
            if self._cube_press is not None:
                hit = self._cube_hit(e.x, e.y)
                if hit == self._cube_press:
                    self._cube_action(hit)
                self._cube_press = None
                return
            if self._drag and self._drag[0] == 1 and self.travel <= 4 and self.picking():
                self._pick_click(e.x, e.y, "Shift" in tuple(e.modifiers))
            self._drag = None
        elif t == "pointer_move" and self._drag:
            btn, lx, ly, mods = self._drag
            dx, dy = e.x - lx, e.y - ly
            self.travel += abs(dx) + abs(dy)            # sag tik menusu: surukleme mi tik mi ayirt etmek icin
            self._drag = (btn, e.x, e.y, mods)
            if btn == 2:                       # sag tus: don, Shift: kaydir, Ctrl: yakinlastir
                if "Shift" in mods:
                    self.rig.pan(dx, dy, h)
                elif "Control" in mods:
                    self.rig.zoom(1.0 - dy * 0.005)
                else:
                    self.rig.rotate(dx, dy)
            elif btn == 3 or (btn == 1 and "Shift" in mods):   # orta tus: kaydir
                self.rig.pan(dx, dy, h)
            elif btn == 1:
                self.rig.rotate(dx, dy)
        elif t == "wheel":
            nx = (e.x / max(w, 1)) * 2 - 1
            ny = 1 - (e.y / max(h, 1)) * 2
            self.rig.zoom(0.88 if e.dy < 0 else 1 / 0.88, nx, ny)

    # ---------------------------------------------------------------- Net Highlighter
    def picking(self) -> bool:
        """Fare altindaki net yanip soner mi: menuden acilan mod ya da secim varken Shift basili."""
        return self.picker or (bool(self.hl.selected) and self._shift)

    def start_picker(self):
        self.picker = True
        self._pick_pos = self._last_pointer
        self.request_draw()

    def stop_highlight(self):
        self.picker = False
        self.hl.clear()
        self._pick_pos = None
        if self._hl2d:
            self.clear_2d()
        self.request_draw()

    def highlight_active(self) -> bool:
        return self.picker or bool(self.hl.selected)

    def net_names(self) -> list:
        snap = self.vs._snap
        return list(getattr(getattr(snap, "copper", None), "net_names", None) or [])

    def with_pair(self, nid: int) -> set:
        """Diff pair ise esi de (KiCad kurali: ad sonu +/- ya da P/N)."""
        names = self.net_names()
        out = {nid}
        if not (0 < nid < len(names)):
            return out
        from .nethl import pair_name
        other = pair_name(names[nid])
        if other:
            try:
                out.add(names.index(other))
            except ValueError:
                pass
        return out

    def _pick_net(self, x, y):
        try:
            info = self.renderer.get_pick_info((x, y))
        except Exception:  # noqa: BLE001
            return None
        return self.hl.net_at(info)

    def _pick_click(self, x, y, shift: bool):
        nid = self._pick_net(x, y)
        if nid is None:
            return
        nets = self.with_pair(nid)
        if shift:
            if nets <= self.hl.selected:
                self.hl.selected = self.hl.selected - nets
            else:
                self.hl.selected = self.hl.selected | nets
        else:
            self.hl.selected = set(nets)
            self.picker = False
            self.hl.hover = set()
        if not self.hl.selected and not self.picker:
            self.stop_highlight()
        self.request_draw()

    def _on_key(self, e):
        if e.key == "Shift":
            self._shift = e.type == "key_down"
            if self._shift and self.picking():
                self._pick_pos = self._last_pointer
            elif not self.picking() and self.hl.hover:
                self.hl.hover = set()
            self.request_draw()

    def select_nets(self, nets):
        """Test/kontrol: netleri dogrudan sec (diff pair esi dahil)."""
        sel = set()
        for n in nets:
            sel |= self.with_pair(int(n))
        self.hl.selected = sel
        self.request_draw()

    def highlight_2d(self):
        names = self.net_names()
        sel = [names[n] for n in sorted(self.hl.selected) if 0 < n < len(names)]
        if sel and self.sync is not None:
            self.sync._send(("hl2d", sel))
            self._hl2d = True

    def clear_2d(self):
        if self.sync is not None:
            self.sync._send(("hlclear",))
        self._hl2d = False

    # ---------------------------------------------------------------- Exploded board view
    EX_MS = 600

    def _init_explode(self):
        import numpy as np
        from .exploder import ExploderGizmo
        self.ex = ExploderGizmo()
        self.ex.group.visible = False
        self.vs.scene.add(self.ex.group)
        self.exploded = False
        self._ex_t = 0.0                     # 0 = normal, 1 = tam patlatilmis (animasyon)
        self._ex_anim = None                 # (baslangic zamani, baslangic t, hedef t)
        self._ex_off = None                  # bakir katmani basina (ustten alta) hedef ek z (mm); en alt = 0
        self._ex_sig = None                  # gizmo hangi stackup/karta gore kuruldu
        self._ex_flags = None
        self._ex_drag = None
        self._ex_hover_pos = None
        self._ex_dirty = False
        self.on_layers_changed = lambda key: None
        self._ex_label_key = None
        self._ex_label_tex = gfx.Texture(np.zeros((4, 4, 4), np.uint8), dim=2)
        mat = gfx.MeshBasicMaterial(map=self._ex_label_tex)
        mat.alpha_mode = "blend"
        self._ex_label = gfx.Mesh(gfx.plane_geometry(1, 1), mat)
        self._ex_label.visible = False
        self._cube_scene.add(self._ex_label)

    def _ex_layers(self):
        st = self.vs.stack
        return st.copper() if st is not None else []

    def toggle_explode(self, on=None):
        import math
        import numpy as np
        on = (not self.exploded) if on is None else bool(on)
        cu = self._ex_layers()
        if not cu or not self.vs.board_bounds:
            return
        n = len(cu)
        if on and (self._ex_off is None or len(self._ex_off) != n):
            b = self.vs.board_bounds
            gap = min(8.0, max(2.0, math.hypot(b[2] - b[0], b[3] - b[1]) * 0.025))
            self._ex_off = np.array([(n - 1 - i) * gap for i in range(n)], float)
        self.exploded = on
        self._ex_anim = (time.perf_counter(), self._ex_t, 1.0 if on else 0.0)
        self.request_draw()

    def _ex_build(self):
        """Gizmo: kartin sag alt kosesinde, her bakir katman icin bir kup (stackup / kart degisince yeniden)."""
        import math
        cu = self._ex_layers()
        b = self.vs.board_bounds
        sig = (tuple(l.layer_id for l in cu), tuple(round(v, 3) for v in b) if b else None)
        if sig == self._ex_sig or not cu or not b:
            return
        self._ex_sig = sig
        self.ex.build([(l.key, l.name, self.cfg.visible(l.key)) for l in cu], (0.0, 0.0), math.hypot(b[2] - b[0], b[3] - b[1]))
        s = self.ex.size
        self.ex.corner = (b[2] + 1.6 * s, b[1] + 1.6 * s)          # sag alt kosenin hemen disi
        self._ex_flags = None
        if self._ex_off is not None and len(self._ex_off) != len(cu):
            self._ex_off = None
            self.exploded = False
            self._ex_t = 0.0

    def _ex_current(self):
        """Uygulanan ofsetler (animasyon egrisiyle)."""
        u = self._ex_t
        e = u * u * (3 - 2 * u)
        return self._ex_off * e if self._ex_off is not None else None

    def _ex_apply(self):
        cu = self._ex_layers()
        off = self._ex_current()
        if off is None or not cu:
            self.vs.set_explode(None)
            self.ex.group.visible = False
            return
        on = self._ex_t > 1e-4
        self.vs.set_explode({l.layer_id: float(off[i]) for i, l in enumerate(cu)} if on else None)
        self.ex.place([(l.z0 + l.z1) / 2 + float(off[i]) for i, l in enumerate(cu)])
        self.ex.group.visible = on

    def _ex_tick(self) -> bool:
        if self.vs.stack is None:
            return False
        dirty = False
        if self._ex_sig is None or self.exploded or self._ex_t > 0:
            before = self._ex_sig
            self._ex_build()
            if self._ex_sig != before:
                self._ex_dirty = True
        if self._ex_anim is not None:
            t0, a, b = self._ex_anim
            u = min(1.0, (time.perf_counter() - t0) * 1000.0 / self.EX_MS)
            self._ex_t = a + (b - a) * u
            if u >= 1.0:
                self._ex_anim = None
            self._ex_dirty = True
            self._interacting()
        if self._ex_dirty:
            self._ex_dirty = False
            self._ex_apply()
            dirty = True
        if self.ex.group.visible:
            flags = [self.cfg.visible(l.key) for l in self._ex_layers()]
            if flags != self._ex_flags:
                self._ex_flags = flags
                self.ex.set_visible_flags(flags)
                dirty = True
            if self._ex_hover_pos is not None and self._ex_drag is None:
                pos, self._ex_hover_pos = self._ex_hover_pos, None
                if self.ex.set_hover(self._ex_pick(*pos)):
                    dirty = True
        elif self.ex.hover is not None:
            self.ex.set_hover(None)
        return dirty

    def _ex_pick(self, x, y):
        try:
            info = self.renderer.get_pick_info((x, y))
        except Exception:  # noqa: BLE001
            return None
        return self.ex.hit_object(info.get("world_object"))

    def _to_screen(self, p):
        import numpy as np
        w, h = self.canvas.get_logical_size()
        v = self.camera.camera_matrix @ np.array([p[0], p[1], p[2], 1.0])
        if abs(v[3]) < 1e-9:
            return None
        n = v[:3] / v[3]
        return np.array([(n[0] + 1) / 2 * w, (1 - n[1]) / 2 * h])

    def _ex_event(self, e) -> bool:
        """Gizmo surukleme / tik. True: olay gizmoya ait (kamera hareket etmez)."""
        import numpy as np
        t = e.type
        if not self.ex.group.visible and self._ex_drag is None:
            return False
        if t == "pointer_move" and self._ex_drag is None:
            self._ex_hover_pos = (e.x, e.y)
            return False
        if t == "pointer_down" and e.button == 1:
            hit = self._ex_pick(e.x, e.y)
            if hit is None:
                return False
            self._ex_drag = {"hit": hit, "x": e.x, "y": e.y, "start": self._ex_off.copy(), "moved": False}
            self.ex.press = hit
            return True
        d = self._ex_drag
        if d is None:
            return False
        if t == "pointer_move":
            dx, dy = e.x - d["x"], e.y - d["y"]
            if abs(dx) + abs(dy) > 3:
                d["moved"] = True
            if not d["moved"]:
                return True
            cu = self._ex_layers()
            i = d["hit"][1]
            n = len(cu)
            z = (cu[i].z0 + cu[i].z1) / 2 + float(self._ex_current()[i])
            c = self.ex.corner
            s0, s1 = self._to_screen((c[0], c[1], z)), self._to_screen((c[0], c[1], z + 1.0))
            if s0 is None or s1 is None:
                return True
            a = s1 - s0                                   # 1 mm yukari = ekranda a piksel
            dz = float(np.dot((dx, dy), a) / max(np.dot(a, a), 1e-9))
            start = d["start"]
            off = start.copy()
            if "Shift" in tuple(e.modifiers):             # tum araliklar esit
                ref = i if i < n - 1 else 0
                g = max(0.0, (start[ref] + dz) / (n - 1 - ref)) if n > 1 else 0.0
                off = np.array([(n - 1 - j) * g for j in range(n)], float)
            elif i < n - 1:                               # en alt (B.Cu) sabit; katmanlar birbirinin icinden gecmez
                hi = off[i - 1] if i > 0 else np.inf
                off[i] = float(np.clip(start[i] + dz, off[i + 1], hi))
            self._ex_off = off
            self._ex_t = 1.0
            self._ex_anim = None
            self._ex_dirty = True
            self._interacting()
            return True
        if t == "pointer_up":
            self._ex_drag = None
            self.ex.press = None
            if not d["moved"] and d["hit"][0] == "small":
                cu = self._ex_layers()
                key = cu[d["hit"][1]].key
                self.cfg.layer_visible[key] = not self.cfg.visible(key)
                self.vs.apply_settings()
                self.on_layers_changed(key)
            self.request_draw()
            return True
        return False

    def _update_ex_label(self, w, h):
        """Fare altindaki katman kupunun adi (kupun solunda, ekran koordinatli)."""
        hov = self.ex.hover if self.ex.group.visible else None
        cu = self._ex_layers()
        if hov is None or hov[1] >= len(cu):
            self._ex_label.visible = False
            return
        i = hov[1]
        try:
            ratio = float(self.canvas.get_pixel_ratio())
        except Exception:  # noqa: BLE001
            ratio = 1.0
        key = (cu[i].name, ratio)
        if key != self._ex_label_key:
            from .exploder import label_image
            self._ex_label_key = key
            arr = label_image(cu[i].name, ratio)
            self._ex_label_tex = gfx.Texture(arr, dim=2)
            self._ex_label.material.map = self._ex_label_tex
            self._ex_label_size = (arr.shape[1] / ratio, arr.shape[0] / ratio)
        off = self._ex_current()
        c = self.ex.corner
        p = self._to_screen((c[0], c[1], (cu[i].z0 + cu[i].z1) / 2 + float(off[i])))
        if p is None:
            self._ex_label.visible = False
            return
        lw, lh = self._ex_label_size
        x = p[0] - 22 - lw / 2
        self._ex_label.local.scale = (lw, lh, 1)
        self._ex_label.local.position = (x, h - p[1], 0)
        self._ex_label.visible = True

    # ---------------------------------------------------------------- mod gecisi
    def enter_3d(self, animate: bool = True):
        self.visible = True
        if animate and self.cfg.anim_ms > 0:
            self.rig.set_start_2d()
            self.rig.go("3d", self.cfg.anim_ms)
        else:
            self.rig.go("3d", immediate=True)
        self.request_draw()

    def leave_3d(self):
        """2D'ye animasyonla don; animasyon bitince on_hidden cagrilir."""
        self.rig.go("2d", self.cfg.anim_ms)
        self.request_draw()

    # ---------------------------------------------------------------- zaman adimi
    def tick(self):
        """~60 Hz cagrilir (Qt QTimer)."""
        dirty = self.vs.poll_loading()
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "moved":
                if self.vs.apply_footprint_updates(payload):
                    dirty = True
                elif self.sync is not None:
                    self.sync.request_full.set()
            elif kind == "tracks":
                self.vs.update_tracks(*payload)
                dirty = True
            elif kind == "partial":
                self.vs.update_partial(*payload)
                if payload[1].get("stack"):
                    self.vs.apply_settings()                # yeni kaplama rengi hemen
                    self.on_snapshot(payload[0])            # panel: stackup listesi + kaplama turu
                dirty = True
            elif kind == "geom":
                self.vs.update_geometry(payload)
                dirty = True
            elif kind == "full":
                if payload.name != self.board_name or not self.loaded:
                    self._framed = False             # yalniz yeni kartta kamerayi yeniden cerceve (ayni kart yenilenirse gorunum korunur)
                self.vs.load_snapshot(payload)
                self.board_name = payload.name
                self.on_snapshot(payload)
                dirty = True
                self.status = f"{len(payload.footprints)} footprint"
            elif kind == "status":
                self.status = payload
                self.on_status(payload)
        if not getattr(self, "_framed", False) and self.vs.board_bounds:
            self.rig.set_aspect(max(0.1, self.canvas.get_logical_size()[0] / max(1, self.canvas.get_logical_size()[1])))
            self.rig.frame(self.vs.board_bounds, self.vs.thickness, self.cfg)
            self._framed = True
            if not self.loaded:
                self.loaded = True
                self.on_loaded()
            dirty = True
        if self.rig.tick():
            dirty = True
            self._interacting()
        if self._pick_pos is not None:
            pos, self._pick_pos = self._pick_pos, None
            if self.picking() and self.visible:
                nid = self._pick_net(*pos)
                hov = self.with_pair(nid) if nid is not None else set()
                if hov != self.hl.hover:
                    self.hl.hover = hov
                    dirty = True
        if self._ex_tick():
            dirty = True
        if self.hl.pulsing() and self.visible:
            dirty = True                                   # yanip sonme: surekli ciz
        if self._quality_scale is not None and self.renderer.pixel_scale != self._quality_scale \
                and time.perf_counter() - self._interact_t > 0.25:
            self.renderer.pixel_scale = self._quality_scale     # durdu: tam kalite (SSAA) ile bir kez daha ciz
            dirty = True
        if self.cfg.show_stats and self.visible and time.perf_counter() - self._stats_t > 0.5:
            self._stats_t = time.perf_counter()
            self._stats_forced = True                      # yaziyi tazelemek icin (FPS'e sayilmaz) nadiren yeniden ciz
            dirty = True
        if dirty or self._need_draw:
            self._need_draw = False
            if self.visible:
                self.canvas.request_draw()

    def close(self):
        if getattr(self, "_sampler", None) is not None:
            self._sampler.stop()
        self.stop_sync()
        self.vs.close()
        self.cfg.save()
