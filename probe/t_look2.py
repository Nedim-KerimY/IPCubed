"""Via yakin cekim + x-ray (ic katmanlar, saydam govde) - karo dikisi / via halkasi kontrolu. Offscreen."""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
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
    snap.poses = {}; snap.data_path = None
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    xray = "--xray" in sys.argv
    if xray:
        cfg.show_inner_copper = True; cfg.substrate_opacity = 0.15
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
    v = snap.copper.vias.xyd
    i = len(v) // 3
    for vh, yaw, pitch in ((3.0, 30, 55), (1.5, 0, 30), (40.0, 20, 40)):
        rig.s = RigState((v[i][0], -v[i][1], vs.thickness), vh, yaw, pitch, 35.0); rig.apply()
        shots.append(np.asarray(canvas.draw())[..., :3])
    Image.fromarray(np.concatenate(shots, axis=1)).save(os.path.join(T, "look_via_xray.png" if xray else "look_via.png"))
    vs.close()


if __name__ == "__main__":
    main()
