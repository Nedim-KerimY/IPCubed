"""Kismi yenileme: yalniz plan'daki katmanlar yeniden uretilir mi, ne kadar surer? (offscreen, KiCad gerekmez)"""
import dataclasses, os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.sync import SyncThread
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    st = SyncThread.__new__(SyncThread); st.ship_files = True; st._n = 0
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.keep_pool = True
    vs.load_snapshot(st._ship(snap))
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    t = time.perf_counter()
    while vs._warm_futs or vs._warm_key is None:                 # hizli iscinin isinmasini bekle (gercekte arka planda)
        vs.poll_loading(); time.sleep(0.02)
        if time.perf_counter() - t > 20: break
    print(f"isinma {time.perf_counter() - t:.1f}s")
    ids0 = {k: id(m) for k, m in vs.layer_meshes.items()}
    tri0 = {k: len(m.geometry.indices.data) for k, m in vs.layer_meshes.items()}

    def run(label, new_cd, plan):
        s2 = dataclasses.replace(snap, copper=new_cd)
        t = time.perf_counter()
        vs.update_partial(st._ship(s2), plan)
        while vs.pending() or vs._batch is not None:
            vs.poll_loading(); time.sleep(0.005)
        dt = time.perf_counter() - t
        changed = sorted(k for k, m in vs.layer_meshes.items() if ids0.get(k) != id(m))
        print(f"{label}: {dt*1000:.0f} ms, yeniden uretilen: {changed}")
        for k in changed:
            ids0[k] = id(vs.layer_meshes[k])

    cd = snap.copper
    tr = dict(cd.tracks); L = 3; tr[L] = tr[L][: len(tr[L]) // 2]          # F.Cu izlerin yarisi silindi
    run("iz (F.Cu)      ", dataclasses.replace(cd, tracks=tr), {"track_data": {3: tr[3]}, "cu": set(), "tracks": {3}, "zones": set(), "body": False, "barrel": False, "silk": False, "pads": False})
    tr2 = dict(tr); tr2[3] = tr2[3][:-3]
    run("iz 2. duzenleme", dataclasses.replace(cd, tracks=tr2), {"track_data": {3: tr2[3]}, "cu": set(), "tracks": {3}, "zones": set(), "body": False, "barrel": False, "silk": False, "pads": False})
    zn = dict(cd.zones); Lz = 3; zn[Lz] = zn[Lz][1:]                       # F.Cu'da bir zone dolgusu gitti
    run("zone (F.Cu)    ", dataclasses.replace(cd, zones=zn), {"zone_data": {3: zn[3]}, "cu": set(), "tracks": set(), "zones": {3}, "body": False, "barrel": False, "silk": False, "pads": False})
    from ipcubed.body import tiles_for
    from ipcubed.copper import ViaData
    v = cd.vias; keep = np.arange(len(v.xyd)) != 100                 # bir via silindi
    nv = ViaData(v.xyd[keep], v.nets[keep], [s for i, s in enumerate(v.layers) if keep[i]], v.cover[keep], v.hide_drill[keep])
    x, y, d, dr = v.xyd[100]
    run("via sil        ", dataclasses.replace(cd, vias=nv), {"cu": set(), "tracks": set(), "zones": set(), "body": False, "vias": True,
        "body_tiles": tiles_for(vs.board_bounds, [(x, -y, d / 2 + 0.6)]), "barrel": False, "silk": False, "pads": False})
    t = time.perf_counter()
    while len(vs._inner) < 10 or any(s != "done" for s in vs._inner.values()):
        vs.poll_loading(); time.sleep(0.05)
        if time.perf_counter() - t > 40:
            break
    print(f"ic katmanlar arka planda: {sum(1 for s in vs._inner.values() if s == 'done')}/10 hazir, {time.perf_counter()-t:.1f}s")
    vs.close()


if __name__ == "__main__":
    main()
