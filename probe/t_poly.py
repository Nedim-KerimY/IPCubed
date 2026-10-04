"""Polygon Opacity (exploded) + Highlight Polygons (net highlighter) + menu gorunumu. Offscreen."""
import os, sys, time, pickle
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication([])
    from ipcubed import compat, theme  # noqa: F401
    theme.apply_app_font(app)
    from rendercanvas.offscreen import RenderCanvas
    from ipcubed.core import ViewerCore
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import RigState
    from ipcubed.ctxmenu import build_menu
    from PIL import Image
    OUT = r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\out"
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    W, H = 1400, 900
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    core = ViewerCore(canvas, cfg); core.visible = True
    vs = core.vs; vs.keep_pool = True
    vs.load_snapshot(snap)
    t0 = time.perf_counter()
    while (vs.pending() or vs.loading or any(v != "done" for v in vs._inner.values())) and time.perf_counter() - t0 < 25:
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    b = vs.board_bounds

    def shot(name):
        Image.fromarray(np.asarray(canvas.draw())[..., :3]).save(os.path.join(OUT, name))

    def settle():
        for _ in range(200):
            core.tick()
            if core._ex_anim is None:
                break
            time.sleep(0.01)
        core.tick()

    core.rig.set_aspect(W / H); core.tick()
    core.rig.frame(b, vs.thickness, core.cfg)
    s = core.rig.s
    core.rig.s = RigState((s.target[0] + 12, s.target[1], 24.0), s.view_h * 1.3, -30.0, 24.0, s.fov); core.rig.apply()
    core.toggle_explode(True); settle()
    zones = [k for k in vs.layer_meshes if k.startswith("cuz:")]
    for op in (1.0, 0.3):
        cfg.polygon_opacity = op; vs.apply_settings()
        mats = {vs.layer_meshes[k].material.opacity for k in zones}
        print(f"polygon opacity {op}: zone mesh sayisi {len(zones)}, malzeme opakligi {mats}, alpha {vs.layer_meshes[zones[0]].material.alpha_mode}")
        shot(f"poly_{int(op * 100)}.png")
    cfg.polygon_opacity = 1.0; vs.apply_settings()
    core.toggle_explode(False); settle()
    print("kapaninca zone opakligi:", {vs.layer_meshes[k].material.opacity for k in zones})
    # Highlight Polygons: True / False (VDDQ zone'lu net)
    names = snap.copper.net_names
    nid = names.index("VDDQ")
    for flag in (True, False):
        cfg.highlight_polygons = flag; vs.apply_settings()
        core.select_nets([nid])
        core.rig.frame(b, vs.thickness, core.cfg)
        shot(f"hlpoly_{flag}.png")
        grp = [core.hl._owner[id(c)] for c in core.hl._sel_group.children]
        print(f"Highlight Polygons {flag}: secili parca {len(grp)}; cuz var mi: {any(k.startswith('cuz:') for k in grp)}")
        # zone uzerinde picking: polygon kapaliyken zone secilmemeli
        hits = {}
        for sy in range(5, H, 40):
            for sx in range(5, W, 40):
                n = core._pick_net(sx, sy)
                if n:
                    hits[n] = hits.get(n, 0) + 1
        print(f"   picking: VDDQ {hits.get(nid, 0)} nokta, toplam {sum(hits.values())}")
    core.select_nets([])
    # menu goruntuleri
    for tag, kw in (("exploded", dict(exploded=True, poly_opacity=0.6)), ("highlight", dict(hl_active=True, has_sel=True, can_2d=True, hl_polygons=False))):
        m, A = build_menu(None, False, True, False, **kw)
        m.show(); app.processEvents()
        m.grab().save(os.path.join(OUT, f"menu_{tag}.png"))
        m.hide()
    core.close()


if __name__ == "__main__":
    main()
