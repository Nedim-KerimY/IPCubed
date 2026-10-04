"""Offscreen performans olcumu (kullanicinin ekranina dokunmaz): derleme suresi, vertex/ucgen sayilari, kare suresi, RAM.
python probe/t_perf.py [--ssaa1] [--models]"""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np, psutil
    from ipcubed import compat
    import pygfx as gfx
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import CameraRig
    from rendercanvas.offscreen import RenderCanvas
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    cd0 = snap.copper
    if not getattr(cd0, "fp_index", None):
        fps_xy = np.array([[f.x, f.y] for f in snap.footprints]); fids = [f.kiid for f in snap.footprints]
        cd0.fp_index = {}
        for q in cd0.pads:
            j = int(np.argmin(np.hypot(fps_xy[:, 0] - q.x, fps_xy[:, 1] - q.y)))
            q.fp = fids[j]; cd0.fp_index.setdefault(q.fp, len(cd0.fp_index))
    snap.poses = {}
    cfg = Settings()
    if "--models" not in sys.argv:
        cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg)
    t0 = time.perf_counter(); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    build = time.perf_counter() - t0
    nv = nt = 0
    rows = []
    for k, m in sorted(vs.layer_meshes.items()):
        if not m.visible:
            continue
        v = len(m.geometry.positions.data); t = len(m.geometry.indices.data)
        mult = 3 if k.startswith("mask:") else 1                # maske 3 gecis (filtre + ton + parlaklik)
        nv += v * mult; nt += t * mult
        rows.append((k, v, t))
    rows.sort(key=lambda r: -r[2])
    mt = mi = 0; big = []
    for g in vs.groups.values():
        for m in g.meshes:
            tri = len(m.geometry.indices.data); mt += tri * len(g.slots); mi += len(g.slots)
            big.append((tri * len(g.slots), tri, len(g.slots), g.path.name))
    big.sort(reverse=True)
    print(f"modeller: {mt/1e6:.2f}M ucgen (ornekli), {mi} ornek, {len(vs.groups)} grup")
    for b in big[:6]: print("   ", b)
    W, H = 1920, 1080
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas)
    if "--ssaa1" in sys.argv:
        r.pixel_scale = 1
    cam = gfx.PerspectiveCamera(35, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg); rig.go("3d", immediate=True)
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    canvas.draw(); canvas.draw()
    n = 15
    t = time.perf_counter()
    for i in range(n):
        rig.rotate(12, 0)
        canvas.draw()
    ft = (time.perf_counter() - t) / n * 1000
    rss = psutil.Process().memory_info().rss / 2**20
    print(f"derleme {build:.1f}s | gorunur ucgen {nt/1e6:.2f}M vertex {nv/1e6:.2f}M | kare {ft:.1f} ms ({1000/ft:.0f} fps, 1920x1080, pixel_scale={r.pixel_scale}) | RSS {rss:.0f} MB")
    for k, v, tt in rows[:8]:
        print(f"   {k:16s} ucgen {tt/1e3:8.0f}k  vertex {v/1e3:8.0f}k")
    vs.close()


if __name__ == "__main__":
    main()
