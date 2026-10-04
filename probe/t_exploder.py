"""Exploder 3D gizmo (PCB'siz, offscreen, yuksek cozunurluk): 12 bakir katman patlatilmis, 2 gizli, biri fare altinda."""
import os, sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
    import pygfx as gfx
    from rendercanvas.offscreen import RenderCanvas
    from ipcubed.exploder import ExploderGizmo
    from ipcubed.lighting import make_environment
    from PIL import Image
    names = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, 11)] + ["B.Cu"]
    g = ExploderGizmo()
    g.build([(n, n, n not in ("In4.Cu", "In7.Cu")) for n in names], corner=(0.0, 0.0), board_size=175.0)
    gap = 4.5
    zs = [gap * (len(names) - 1 - i) for i in range(len(names))]          # ustten alta
    g.place(zs)
    g.set_hover(("big", 3))
    scene = gfx.Scene()
    scene.add(g.group)
    scene.add(gfx.AmbientLight(intensity=0.55))
    sun = gfx.DirectionalLight(intensity=1.8); sun.local.position = (0.35, -0.55, 1.0); scene.add(sun)
    fill = gfx.DirectionalLight(intensity=0.6); fill.local.position = (-0.65, 0.3, 0.55); scene.add(fill)
    scene.environment = make_environment()
    scene.add(gfx.Background.from_color("#46566f", "#0d1119"))
    W, H = 1600, 2000
    canvas = RenderCanvas(size=(W, H), pixel_ratio=1)
    r = gfx.WgpuRenderer(canvas); r.pixel_scale = 2
    cam = gfx.PerspectiveCamera(30, W / H); cam.world.reference_up = (0, 0, 1)
    mid = zs[-1] / 2 + zs[0] / 2
    cam.local.position = (-46.0, -78.0, mid + 34.0)
    cam.look_at((1.5, 0.0, mid))
    canvas.request_draw(lambda: r.render(scene, cam))
    img = np.asarray(canvas.draw())[..., :3]
    path = r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\out\exploder_3d.png"
    Image.fromarray(img).save(path)
    print(path, img.shape)


if __name__ == "__main__":
    main()


