"""Net Highlighter offscreen: picking dogrulamasi + tek net / zone'lu net / diff pair secim goruntuleri + hover."""
import os, sys, time, pickle
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication([])  # noqa: F841  (ViewCube/istatistik QPainter kullanir)
    from ipcubed import compat  # noqa: F401
    from rendercanvas.offscreen import RenderCanvas
    from ipcubed.core import ViewerCore
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import RigState
    from ipcubed.nethl import pair_name
    from PIL import Image
    T = os.environ["TEMP"]
    OUT = r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\out"
    os.makedirs(OUT, exist_ok=True)
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    W, H = 1100, 700
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    cfg = Settings()
    if os.environ.get('NOMODELS'): cfg.show_comp_top = cfg.show_comp_bottom = False
    core = ViewerCore(canvas, cfg)
    core.visible = True
    vs = core.vs
    vs.keep_pool = True
    vs.load_snapshot(snap)
    t0 = time.perf_counter()
    while (vs.pending() or vs.loading) and time.perf_counter() - t0 < 25:
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    t0 = time.perf_counter()                                    # ic katmanlar arka planda
    while any(v != "done" for v in vs._inner.values()) or vs.layer_futures:
        vs.poll_loading(); time.sleep(0.02)
        if time.perf_counter() - t0 > 15: break
    vs.poll_loading()
    print(f"yuklendi; ic katman: {sum(v == 'done' for v in vs._inner.values())}, model grubu: {len(vs.groups)}")
    cd = snap.copper
    names = cd.net_names
    # aday netler
    seg = {}
    for L, arr in cd.tracks.items():
        for n in arr[:, 5].astype(int):
            seg[n] = seg.get(n, 0) + 1
    zn = {}
    for L, zs in cd.zones.items():
        for _, _, n in zs:
            zn.setdefault(n, set()).add(L)
    vnets = set(np.asarray(cd.vias.nets).tolist())

    def is_pair(n):
        p = pair_name(names[n]) if 0 < n < len(names) else None
        return p is not None and p in names
    single = max((n for n in seg if n and n not in zn and not is_pair(n) and n in vnets and seg[n] < 400), key=lambda n: seg[n])
    poly = max((n for n in zn if n and len(zn[n]) <= 3), key=lambda n: seg.get(n, 0))
    pairs = [n for n in seg if n and is_pair(n)]
    pair = max(pairs, key=lambda n: seg[n]) if pairs else None
    print("tek:", names[single], "| zone:", names[poly], sorted(zn[poly]), "| pair:", names[pair] if pair else None, "->", pair_name(names[pair]) if pair else None)

    def bbox(nets):
        xs, ys = [], []
        for arr in cd.tracks.values():
            m = np.isin(arr[:, 5].astype(int), list(nets))
            xs += list(arr[m, 0]) + list(arr[m, 2]); ys += list(arr[m, 1]) + list(arr[m, 3])
        for zs in cd.zones.values():
            for out, _, n in zs:
                if n in nets:
                    xs += list(out[:, 0]); ys += list(out[:, 1])
        return min(xs), -max(ys), max(xs), -min(ys)

    def frame(nets, yaw=-25.0, pitch=55.0):
        x0, y0, x1, y1 = bbox(nets)
        span = max(x1 - x0, y1 - y0, 6.0)
        core.rig.set_aspect(W / H)
        core.rig.s = RigState(((x0 + x1) / 2, (y0 + y1) / 2, vs.thickness / 2), span * 1.25, yaw, pitch, 35.0)
        core.rig.apply()

    def shot(name):
        img = np.asarray(canvas.draw())[..., :3]
        Image.fromarray(img).save(os.path.join(OUT, name))
        return img

    # --- picking: tek netin bir izinin ortasina ekranda tikla
    core.select_nets([])
    frame({single}, 0.0, 90.0)
    canvas.draw()
    # ekrani tara: tek netin pikselleri picking ile bulunuyor mu, kac ms
    hits, nets_seen, t = 0, set(), time.perf_counter()
    for sy in range(5, H, 12):
        for sx in range(5, W, 12):
            n = core._pick_net(sx, sy)
            if n:
                nets_seen.add(n)
            if n == single:
                hits += 1
    k = (H // 12 + 1) * (W // 12 + 1)
    print(f"picking taramasi: {names[single]} {hits} nokta, {len(nets_seen)} farkli net; {(time.perf_counter() - t) * 1000 / k:.2f} ms/pick")

    for label, n, fname in (("tek", single, "hl_single.png"), ("zone", poly, "hl_polygon.png"), ("pair", pair, "hl_diffpair.png")):
        if n is None:
            continue
        core.select_nets([n])
        frame(core.hl.selected)
        t = time.perf_counter()
        shot(fname)
        print(f"{label}: secili {[names[k] for k in sorted(core.hl.selected)]} ({(time.perf_counter() - t) * 1000:.0f} ms ilk kare) parca={len(core.hl._sel_group.children)} {[core.hl._owner[id(c)] for c in core.hl._sel_group.children]}")
    if pair is not None and os.environ.get("ALIAS"):             # ayni uzak goruntu: varsayilan vs 4x ornekleme (ince iz kesikleri)
        core.select_nets([pair]); frame(core.hl.selected)
        core._quality_scale = None
        a = shot("alias_ps2.png")
        core.renderer.pixel_scale = 4
        b = shot("alias_ps4.png")
        Image.fromarray(np.concatenate([a[250:520, 150:600], b[250:520, 150:600]], 1)).resize((1800, 540), Image.NEAREST).save(os.path.join(OUT, "alias_cmp.png"))
        core.renderer.pixel_scale = 2
        core.close(); return
    if pair is not None:                                        # diff pair yakindan: en uzun parcanin ortasi
        core.select_nets([pair])
        arr = cd.tracks[3] if 3 in cd.tracks else next(iter(cd.tracks.values()))
        m = arr[np.isin(arr[:, 5].astype(int), list(core.hl.selected))]
        if len(m):
            L = np.hypot(m[:, 2] - m[:, 0], m[:, 3] - m[:, 1]); r = m[np.argmax(L)]
            cx, cy = (r[0] + r[2]) / 2, -(r[1] + r[3]) / 2
            core.rig.s = RigState((cx, cy, vs.thickness / 2), 9.0, -25.0, 50.0, 35.0); core.rig.apply()
            shot("hl_diffpair_close.png")
    # alttan: secili netin arkadaki izleri de one gelir mi
    core.select_nets([single]); frame({single}, -25.0, -55.0); shot("hl_single_bottom.png")
    # hover (secim yok): mavi yanip sonme, kart arkasindaki bakir da gorunur
    core.select_nets([])
    core.hl.hover = core.with_pair(single)
    frame({single})
    import ipcubed.nethl as nh
    tt = time.perf_counter()
    while (time.perf_counter() % nh.PULSE_S) / nh.PULSE_S < 0.45 or (time.perf_counter() % nh.PULSE_S) / nh.PULSE_S > 0.55:
        time.sleep(0.005)                                        # yanip sonmenin tepesi
    shot("hl_hover.png")
    # ayni net, normal gorunum (karsilastirma)
    core.hl.hover = set(); shot("hl_none.png")
    # performans: secim varken kare suresi
    core.select_nets([poly]); frame({poly})
    canvas.draw()
    t = time.perf_counter()
    for _ in range(10):
        canvas.draw()
    print(f"secim varken kare: {(time.perf_counter() - t) * 100:.1f} ms")
    core.close()


if __name__ == "__main__":
    main()


