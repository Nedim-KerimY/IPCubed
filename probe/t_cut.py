import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed.kicad_source import KiCadSource
from ipcubed.geometry import outline_to_polygon
from ipcubed.body import build_body

s = KiCadSource()
snap = s.snapshot()
print("kart:", snap.name, "| cizgi/polyline:", len(snap.outline_lines))
poly = outline_to_polygon(snap.outline_lines)
print("kart poligonu:", poly.geom_type, "alan %.1f mm2" % poly.area, "bounds", tuple(round(v, 1) for v in poly.bounds),
      "ic delik/cutout:", sum(len(p.interiors) for p in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly])))
cd, st = snap.copper, snap.stack
t = time.perf_counter()
b = build_body(snap.outline_lines, st, cd, snap.mask_expansion, None, snap.silk)
print("body %.1fs" % (time.perf_counter() - t), {k: len(v[2]) for k, v in b.items()})
holes = sum(1 for p in cd.pads if p.drill_w > 0) + int((cd.vias.xyd[:, 3] > 0).sum()) if len(cd.vias.xyd) else 0
print("kesilen delik sayisi:", holes)
