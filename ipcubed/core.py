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
        self._update_stats(w, h)
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
        if t == "pointer_leave":
            if self.cube.hover is not None:
                self.cube.hover = None
                self.request_draw()
            return
        if t == "pointer_move" and not self._drag:
            hov = self._cube_hit(e.x, e.y)
            if hov != self.cube.hover:
                self.cube.hover = hov
                self.request_draw()
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
