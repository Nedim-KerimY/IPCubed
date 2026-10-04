"""Bir via'yi tam ustten (ortografige yakin) ciz, halka ve delik capini piksel olarak olc. Offscreen."""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def runs(row, mask, c):
    """c merkez pikselinden saga/sola mask True olan kesintisiz uzunluk."""
    l = c
    while l > 0 and mask[l - 1]:
        l -= 1
    r = c
    while r < len(row) - 1 and mask[r + 1]:
        r += 1
    return l, r


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
    i = 7
    vx, vy, vd, vdr = snap.copper.vias.xyd[i]
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    for k in ("mask:top", "mask:bottom", "silk:top", "silk:bottom"):      # bakir halkayi dogrudan gormek icin maske/silk kapali
        cfg.layer_visible[k] = False
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    W = H = 1000
    VIEW = 0.8                                       # mm: goruntu yuksekligi -> 1 px = 0.8 um
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); r.pixel_scale = 1
    cam = gfx.OrthographicCamera(VIEW, VIEW)          # gercek ortografik: perspektif kaymasi yok
    cam.local.position = (vx, -vy, vs.thickness + 5.0)
    cam.world.reference_up = (0, 1, 0)
    cam.look_at((vx, -vy, 0.0))
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    img = np.asarray(canvas.draw())[..., :3].astype(np.int32)
    out = os.path.join(r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d", "via_top_measure.png")
    Image.fromarray(img.astype(np.uint8)).save(out)
    c = W // 2
    row = img[c]
    hole_col = row[c]                                # merkez: delikten gorunen (arka plan)
    diel_col = row[5]                                # kenar: dielektrik yuzeyi
    near = lambda a, b: np.abs(a - b).sum(axis=-1) < 40
    h_l, h_r = runs(row, near(row, hole_col), c)
    ring = ~near(row, diel_col)                      # dielektrik olmayan her sey (halka + delik)
    o_l, o_r = runs(row, ring, c)
    hole_px, ring_px = h_r - h_l + 1, o_r - o_l + 1
    mm_per_px = VIEW / H
    print(f"via #{i}: KiCad size {vd:.3f} mm, drill {vdr:.3f} mm (oran {vd/vdr:.2f})")
    print(f"renk: delik {hole_col.tolist()} dielektrik {diel_col.tolist()} halka {row[(o_l + h_l) // 2].tolist()}")
    print(f"olculen: bakir halka {ring_px} px = {ring_px*mm_per_px:.3f} mm, delik {hole_px} px = {hole_px*mm_per_px:.3f} mm, oran {ring_px/hole_px:.2f}")
    # dikey de olc
    col = img[:, c]
    h2 = runs(col, near(col, hole_col), c); o2 = runs(col, ~near(col, diel_col), c)
    print(f"dikey   : bakir halka {o2[1]-o2[0]+1} px, delik {h2[1]-h2[0]+1} px")
    print(out)
    vs.close()


if __name__ == "__main__":
    main()
