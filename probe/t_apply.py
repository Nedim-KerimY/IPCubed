import copy, time, numpy as np
from ipcubed import compat
import pygfx as gfx
from ipcubed.kicad_source import KiCadSource
from ipcubed.scene_builder import ViewerScene
from ipcubed.app import _frame_board
from rendercanvas.offscreen import RenderCanvas
from PIL import Image

def main():
    snap = KiCadSource().snapshot()
    vs = ViewerScene(); vs.load_snapshot(snap)
    while vs.pending(): vs.poll_loading(); time.sleep(.05)
    vs.poll_loading()
    canvas = RenderCanvas(size=(1400, 900), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(40, 1400/900)
    _frame_board(cam, vs)
    vs.scene.add(gfx.Background.from_color("#2b2f36", "#14161a"))
    def shot(p):
        canvas.request_draw(lambda: r.render(vs.scene, cam)); Image.fromarray(np.asarray(canvas.draw())).save(p)
    shot("C:/Users/erdem/AppData/Local/Temp/ap0.png")
    # bir grup buyuk komponenti (en cok instance'li olmayan) kaydir
    fps = [f for f in snap.footprints if f.models and not f.bottom]
    big = [f for f in fps if f.reference.startswith(("U", "J"))][:6]
    moved = []
    for f in big:
        g = copy.deepcopy(f); g.x += 30; moved.append(g)
    print("refs", [m.reference for m in moved], "ok=", vs.apply_footprint_updates(moved))
    shot("C:/Users/erdem/AppData/Local/Temp/ap1.png")
    vs.close()

if __name__ == '__main__':
    main()
