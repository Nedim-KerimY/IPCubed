"""Gorsel kontrol (offscreen): genel izometrik + PTH delik yakin + kart kenari yakin."""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat
    import pygfx as gfx
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import CameraRig, RigState
    from rendercanvas.offscreen import RenderCanvas
    from PIL import Image
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    W, H = 640, 420
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas)
    cam = gfx.PerspectiveCamera(35, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg)
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    shots = []
    rig.go("3d", immediate=True); shots.append(np.asarray(canvas.draw()))
    p = next(p for p in snap.copper.pads if not p.npth and p.drill_w >= 0.8)
    rig.s = RigState((p.x, -p.y, vs.thickness), 4.0 * max(p.drill_w, 1.0), 20.0, 50.0, 35.0); rig.apply()
    shots.append(np.asarray(canvas.draw()))
    b = vs.board_bounds
    rig.s = RigState((b[0] + 2, (b[1] + b[3]) / 2, vs.thickness / 2), 6.0, -60.0, 15.0, 35.0); rig.apply()
    shots.append(np.asarray(canvas.draw()))
    Image.fromarray(np.concatenate([s[..., :3] for s in shots], axis=1)).save(os.path.join(T, sys.argv[1] if len(sys.argv) > 1 else "look.png"))
    vs.close()


if __name__ == "__main__":
    main()
