import time, numpy as np
from ipcubed import compat
import pygfx as gfx
from ipcubed.kicad_source import KiCadSource
from ipcubed.scene_builder import ViewerScene
from ipcubed.app import _frame_board
from rendercanvas.offscreen import RenderCanvas


def main():
    t0 = time.perf_counter()
    snap = KiCadSource().snapshot()
    t1 = time.perf_counter()
    vs = ViewerScene(); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    t2 = time.perf_counter()
    print(f"snapshot {t1-t0:.2f}s, sahne+modeller+bakir hazir {t2-t1:.2f}s")
    canvas = RenderCanvas(size=(1920, 1080), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(40, 1920 / 1080)
    _frame_board(cam, vs)
    vs.scene.add(gfx.Background.from_color("#2b2f36", "#14161a"))
    canvas.request_draw(lambda: r.render(vs.scene, cam)); canvas.draw()
    n = 60
    t = time.perf_counter()
    for i in range(n):
        cam.local.x += 0.2
        canvas.request_draw(lambda: r.render(vs.scene, cam)); canvas.draw()
    dt = (time.perf_counter() - t) / n
    print(f"kare suresi {dt*1000:.1f} ms  ({1/dt:.0f} fps) @1920x1080 (okuma dahil)")
    tris = sum(len(g.data.indices) * len(g.slots) for g in vs.groups.values() if g.data is not None)
    print("model ucgen (instance toplam):", tris)
    vs.close()


if __name__ == "__main__":
    main()
