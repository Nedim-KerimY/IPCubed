import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
from ipcubed import theme
theme.apply_app_font(app)
from ipcubed.viewcube import ViewCube, S
from PIL import Image
c = ViewCube()
views = [(30, 35, None), (30, 35, ("dir", (1, -1, 1))), (30, 35, ("dir", (1, 0, 1))), (200, -35, None), (90, 0, None), (-40, -25, "toggle")]
tiles = []
for yaw, pitch, hov in views:
    c.hover = hov
    a = c.render(yaw, pitch, True, 2.0)
    bg = np.zeros((a.shape[0], a.shape[1], 3), np.float32); bg[:] = (51, 66, 92)
    al = a[..., 3:4] / 255.0
    rgb = (a[..., :3] * al + bg * (1 - al)).astype(np.uint8)
    tiles.append(rgb)
    print(yaw, pitch, hov, "->", c.hit(S / 2, S / 2, yaw, pitch, True))
row = np.concatenate(tiles, axis=1)
Image.fromarray(row).save(os.path.join(os.environ["TEMP"], "cube.png"))
c.hover = None
a = c.render(0, 48, False)
print("gizli: alfa>0 piksel:", int((a[..., 3] > 0).sum()), "toggle hit:", c.hit(S - 5, 5, 0, 48, False), "yuz hit:", c.hit(S / 2, S / 2, 0, 48, False))

