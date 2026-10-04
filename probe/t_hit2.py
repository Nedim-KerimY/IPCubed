import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np, shapely
from shapely.strtree import STRtree
from ipcubed.geometry import board_clip
from ipcubed.copper import _hole_union, _drill_shape, hole_segs
from shapely.geometry import Point
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
cd = snap.copper
board, outside = board_clip(snap.outline_lines)
t = time.perf_counter()
hs = []
for p in cd.pads:
    if p.drill_w > 0 and p.drill_h > 0: hs.append(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
for x, y, d, dr in cd.vias.xyd:
    if dr > 0: hs.append(Point(x, -y).buffer(dr / 2, quad_segs=hole_segs(dr)))
htree = STRtree(hs); print("agac", round(time.perf_counter() - t, 2))
bl = shapely.get_parts(shapely.boundary(board)); bl = shapely.get_parts(bl); bt = STRtree(list(bl))
allv = 0; t0 = time.perf_counter(); tot = 0; nh = 0
for L, segs in cd.tracks.items():
    s = segs.copy(); s[:, [1, 3]] *= -1
    lines = shapely.linestrings(np.stack([s[:, 0:2], s[:, 2:4]], 1)); w = s[:, 4] / 2
    a = htree.query(lines, predicate="dwithin", distance=w)
    hit = np.zeros(len(s), bool); hit[a[0]] = True
    b = bt.query(lines, predicate="dwithin", distance=w); hit[b[0]] = True
    hit |= ~shapely.contains_xy(board, s[:, 0], s[:, 1])
    tot += len(s); nh += hit.sum()
print(f"strtree: {time.perf_counter()-t0:.2f}s iz={tot} hit={nh}")
