"""Via deligi kenarindaki cizgilenmenin kaynagi: mesh'leri tek tek kapatip ayni yakin cekimi al. Offscreen."""
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
    vx, vy, vd, vdr = snap.copper.vias.xyd[7]
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    W, H = 500, 400
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas)
    cam = gfx.PerspectiveCamera(35, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg)
    rig.s = RigState((vx, -vy, vs.thickness), 0.9, 200.0, 38.0, 35.0); rig.apply()
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    shots = []
    tests = [("hepsi", []), ("iz yok", ["cut:3"]), ("tup yok", ["viab", "viabc"]), ("maske yok", ["mask:"]), ("dielektrik yok", ["diel:"])]
    for name, hide in tests:
        changed = []
        for k, m in list(vs.layer_meshes.items()):
            if any(k.startswith(h) for h in hide) and m.visible:
                m.visible = False; changed.append(m)
        for k, ex in vs.mask_haze.items():
            if any(k.startswith(h) for h in hide):
                for x in ex:
                    if x.visible:
                        x.visible = False; changed.append(x)
        shots.append(np.asarray(canvas.draw())[..., :3].copy())
        for m in changed:
            m.visible = True
        print(name)
    Image.fromarray(np.concatenate(shots, axis=1)).save(os.path.join(T, "via_zfight.png"))
    vs.close()


if __name__ == "__main__":
    main()
