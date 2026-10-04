"""Arka plan KiCad veri cekimi (sync thread) render karelerini ne kadar takiltiyor? (offscreen, salt-okunur)"""
import os, sys, time, pickle, threading
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat
    import pygfx as gfx
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import CameraRig
    from ipcubed.kicad_source import KiCadSource
    from rendercanvas.offscreen import RenderCanvas
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    cd0 = snap.copper
    if not getattr(cd0, "fp_index", None):
        cd0.fp_index = {}
    snap.poses = {}
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    W, H = 1280, 720
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); r.pixel_scale = 1
    cam = gfx.PerspectiveCamera(35, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg); rig.go("3d", immediate=True)
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    canvas.draw()

    def frames(sec):
        out = []
        t_end = time.perf_counter() + sec
        while time.perf_counter() < t_end:
            t = time.perf_counter(); rig.rotate(3, 0); canvas.draw(); out.append((time.perf_counter() - t) * 1000)
        a = np.array(out)
        return f"n={len(a)} p50={np.percentile(a,50):.1f} p95={np.percentile(a,95):.1f} max={a.max():.0f} ms"

    print("bosta        :", frames(2.0))
    done = threading.Event()

    def bg():
        t = time.perf_counter()
        # KiCad protobuf cozumlemesine benzer saf Python yuk (GIL tutar): ~2 sn
        acc = []
        while time.perf_counter() - t < 2.0:
            acc.append([(i * 0.5, str(i)) for i in range(2000)])
        print(f"   (refresh_geometry {time.perf_counter() - t:.1f}s)")
        done.set()
    threading.Thread(target=bg, daemon=True).start()
    print("cekim sirasinda:", frames(2.5))
    done.wait(10)
    vs.close()


if __name__ == "__main__":
    main()
