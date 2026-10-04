import os, re, sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from collections import defaultdict
from kipy import KiCad

ORG = (107.0, 46.0)
NM = 1e-6
side = sys.argv[1] if len(sys.argv) > 1 else "top"
LAY = 40 if side == "top" else 39
s = open(os.environ["TEMP"] + rf"\silk_ref\{'top' if side == 'top' else 'bot'}.svg", encoding="utf-8", errors="ignore").read()
segs = []
for m in re.finditer(r'<path d="([^"]+)"', s):
    d = m.group(1)
    if "A" in d:
        continue
    pts = [tuple(map(float, p)) for p in re.findall(r"([-0-9.]+)\s+([-0-9.]+)", d)]
    for a, b in zip(pts, pts[1:]):
        segs.append((a[0] + ORG[0], a[1] + ORG[1], b[0] + ORG[0], b[1] + ORG[1]))
S = np.array(segs)
print("svg segs", len(S))

def has_match(x1, y1, x2, y2, tol=0.06):
    # iki yonlu eslesme
    d1 = np.abs(S[:, 0] - x1) + np.abs(S[:, 1] - y1) + np.abs(S[:, 2] - x2) + np.abs(S[:, 3] - y2)
    d2 = np.abs(S[:, 0] - x2) + np.abs(S[:, 1] - y2) + np.abs(S[:, 2] - x1) + np.abs(S[:, 3] - y1)
    return min(d1.min(), d2.min()) < tol * 4

b = KiCad(timeout_ms=60000).get_board()
tot = ok = 0
bad = defaultdict(int)
info = {}
for f in b.get_footprints():
    ref = f.reference_field.text.value
    for it in f.definition.items:
        if type(it).__name__ != "BoardShape" or int(it.layer) != LAY:
            continue
        g = it.proto.shape
        if g.WhichOneof("geometry") != "segment":
            continue
        a, c = g.segment.start, g.segment.end
        tot += 1
        if has_match(a.x_nm * NM, a.y_nm * NM, c.x_nm * NM, c.y_nm * NM):
            ok += 1
        else:
            bad[ref] += 1
            info[ref] = (round(f.position.x * NM, 1), round(f.position.y * NM, 1), f.orientation.degrees, int(f.layer))
print(f"{side}: segment eslesen {ok}/{tot}")
for ref, n in sorted(bad.items(), key=lambda kv: -kv[1])[:15]:
    print(" ", ref, n, "fp pos/angle/layer", info[ref])
