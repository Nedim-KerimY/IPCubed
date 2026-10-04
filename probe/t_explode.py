"""Exploded board view offscreen: animasyon, gizmo picking/hover etiketi, surukleme, Shift ile esit aralik, kucuk kup tiki."""
import os, sys, time, pickle
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


class Ev:
    def __init__(self, type, x, y, button=0, modifiers=()):
        self.type, self.x, self.y, self.button, self.modifiers = type, x, y, button, tuple(modifiers)
        self.dx = self.dy = 0


def main():
    import numpy as np
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication([])  # noqa: F841
    from ipcubed import compat  # noqa: F401
    from rendercanvas.offscreen import RenderCanvas
    from ipcubed.core import ViewerCore
    from ipcubed.settings import Settings
    from ipcubed.camera_rig import RigState
    from PIL import Image
    OUT = r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\out"
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    W, H = 1400, 900
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    cfg = Settings(); cfg.show_inner_copper = True
    if os.environ.get("NOMODELS"):
        cfg.show_comp_top = cfg.show_comp_bottom = False
    core = ViewerCore(canvas, cfg)
    core.visible = True
    vs = core.vs; vs.keep_pool = True
    vs.load_snapshot(snap)
    t0 = time.perf_counter()
    while (vs.pending() or vs.loading or any(v != "done" for v in vs._inner.values())) and time.perf_counter() - t0 < 25:
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    b = vs.board_bounds

    def view():
        core.rig.set_aspect(W / H)
        core.rig.frame(b, vs.thickness, core.cfg)
        s = core.rig.s
        tx, ty, _ = s.target
        core.rig.s = RigState((tx + 12, ty, 24.0), s.view_h * 1.3, -30.0, 24.0, s.fov); core.rig.apply()

    def shot(name):
        img = np.asarray(canvas.draw())[..., :3]
        Image.fromarray(img).save(os.path.join(OUT, name))

    def settle():
        for _ in range(200):
            core.tick()
            if core._ex_anim is None:
                break
            time.sleep(0.01)
        core.tick()

    core.tick(); view(); core.tick(); shot("ex_0_normal.png")
    t = time.perf_counter()
    core.toggle_explode(True)
    core.tick()
    ta = time.perf_counter(); canvas.draw(); print(f"animasyon karesi (ilk): {(time.perf_counter() - ta) * 1000:.0f} ms")
    settle()
    print(f"patlatma animasyonu bitti: {(time.perf_counter() - t) * 1000:.0f} ms; ofset {np.round(core._ex_off, 2).tolist()}")
    shot("ex_1_exploded.png")
    vs.ex_hide_diel = True; vs.apply_settings(); shot("ex_1d_nodiel.png"); vs.ex_hide_diel = False; vs.apply_settings()
    keep = core.rig.s
    pth = next(p for p in snap.copper.pads if not p.npth and p.drill_w >= 0.9)
    core.rig.s = RigState((pth.x, -pth.y, 20.0), 45.0, -30.0, 18.0, keep.fov); core.rig.apply(); shot("ex_1b_pth.png")
    core.rig.s = RigState((pth.x + 6, -pth.y, 30.0), 14.0, -20.0, 12.0, keep.fov); core.rig.apply(); shot("ex_1c_close.png")
    core.rig.s = keep; core.rig.apply()
    t = time.perf_counter()
    for _ in range(5):
        canvas.draw()
    print(f"patlatilmis kare: {(time.perf_counter() - t) * 200:.1f} ms")
    # gizmo picking: 4. kup (In3) ekranda nerede, pick dogru mu
    cu = core._ex_layers()
    off = core._ex_current()
    c = core.ex.corner

    def scr(i, small=False):
        x = c[0] + (core.ex.size * 1.65 if small else 0)
        return core._to_screen((x, c[1], (cu[i].z0 + cu[i].z1) / 2 + float(core._ex_current()[i])))
    p = scr(3)
    print("pick In3 buyuk:", core._ex_pick(*p), "kucuk:", core._ex_pick(*scr(3, True)))
    core._on_event(Ev("pointer_move", p[0], p[1])); core.tick()
    shot("ex_2_hover.png")
    # surukle: In3 yukari 60 px
    z_before = float(core._ex_off[3])
    core._on_event(Ev("pointer_down", p[0], p[1], 1))
    for k in range(1, 7):
        core._on_event(Ev("pointer_move", p[0], p[1] - 10 * k)); core.tick()
    core._on_event(Ev("pointer_up", p[0], p[1] - 60, 1)); core.tick()
    print(f"surukleme In3: {z_before:.2f} -> {core._ex_off[3]:.2f} mm (ust {core._ex_off[2]:.2f}, alt {core._ex_off[4]:.2f})")
    shot("ex_3_dragged.png")
    # Shift ile: esit aralik
    p = scr(5)
    core._on_event(Ev("pointer_down", p[0], p[1], 1, ("Shift",)))
    for k in range(1, 5):
        core._on_event(Ev("pointer_move", p[0], p[1] + 10 * k, 0, ("Shift",))); core.tick()
    core._on_event(Ev("pointer_up", p[0], p[1] + 40, 1, ("Shift",))); core.tick()
    d = np.diff(core._ex_off[::-1])
    print(f"Shift surukleme: araliklar {np.round(d, 2).tolist()}")
    # kucuk kup tiki: In5 gizle
    p = scr(5, True)
    canvas.draw()
    key = cu[5].key
    v0 = core.cfg.visible(key)
    core._on_event(Ev("pointer_down", p[0], p[1], 1)); core._on_event(Ev("pointer_up", p[0], p[1], 1)); core.tick()
    print(f"kucuk kup tik {key}: {v0} -> {core.cfg.visible(key)}")
    shot("ex_4_toggled.png")
    core.toggle_explode(False); settle()
    print("geri donus: dielektrik tek govde:", vs._diel_merged(), "tup tabani temiz:", not vs._tube_base, "gizmo gizli:", not core.ex.group.visible)
    shot("ex_5_back.png")
    core.close()


if __name__ == "__main__":
    main()





