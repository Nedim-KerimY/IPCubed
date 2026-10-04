import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
import pygfx as gfx
from rendercanvas.offscreen import RenderCanvas
from PIL import Image

W, H = 600, 400
canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
r = gfx.WgpuRenderer(canvas)
scene = gfx.Scene(); scene.add(gfx.Background.from_color("#334466", "#112233"))
cam = gfx.PerspectiveCamera(40, W / H)

# arka plan degil 4 kanalli test dokusu: sol ust kirmizi, sag alt mavi, yari saydam govde
arr = np.zeros((64, 128, 4), np.uint8)
arr[:, :, :] = (40, 200, 40, 160)
arr[:10, :10] = (255, 0, 0, 255)           # sol ust (veri satir 0 = ust)
arr[-10:, -10:] = (0, 0, 255, 255)         # sag alt
tex = gfx.Texture(arr, dim=2)
quad = gfx.Mesh(gfx.plane_geometry(128, 64), gfx.MeshBasicMaterial(map=tex))
quad.material.alpha_mode = "blend"
quad.local.position = (W - 128 / 2 - 10, 64 / 2 + 10, 0)
ov = gfx.Scene(); ov.add(quad)
scam = gfx.ScreenCoordsCamera()


def draw():
    r.render(scene, cam, flush=False)
    r.render(ov, scam)


canvas.request_draw(draw)
Image.fromarray(np.asarray(canvas.draw())).save(sys.argv[1])
print("ok")
