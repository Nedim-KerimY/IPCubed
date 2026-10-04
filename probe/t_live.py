import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
import pygfx as gfx
from ipcubed.kicad_source import KiCadSource
from ipcubed.scene_builder import ViewerScene
from ipcubed.settings import Settings
from ipcubed.camera_rig import CameraRig
from rendercanvas.offscreen import RenderCanvas
from PIL import Image

src = KiCadSource()
t = time.perf_counter(); snap = src.snapshot(); print("snapshot", round(time.perf_counter() - t, 1), "s")
s1 = src.geom_signature(); s2 = src.geom_signature()
print("imza kararli:", s1 == s2, s1)
t = time.perf_counter(); s3 = src.geom_signature(); print("imza", round((time.perf_counter() - t) * 1000), "ms")
t = time.perf_counter(); snap2 = src.refresh_geometry(snap); print("refresh_geometry", round(time.perf_counter() - t, 1), "s")

cfg = Settings()
vs = ViewerScene(cfg)
vs.load_snapshot(snap)
def wait():
    while vs.pending():
        vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
wait()
keys1 = sorted(vs.layer_meshes)
m_before = {k: id(v) for k, v in vs.layer_meshes.items()}
vs.update_geometry(snap2)
# soft: eski katmanlar yenileri gelene dek durmali
print("update sonrasi hemen katman sayisi:", len(vs.layer_meshes), "/", len(keys1))
wait()
keys2 = sorted(vs.layer_meshes)
print("ayni anahtarlar:", keys1 == keys2, "degisen mesh:", sum(1 for k in keys2 if m_before.get(k) != id(vs.layer_meshes[k])))
vs.load_snapshot(snap)          # ayni kart tam yenileme: modeller kaybolmamali
wait()
print("grup mesh:", sum(1 for g in vs.groups.values() if g.meshes), "/", len(vs.groups))
W, H = 1000, 640
canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
r = gfx.WgpuRenderer(canvas); cam = gfx.PerspectiveCamera(35, W / H)
rig = CameraRig(cam); rig.set_aspect(W / H); rig.frame(vs.board_bounds, vs.thickness, cfg); rig.go("3d", immediate=True)
canvas.request_draw(lambda: r.render(vs.scene, cam))
Image.fromarray(np.asarray(canvas.draw())).save(sys.argv[1])
vs.close()
