import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed.kicad_source import KiCadSource
from ipcubed.copper import build_copper_layer
from ipcubed.geometry import outline_to_polygon, board_clip
from ipcubed.silk import build_silk

snap = KiCadSource().snapshot()
cd, st = snap.copper, snap.stack
board, outside = board_clip(snap.outline_lines)
print("kart:", board.geom_type, round(board.area, 1), tuple(round(v, 1) for v in board.bounds))
tot_out = 0
for l in st.copper()[:3]:
    t = time.perf_counter()
    r = build_copper_layer(cd, l.layer_id, l.z0, l.z1, l.side, snap.silk, None, snap.outline_lines)
    # kart disindaki bakir var mi? vertex'lerin kart disinda kalan orani
    from shapely import points, within
    import shapely
    for key, m in r.items():
        if m is None: continue
        P = m[0][:, :2]
        pts = shapely.points(P[:, 0].astype(float), P[:, 1].astype(float))
        buf = board.buffer(0.02)
        out_n = int((~shapely.contains(buf, pts)).sum())
        print(f"{l.name} {key}: {len(P)} vertex, kart disi {out_n}  ({time.perf_counter()-t:.1f}s)")
st_ = build_silk(snap.silk, "top", st.thickness + 0.012, snap.outline_lines)
P = st_[0][:, :2]
import shapely
pts = shapely.points(P[:, 0].astype(float), P[:, 1].astype(float))
print("silk top: vertex", len(P), "kart disi", int((~shapely.contains(board.buffer(0.02), pts)).sum()))
