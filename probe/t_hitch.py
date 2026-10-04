"""Yeniden derleme (update_geometry) sirasinda render takilmasi: tam nesne vs dosya yolu. Offscreen."""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
    import pygfx as gfx
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import CameraRig
    from ipcubed.sync import SyncThread
    from rendercanvas.offscreen import RenderCanvas
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    st = SyncThread.__new__(SyncThread); st.ship_files = True; st._n = 0
    lite = st._ship(snap)
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
    for label, s in (("tam nesne ", snap), ("dosya yolu", lite)):
        canvas.draw()
        vs.update_geometry(s)
        out = []
        t_end = time.perf_counter() + 4.0
        while time.perf_counter() < t_end:
            t = time.perf_counter(); vs.poll_loading(); rig.rotate(2, 0); canvas.draw(); out.append((time.perf_counter() - t) * 1000)
        while vs.pending():
            vs.poll_loading(); time.sleep(0.02)
        a = np.array(out)
        print(f"{label}: kare n={len(a)} p50={np.percentile(a,50):.1f} p95={np.percentile(a,95):.1f} max={a.max():.0f} ms")
    vs.close()


if __name__ == "__main__":
    main()
