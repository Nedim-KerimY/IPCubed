import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication([])
    from ipcubed import compat, theme
    theme.apply_app_font(app)
    from rendercanvas.offscreen import RenderCanvas
    from ipcubed.core import ViewerCore
    from ipcubed.settings import Settings
    from PIL import Image
    canvas = RenderCanvas(size=(700, 450), pixel_ratio=1)
    core = ViewerCore(canvas, Settings())
    core.vs.board_bounds = (0, 0, 100, 60)
    core.rig.frame(core.vs.board_bounds, 1.6, core.cfg)
    T = os.environ["TEMP"]

    def shot(name):
        core._cube_key = None
        Image.fromarray(np.asarray(canvas.draw())).save(os.path.join(T, name))

    shot("core_a.png")                       # varsayilan 3D, kup acik
    core.rig.goto(None, -90.0, 0)            # arkadan (alttan)
    shot("core_b.png")
    core.cfg.show_view_cube = False
    shot("core_c.png")                       # gizli: yalniz dugme
    print("pitch:", core.rig.s.pitch)
    # kup uzerinde tik: yuz bul
    core.cfg.show_view_cube = True
    core.rig.goto(0.0, 48.0, 0)
    x0 = 700 - 12 - 140
    print("hit merkez:", core._cube_hit(x0 + 74, 12 + 74), "toggle:", core._cube_hit(700 - 12 - 5, 12 + 5), "disinda:", core._cube_hit(10, 10))
    core.close()


if __name__ == "__main__":
    main()
