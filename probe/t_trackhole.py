import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
import shapely
from ipcubed.kicad_source import KiCadSource
from ipcubed.copper import build_copper_layer, _hole_union

snap = KiCadSource().snapshot()
cd, st = snap.copper, snap.stack
hu = _hole_union(cd)
for l in st.copper()[:3]:
    t = time.perf_counter()
    r = build_copper_layer(cd, l.layer_id, l.z0, l.z1, l.side, snap.silk, None, snap.outline_lines)
    m = r["cu"]
    P = m[0][:, :2].astype(float)
    # ust kapak vertex'leri (normal +z) delik icinde mi?
    top = m[1][:, 2] > 0.5
    pts = shapely.points(P[top, 0], P[top, 1])
    shrunk = hu.buffer(-0.03)                    # deligin hafif icindeki bolge: orada bakir olmamali
    inside = int(shapely.contains(shrunk, pts).sum())
    print(f"{l.name}: ust vertex {int(top.sum())}, delik ICINDE kalan {inside}  ({time.perf_counter()-t:.1f}s)")
