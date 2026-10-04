import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
import pygfx as gfx
from ipcubed.kicad_source import KiCadSource
from ipcubed.scene_builder import ViewerScene
from ipcubed.camera_rig import CameraRig, RigState
from ipcubed.settings import Settings
from rendercanvas.offscreen import RenderCanvas
from PIL import Image


def main():
    cfg = Settings()
    cfg.show_comp_top = cfg.show_comp_bottom = False
    snap = KiCadSource().snapshot()
    pads = [p for p in snap.copper.pads if not p.npth and p.drill_w >= 0.8 and abs(p.drill_w - p.drill_h) < 1e-6]
    p = pads[0]
    print("pad:", round(p.x, 2), round(p.y, 2), "delik", p.drill_w)
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
    W, H = 1000, 700
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(40, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg)
    rig.s = RigState((p.x, -p.y, vs.thickness), 5.0 * max(p.drill_w, 1.0), 0.0, 52.0, 35.0)
    rig.apply()
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    Image.fromarray(np.asarray(canvas.draw())).save(r"C:\Users\erdem\AppData\Local\Temp\pth_zoom.png")
    vs.close()


if __name__ == "__main__":
    main()
