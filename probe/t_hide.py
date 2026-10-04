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
    snap = KiCadSource().snapshot()
    vs = ViewerScene(Settings()); vs.load_snapshot(snap)
    while vs.pending():
        vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
    canvas = RenderCanvas(size=(1200, 800), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(40, 1.5)
    rig = CameraRig(cam); rig.set_aspect(1.5); rig.frame(vs.board_bounds, vs.thickness, vs.cfg); rig.go("2d", immediate=True)

    def shot(path):
        canvas.request_draw(lambda: r.render(vs.scene, cam)); a = np.asarray(canvas.draw()); Image.fromarray(a).save(path); return a

    a = shot(r"C:\Users\erdem\AppData\Local\Temp\hide0.png")
    idx = vs.model_index()
    print("model dizini:", [(d["name"], len(d["items"])) for d in idx[:4]], "...", len(idx), "farkli model")
    from pathlib import Path
    def vol(d):
        m = vs.mesh_data.get(Path(d["path"]))
        return 0 if m is None else float(np.prod(m.positions.max(0) - m.positions.min(0)))
    big = max(idx, key=vol)
    vs.set_hidden({(k, mi) for k, mi, _, _ in big["items"]})
    b = shot(r"C:\Users\erdem\AppData\Local\Temp\hide1.png")
    print(f"'{big['name']}' ({len(big['items'])} adet) gizlendi: degisen piksel orani", float((a != b).any(-1).mean()))
    # tek ornek
    one = next(it for it in big["items"] if not it[3])
    vs.set_hidden({(one[0], one[1])})
    c = shot(r"C:\Users\erdem\AppData\Local\Temp\hide2.png")
    print(f"tek ornek ({one[2]}) gizli: degisen piksel orani", float((a != c).any(-1).mean()))
    vs.set_hidden(set())
    d = shot(r"C:\Users\erdem\AppData\Local\Temp\hide3.png")
    print("geri acinca ilk haline esit mi:", bool((a == d).all()))
    vs.close()


if __name__ == "__main__":
    main()

