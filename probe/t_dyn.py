import dataclasses, os, sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat
    import pygfx as gfx
    from ipcubed.kicad_source import KiCadSource
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import CameraRig, RigState
    from rendercanvas.offscreen import RenderCanvas
    from PIL import Image
    T = os.environ["TEMP"]
    import pickle
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    cd0 = snap.copper
    fps_xy = np.array([[f.x, f.y] for f in snap.footprints]); fids = [f.kiid for f in snap.footprints]
    cd0.fp_index = {}
    for q in cd0.pads:                                  # eski goruntude pad ust footprint'i yok: en yakin footprint'e ata
        j = int(np.argmin(np.hypot(fps_xy[:, 0] - q.x, fps_xy[:, 1] - q.y)))
        q.fp = fids[j]; cd0.fp_index.setdefault(q.fp, len(cd0.fp_index))
    snap.poses = {}
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.keep_pool = True; vs.load_snapshot(snap)
    t0 = time.perf_counter()
    while vs.pending():
        vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
    print("derleme", round(time.perf_counter() - t0, 1), "s; taban mesh:", sorted(vs._tri))
    t1 = time.perf_counter()
    while (vs._warm_futs or vs._warm_key is None or vs._mask_fut is not None or vs._mask_cuts is None or not isinstance(vs._mask_cuts[1], dict)) and time.perf_counter() - t1 < 20:
        vs.poll_loading(); time.sleep(0.02)
        if vs._mask_cuts is not None and not isinstance(vs._mask_cuts[1], dict) and vs._mask_cuts[1].done():
            vs._mask_cuts = (vs._mask_cuts[0], vs._mask_cuts[1].result())
    t2 = time.perf_counter()
    while time.perf_counter() - t2 < 6:                      # arka plan isleri (isinma, ic katmanlar) bitsin
        vs.poll_loading(); time.sleep(0.05)
    print("isindi", round(time.perf_counter() - t1, 1), "s; bekleyen:", len(vs._warm_futs), vs.pending())
    # SMD pad'li, top yuz, birkac pad'li bir footprint sec
    cd = snap.copper
    by = {}
    for p in cd.pads:
        if 42 in p.layers and 3 in p.layers and not p.npth and p.drill_w == 0:
            by.setdefault(p.fp, []).append(p)
    kiid = next(k for k, v in by.items() if 6 <= len(v) <= 12 and not snap.footprints[0].bottom)
    fp = vs.fps[kiid]
    print("footprint", fp.reference, round(fp.x, 2), round(fp.y, 2), "pad", len(by[kiid]))
    W, H = 900, 600
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(30, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H)
    rig.s = RigState((fp.x + 2.0, -fp.y, vs.thickness), 22.0, 0.0, 90.0, 30.0); rig.apply()
    def shot(name):
        canvas.request_draw(lambda: r.render(vs.scene, cam))
        Image.fromarray(np.asarray(canvas.draw())).save(os.path.join(T, name))
    shot("dyn_0.png")
    new = dataclasses.replace(fp, x=fp.x + 4.0)
    t = time.perf_counter()
    ok = vs.apply_footprint_updates([new])
    dt = (time.perf_counter() - t) * 1000
    print("apply_footprint_updates:", ok, f"{dt:.0f} ms; dyn:", sorted(k for k in vs.layer_meshes if k.endswith(':dyn')))
    tj = time.perf_counter(); f = vs._mask_fut
    while f is not None and not f.done(): time.sleep(0.002)
    print(f"  maske isi (isci): {time.perf_counter()-tj:.2f}s karolar={sorted(vs._mask_tiles_live)} cuts={type(vs._mask_cuts[1]).__name__ if vs._mask_cuts else None}")
    t1 = time.perf_counter()
    while vs._mask_fut is not None or vs._mask_shown is None or vs._mask_shown[1] == ():
        vs.poll_loading(); time.sleep(0.02)
        if time.perf_counter() - t1 > 15: print("maske zaman asimi"); break
    print(f"maske yenilendi: {time.perf_counter() - t1:.2f} s (sicak)")
    shot("dyn_1.png")
    # geri al: taban konuma
    vs.apply_footprint_updates([fp])
    print("geri alinca dyn:", sorted(k for k in vs.layer_meshes if k.endswith(':dyn')))
    t = time.perf_counter(); vs.apply_footprint_updates([dataclasses.replace(fp, x=fp.x + 4.0, angle=fp.angle + 90)]); print(f"tasi+dondur {1000*(time.perf_counter()-t):.0f} ms")
    shot("dyn_2.png")
    vs.close()


if __name__ == "__main__":
    main()
