"""Uzun yollarda eksik kisa parcalar: her iz parcasinin ortasi, o katmanin iz mesh'inde (ayni net) bir ucgenle kaplaniyor mu?
Delik (via/pad drill) icine dusen parca ortalari ayrica sayilir (dogru kirpma). Tam yapim + canli kismi iz yenilemesi."""
import dataclasses, os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.sync import SyncThread
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    st = SyncThread.__new__(SyncThread); st.ship_files = True; st._n = 0
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg); vs.keep_pool = True; vs.load_snapshot(st._ship(snap))
    t0 = time.perf_counter()
    while (vs.pending() or any(v != "done" for v in vs._inner.values())) and time.perf_counter() - t0 < 25:
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    cd = snap.copper
    hx, hy, hr = [], [], []
    xyd = np.asarray(cd.vias.xyd).reshape(-1, 4)
    hx += list(xyd[:, 0]); hy += list(-xyd[:, 1]); hr += list(xyd[:, 3] / 2 + 0.006)
    for p in cd.pads:
        if p.drill_w > 0:
            hx.append(p.x); hy.append(-p.y); hr.append(max(p.drill_w, p.drill_h) / 2 + 0.006)
    hx, hy, hr = map(np.array, (hx, hy, hr))

    def prep(m, G):
        P = m.geometry.positions.data[:, :2]
        T = np.asarray(m.geometry.indices.data).reshape(-1, 3)
        A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        net = G[T[:, 0]] & 0xFFFF
        o = np.argsort(net, kind="stable")
        A, B, C, net = A[o], B[o], C[o], net[o]
        return A, B, C, net, np.minimum(np.minimum(A, B), C), np.maximum(np.maximum(A, B), C)

    def covered(pr, q, n):
        A, B, C, net, lo, hi = pr
        i0, i1 = np.searchsorted(net, n, "left"), np.searchsorted(net, n, "right")
        A, B, C, lo, hi = A[i0:i1], B[i0:i1], C[i0:i1], lo[i0:i1], hi[i0:i1]
        s = (lo[:, 0] <= q[0] + 1e-6) & (hi[:, 0] >= q[0] - 1e-6) & (lo[:, 1] <= q[1] + 1e-6) & (hi[:, 1] >= q[1] - 1e-6)
        a, b, c = A[s], B[s], C[s]

        def cr(u, v):
            return (v[:, 0] - u[:, 0]) * (q[1] - u[:, 1]) - (v[:, 1] - u[:, 1]) * (q[0] - u[:, 0])
        d1, d2, d3 = cr(a, b), cr(b, c), cr(c, a)
        return bool((((d1 >= -1e-9) & (d2 >= -1e-9) & (d3 >= -1e-9)) | ((d1 <= 1e-9) & (d2 <= 1e-9) & (d3 <= 1e-9))).any())

    def check(cd, layers, tag):
        tot, hole = 0, 0
        for L in sorted(layers):
            arr = cd.tracks.get(L)
            m = vs.layer_meshes.get(f"cut:{L}")
            if arr is None or m is None:
                continue
            pr = prep(m, vs.layer_tags[f"cut:{L}"])
            mids = np.c_[(arr[:, 0] + arr[:, 2]) / 2, -(arr[:, 1] + arr[:, 3]) / 2]
            for i, q in enumerate(mids):
                if covered(pr, q, int(arr[i, 5])):
                    continue
                if (np.hypot(hx - q[0], hy - q[1]) <= hr).any():
                    hole += 1
                    continue
                tot += 1
                if tot <= 5:
                    print("   EKSIK", f"cut:{L}", np.round(arr[i], 4).tolist(), cd.net_names[int(arr[i, 5])])
        print(f"{tag}: gercek eksik {tot}, delik icinde (dogru) {hole}")

    check(cd, set(cd.tracks), "tam yapim")
    tr = dict(cd.tracks); tr[3] = tr[3][:-1]; tr[34] = tr[34][:-1]
    cd2 = dataclasses.replace(cd, tracks=tr)
    vs.update_partial(st._ship(dataclasses.replace(snap, copper=cd2)), {"track_data": {3: tr[3], 34: tr[34]}, "cu": set(), "tracks": {3, 34},
                      "zones": set(), "body": False, "barrel": False, "silk": False, "pads": False})
    while vs.pending() or vs._batch is not None:
        vs.poll_loading(); time.sleep(0.01)
    check(cd2, {3, 34}, "canli iz yenilemesi")
    vs.close()


if __name__ == "__main__":
    main()
