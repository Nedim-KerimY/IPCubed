import os, re, sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from PIL import Image, ImageDraw
import ipcubed.silk as silk
from ipcubed.kicad_source import KiCadSource

PPM = 40
ORG = (107.0, 46.0)
W, H = 152.88, 89.99
s = open(os.environ["TEMP"] + r"\silk_ref\top.svg", encoding="utf-8", errors="ignore").read()
ref = Image.new("L", (int(W * PPM) + 8, int(H * PPM) + 8), 0)
d = ImageDraw.Draw(ref)
for m in re.finditer(r'<path d="([^"]+)"', s):
    if "A" in m.group(1):
        continue
    pts = [tuple(map(float, p)) for p in re.findall(r"([-0-9.]+)\s+([-0-9.]+)", m.group(1))]
    if len(pts) >= 2:
        d.line([(x * PPM, y * PPM) for x, y in pts], fill=255, width=2)
A = np.asarray(ref) > 0

b = KiCadSource().board
silk.UPRIGHT_SWAP = False
sd = silk.fetch_silk(b, b.get_footprints())
T = [t for t in sd.texts["top"] if "\n" not in t["value"] and len(t["value"]) >= 3]
P = np.array([(t["x"], t["y"]) for t in sd.texts["top"]])
rows = []
for t in T:
    if t["angle"] % 180 != 0:
        continue
    dist = np.hypot(P[:, 0] - t["x"], P[:, 1] - t["y"])
    if np.sort(dist)[1] < 4.5:        # yalniz izole yazilar
        continue
    n = len(t["value"])
    # pencere: anchor etrafi
    x0 = int((t["x"] - ORG[0] - n * t["sx"] * 1.3) * PPM); x1 = int((t["x"] - ORG[0] + n * t["sx"] * 1.3) * PPM)
    y0 = int((t["y"] - ORG[1] - t["sy"] * 1.6) * PPM); y1 = int((t["y"] - ORG[1] + t["sy"] * 1.6) * PPM)
    win = A[max(y0, 0):y1, max(x0, 0):x1]
    ys, xs = np.nonzero(win)
    if len(xs) < 20:
        continue
    wi, hi = (xs.max() - xs.min()) / PPM, (ys.max() - ys.min()) / PPM
    # silk cizgileri kirletmesin: orani makul olanlar
    if hi > t["sy"] * 1.4 or wi > n * t["sx"] * 1.4:
        continue
    cx = (xs.min() + xs.max()) / 2 / PPM + max(x0, 0) / PPM + ORG[0]
    cy = (ys.min() + ys.max()) / 2 / PPM + max(y0, 0) / PPM + ORG[1]
    rows.append((t["value"], n, t["sx"], t["sy"], t["halign"], t["valign"], wi, hi, cx - t["x"], cy - t["y"]))
print("izole yazi:", len(rows))
a = np.array([(r[6] / (r[1] * r[2]), r[7] / r[3]) for r in rows])
print("width/(n*sx) medyan", np.median(a[:, 0]), " height/sy medyan", np.median(a[:, 1]))
for r in rows[:10]:
    print(r)
by = {}
for r in rows:
    by.setdefault((r[4], r[5]), []).append((r[8], r[9], r[6], r[7], r[1] * r[2], r[3]))
for k, v in by.items():
    v = np.array(v)
    print("halign,valign", k, "n", len(v), "ink center offset (dx,dy) medyan", np.median(v[:, 0]).round(2), np.median(v[:, 1]).round(2),
          " w/h", np.median(v[:, 2] / v[:, 4]).round(2), np.median(v[:, 3] / v[:, 5]).round(2))
