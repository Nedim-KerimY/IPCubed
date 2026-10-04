"""BGA civarindaki bir via'nin izometrik yakin cekimi (offscreen)."""
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
    bga = next(f for f in snap.footprints if any("BGA" in m.raw_path.upper() for m in f.models))
    # BGA pad'lerinin sinir kutusu
    pads = [p for p in snap.copper.pads if abs(p.x - bga.x) < 20 and abs(p.y - bga.y) < 20]
    xs = np.array([p.x for p in pads]); ys = np.array([p.y for p in pads])
    near = [p for p in pads if abs(p.x - bga.x) < 16 and abs(p.y - bga.y) < 16]
    x0, x1 = min(p.x for p in near), max(p.x for p in near); y0, y1 = min(p.y for p in near), max(p.y for p in near)
    v = snap.copper.vias.xyd
    # BGA disinda, kenarina 1.5-4 mm uzaklikta, ust yuzde (F.Cu) olan bir via
    best = None
    for i, (x, y, d, dr) in enumerate(v):
        dx = max(x0 - x, 0, x - x1); dy = max(y0 - y, 0, y - y1)
        dist = max(dx, dy)
        if 4.0 < dist < 9.0 and 3 in snap.copper.vias.layers[i]:
            if best is None or dist < best[0]:
                best = (dist, i)
    i = best[1]
    vx, vy, vd, vdr = v[i]
    print(f"BGA {bga.reference} @ ({bga.x:.1f},{bga.y:.1f}); via #{i} @ ({vx:.2f},{vy:.2f}) cap {vd:.2f} mm delik {vdr:.2f} mm")
    cfg = Settings()
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    W, H = 1600, 1000
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas)
    cam = gfx.PerspectiveCamera(35, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg)
    # BGA'ya dogru bakan izometrik aci: via one, BGA arkada
    ux, uy = bga.x - vx, -(bga.y - vy)                      # sahne koordinatinda via -> BGA yonu
    n = (ux * ux + uy * uy) ** 0.5; ux, uy = ux / n, uy / n
    ang = np.degrees(np.arctan2(-ux, uy))                    # kamera BGA'nin karsi tarafinda, via'ya ve arkasindaki BGA'ya bakar
    close = "--close" in sys.argv
    if close:
        rig.s = RigState((vx, -vy, vs.thickness), 1.1, float(ang), 55.0, 35.0)
    else:
        rig.s = RigState((vx + ux * 1.2, -vy + uy * 1.2, vs.thickness), 6.0, float(ang), 35.0, 35.0)
    rig.apply()
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    canvas.draw()
    out = os.path.join(r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d", "via_bga_close.png" if close else "via_bga_iso.png")
    Image.fromarray(np.asarray(canvas.draw())[..., :3]).save(out)
    print(out)
    vs.close()


if __name__ == "__main__":
    main()
