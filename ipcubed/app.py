"""Pencere, kamera ve canli senkronizasyon dongusu."""
from __future__ import annotations

import queue
import threading
import time

from . import compat  # noqa: F401
import numpy as np
import pygfx as gfx

from .kicad_source import KiCadSource
from .scene_builder import ViewerScene


from .log import _log  # noqa: E402,F401  (geriye uyum: eski 'from .app import _log')
from .sync import SyncThread  # noqa: E402,F401


_VIEWS = {  # ad -> (bakis yonu, yukari vektoru)
    "iso": ((0, 0.45, -0.89), (0, 0, 1)),
    "top": ((0, 0, -1), (0, 1, 0)),
    "bottom": ((0, 0, 1), (0, 1, 0)),
}


def _frame_board(camera, vs: ViewerScene, controller=None, view: str = "iso"):
    b = vs.board_bounds or (0, 0, 100, 100)
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    radius = 0.5 * float(np.hypot(b[2] - b[0], b[3] - b[1])) * (0.85 if view == "iso" else 0.75)
    vdir, up = _VIEWS[view]
    camera.show_object((cx, cy, vs.thickness / 2, radius), view_dir=vdir, up=up)


def run(args):
    src = KiCadSource()
    t0 = time.perf_counter()
    snap = src.snapshot()
    print(f"snapshot: {len(snap.footprints)} footprint, {(time.perf_counter()-t0):.2f}s")

    from .settings import MASK_PRESETS, STYLES, Settings
    cfg = Settings()
    if getattr(args, "style", None):
        for k, v in STYLES[args.style].items():
            setattr(cfg, k, v)
    if getattr(args, "mask", None):
        for k, v in MASK_PRESETS[args.mask].items():
            setattr(cfg, k, v)
    if getattr(args, "xray", False):          # tum katmanlar: saydam kart, ic bakir acik
        cfg.show_inner_copper = True
        cfg.substrate_opacity = 0.15
    vs = ViewerScene(cfg)
    vs.load_snapshot(snap)
    if vs.missing:
        print("bulunamayan model:", len(vs.missing))

    if args.screenshot:
        from rendercanvas.offscreen import RenderCanvas
        canvas = RenderCanvas(size=(args.width, args.height), pixel_ratio=1)
    else:
        from rendercanvas.auto import RenderCanvas
        canvas = RenderCanvas(size=(1400, 900), title="IPCubed", max_fps=120)

    renderer = gfx.WgpuRenderer(canvas)
    camera = gfx.PerspectiveCamera(40, args.width / args.height)
    if args.screenshot and getattr(args, "view", "iso") in ("iso", "top"):
        # canli gorunumle ayni kamera donanimi (dinamik derinlik araligi dahil)
        from .camera_rig import CameraRig
        rig = CameraRig(camera)
        rig.set_aspect(args.width / args.height)
        rig.frame(vs.board_bounds, vs.thickness, cfg)
        rig.go("2d" if args.view == "top" else "3d", immediate=True)
        if getattr(args, "far", 1.0) != 1.0:
            rig.s.view_h *= args.far
            rig.apply()
    else:
        controller = gfx.OrbitController(camera, register_events=renderer)
        _frame_board(camera, vs, controller, getattr(args, "view", "iso"))

    if args.screenshot:
        t0 = time.perf_counter()
        while vs.pending():
            vs.poll_loading()
            time.sleep(0.05)
        vs.poll_loading()
        print(f"modeller hazir: {time.perf_counter()-t0:.1f}s")
        canvas.request_draw(lambda: renderer.render(vs.scene, camera))
        img = np.asarray(canvas.draw())
        from PIL import Image
        Image.fromarray(img).save(args.screenshot)
        print("kaydedildi", args.screenshot)
        vs.close()
        return

    q: queue.Queue = queue.Queue()
    sync = SyncThread(q)
    sync.start()

    def draw():
        renderer.render(vs.scene, camera)

    async def pump():
        """Kuyruktaki KiCad degisikliklerini ve biten modelleri isle; sadece degisince ciz."""
        import asyncio
        while True:
            dirty = vs.poll_loading()
            while True:
                try:
                    kind, payload = q.get_nowait()
                except queue.Empty:
                    break
                if kind == "moved":
                    if vs.apply_footprint_updates(payload):
                        dirty = True
                    else:
                        sync.request_full.set()
                elif kind == "full":
                    vs.load_snapshot(payload)
                    dirty = True
                elif kind == "status":
                    print(payload)
            if dirty:
                _log("draw")
                canvas.request_draw()
            await asyncio.sleep(0.016 if vs.pending() else 0.02)

    canvas.request_draw(draw)
    from rendercanvas.auto import loop
    loop.add_task(pump)
    try:
        loop.run()
    finally:
        sync.stop()
        vs.close()
