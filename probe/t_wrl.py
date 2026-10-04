import sys, os
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
import pygfx as gfx
from pathlib import Path
from ipcubed.scene_builder import ViewerScene, ModelGroup
from ipcubed.settings import Settings
from ipcubed.model_loader import load_model
from rendercanvas.offscreen import RenderCanvas
from PIL import Image

wrl = Path(sys.argv[1])
vs = ViewerScene(Settings())
vs.mesh_data[wrl] = load_model(wrl)
g = ModelGroup(wrl, False)
g.slots = [("a", 0)]; g.slot_of = {("a", 0): 0}; g.matrices = [np.eye(4)]
vs.groups[(wrl, False)] = g
vs._build_group_mesh(g)
print("opak:", g.mesh is not None, "saydam:", g.mesh_t is not None)
# arkaya opak bir levha: saydamligi gormek icin
plate = gfx.Mesh(gfx.box_geometry(30, 12, 0.5), gfx.MeshStandardMaterial(color="#1c8a4a"))
plate.local.position = (0, 0, -0.3)
vs.root.add(plate)
W, H = 900, 560
canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
r = gfx.WgpuRenderer(canvas)
cam = gfx.PerspectiveCamera(35, W / H)
cam.show_object((0, 0, 0.5, 6), view_dir=(0.2, 0.7, -0.55), up=(0, 0, 1))
canvas.request_draw(lambda: r.render(vs.scene, cam))
Image.fromarray(np.asarray(canvas.draw())).save(sys.argv[2])
vs.close()
