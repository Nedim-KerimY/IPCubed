import os, sys, time
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
    cfg = Settings()
    cfg.show_stats = True
    canvas = RenderCanvas(size=(900, 500), pixel_ratio=1)
    core = ViewerCore(canvas, cfg)
    core.vs.board_bounds = (0, 0, 100, 60)
    core.rig.frame(core.vs.board_bounds, 1.6, cfg)
    for _ in range(20):                       # gercek cizimler: FPS sayaci
        canvas.draw()
    time.sleep(2.3)                           # ornekleyici en az bir kez olcsun
    for _ in range(3):
        canvas.draw()
    Image.fromarray(np.asarray(canvas.draw())).save(os.path.join(os.environ["TEMP"], "stats.png"))
    print("metin:", core._stats_text[0] if core._stats_text else None)
    s = core._sampler
    print(f"cpu {s.cpu:.2f} ram {s.ram_mb:.0f} gpu {s.gpu} vram {s.vram_mb}")
    core.toggle_stats(False)
    print("kapali:", core._sampler is None)
    core.close()


if __name__ == "__main__":
    main()
