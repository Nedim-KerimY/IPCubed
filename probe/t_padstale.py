import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
from ipcubed.copper import fetch_copper

src = KiCadSource()
b = src.board
cd = fetch_copper(b, [3, 34])
bad = []
for i, p in enumerate(cd.pads):
    arr = p.front if p.front is not None else p.back
    if arr is None or len(arr) < 3:
        continue
    c = (arr.min(0) + arr.max(0)) / 2
    d = float(np.hypot(c[0] - p.x, c[1] - p.y))
    size = float(max(np.ptp(arr[:, 0]), np.ptp(arr[:, 1])))
    if d > max(0.3, size):                 # poligon merkezi pad konumundan pad boyundan fazla uzakta: bayat
        bad.append((i, round(d, 2), round(p.x, 2), round(p.y, 2)))
print("pad:", len(cd.pads), "bayat:", len(bad), bad[:10])
