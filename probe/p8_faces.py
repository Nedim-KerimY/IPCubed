import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from collections import Counter
from ipcubed.kicad_source import KiCadSource
from ipcubed import geometry as g
from shapely.geometry import LineString
from shapely.ops import unary_union, polygonize

s = KiCadSource()
snap = s.snapshot(with_copper=False)
L = snap.outline_lines
print("polyline:", len(L))
xs = [x for l in L for x, y in l]; ys = [y for l in L for x, y in l]
print("tum cizgi sinirlari x %.1f..%.1f y %.1f..%.1f" % (min(xs), max(xs), min(ys), max(ys)))
kinds = Counter(type(sh).__name__ for sh in s.board.get_shapes() if int(sh.layer) == 44)
print("Edge.Cuts sekil turleri (get_shapes):", kinds)
for snapv in (0.001, 0.01, 0.05):
    faces, segs = g._faces(L, snapv)
    print(f"snap {snapv}: yuz sayisi {len(faces)}", [(round(f.area, 1), tuple(round(v) for v in f.bounds)) for f in sorted(faces, key=lambda f: -f.area)[:8]])
# acik ucu olan (komsusuz) uc noktalar
from collections import defaultdict
ends = defaultdict(int)
for l in L:
    for p in (l[0], l[-1]):
        ends[(round(p[0], 3), round(p[1], 3))] += 1
dangling = [p for p, c in ends.items() if c == 1]
print("serbest (komsusuz) uc nokta:", len(dangling), dangling[:12])
# footprint icindeki Edge.Cuts
cnt = 0
for f in s.board.get_footprints():
    for it in f.definition.items:
        if hasattr(it, "layer") and int(it.layer) == 44:
            cnt += 1
print("footprint icinde Edge.Cuts ogesi:", cnt)
