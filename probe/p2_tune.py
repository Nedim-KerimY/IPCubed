import os, re, sys, itertools
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from PIL import Image, ImageDraw
import ipcubed.silk as silk
from ipcubed.kicad_source import KiCadSource

PPM = 16
ORG = (107.0, 46.0)
W, H = 152.88, 89.99
side = "top"
s = open(os.environ["TEMP"] + r"\silk_ref\top.svg", encoding="utf-8", errors="ignore").read()
ref = Image.new("L", (int(W * PPM) + 8, int(H * PPM) + 8), 0)
d = ImageDraw.Draw(ref)
for m in re.finditer(r'<path d="([^"]+)"', s):
    if "A" in m.group(1):
        continue
    pts = [tuple(map(float, p)) for p in re.findall(r"([-0-9.]+)\s+([-0-9.]+)", m.group(1))]
    if len(pts) >= 2:
        d.line([(x * PPM, y * PPM) for x, y in pts], fill=255, width=max(2, int(0.2 * PPM)))
A = np.asarray(ref) > 0

b = KiCadSource().board
raw = b.get_footprints()
results = []
for swap, emf, wf in itertools.product([True, False], [1.0, 1.15, 1.3, 1.45], [1.0, 1.15, 1.3]):
    silk.UPRIGHT_SWAP, silk.EM_FACTOR, silk.WIDTH_FACTOR = swap, emf, wf
    sd = silk.fetch_silk(b, raw)
    img = Image.new("L", ref.size, 0)
    dm = ImageDraw.Draw(img)
    n = 0
    for t in sd.texts[side]:
        g = silk.text_geometry(t)
        if g is None or g.is_empty:
            continue
        for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            if poly.geom_type == "Polygon":
                dm.polygon([((x - ORG[0]) * PPM, (y - ORG[1]) * PPM) for x, y in poly.exterior.coords], fill=255)
        n += 1
    M = np.asarray(img) > 0
    prec = (M & A).sum() / max(1, M.sum())
    results.append((prec, swap, emf, wf, int(M.sum())))
    print(f"swap={swap} em={emf} w={wf}: precision={prec:.3f} my_px={M.sum()}", flush=True)
results.sort(reverse=True)
print("EN IYI:", results[:3])
