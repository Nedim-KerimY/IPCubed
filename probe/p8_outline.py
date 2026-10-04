import os, re, subprocess, sys, tempfile
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from PIL import Image, ImageDraw
from kipy import KiCad
from ipcubed.kicad_source import KiCadSource
from ipcubed.geometry import outline_to_polygon

tmp = os.path.join(tempfile.gettempdir(), "kv_copy")
os.makedirs(tmp, exist_ok=True)
pcb = os.path.join(tmp, "copy.kicad_pcb")
b = KiCad(timeout_ms=120000).get_board()
b.save_as(pcb, overwrite=True, include_project=False)          # kopya: acik belge degismez
cli = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
svg = os.path.join(tmp, "edge.svg")
subprocess.run([cli, "pcb", "export", "svg", "--layers", "Edge.Cuts", "--mode-single", "--exclude-drawing-sheet",
                "--page-size-mode", "2", "--black-and-white", "-o", svg, pcb], capture_output=True)
s = open(svg, encoding="utf-8", errors="ignore").read()
m = re.search(r'viewBox="([-0-9. ]+)"', s)
vb = [float(v) for v in m.group(1).split()]
print("svg viewBox:", vb)
paths = []
for pm in re.finditer(r'<path d="([^"]+)"', s):
    pts = [tuple(map(float, p)) for p in re.findall(r"([-0-9.]+)\s+([-0-9.]+)", pm.group(1))]
    if len(pts) >= 2:
        paths.append(pts)
print("svg yol sayisi:", len(paths))

snap = KiCadSource().snapshot(with_copper=False)
poly = outline_to_polygon(snap.outline_lines)
print("benim poligon alan:", round(poly.area, 1), "bounds", tuple(round(v, 1) for v in poly.bounds))
xs = [x for l in snap.outline_lines for x, y in l]; ys = [y for l in snap.outline_lines for x, y in l]
minx, miny = min(xs), min(ys)
PPM = 8
W, H = int(vb[2] * PPM) + 20, int(vb[3] * PPM) + 20
img = Image.new("RGB", (W, H), (0, 0, 0))
d = ImageDraw.Draw(img)
# benim poligon dolgusu (yesil)
def tp(x, y):          # sahne (y yukari, negatif) -> goruntu
    return ((x - minx) * PPM + 10, (-y - miny) * PPM + 10)
for p in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
    d.polygon([tp(x, y) for x, y in p.exterior.coords], fill=(20, 110, 40))
    for r in p.interiors:
        d.polygon([tp(x, y) for x, y in r.coords], fill=(0, 0, 0))
# KiCad Edge.Cuts cizgileri (kirmizi)
for pts in paths:
    d.line([(x * PPM + 10, y * PPM + 10) for x, y in pts], fill=(255, 60, 60), width=2)
img.save(os.path.join(tempfile.gettempdir(), "outline_cmp.png"))
print("kaydedildi", img.size)
