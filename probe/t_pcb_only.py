import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
import pygfx as gfx
from ipcubed.kicad_source import KiCadSource
from ipcubed.scene_builder import ViewerScene
from ipcubed.camera_rig import CameraRig
from ipcubed.settings import Settings
from rendercanvas.offscreen import RenderCanvas
from PIL import Image


def main():
    cfg = Settings()
    cfg.show_comp_top = cfg.show_comp_bottom = False
    if len(sys.argv) > 1 and sys.argv[1] == "xray":
        cfg.show_inner_copper = True; cfg.substrate_opacity = 0.12
    snap = KiCadSource().snapshot()
    vs = ViewerScene(cfg); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
    W, H = 1800, 1100
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(40, W / H)
    rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg); rig.go("2d", immediate=True)
    canvas.request_draw(lambda: r.render(vs.scene, cam))
    Image.fromarray(np.asarray(canvas.draw())).save(r"C:\Users\erdem\AppData\Local\Temp\pcb_only.png")
    vs.close()


if __name__ == "__main__":
    main()
