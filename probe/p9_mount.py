import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed.kicad_source import KiCadSource
s = KiCadSource()
snap = s.snapshot()
cd = snap.copper
big = [p for p in cd.pads if p.drill_w >= 1.5]
print("buyuk delikli pad:", len(big))
for p in big[:8]:
    print(f"  ({p.x:.1f},{p.y:.1f}) drill {p.drill_w:.2f}x{p.drill_h:.2f} npth={p.npth} katmanlar={sorted(p.layers)[:6]}... "
          f"front={None if p.front is None else len(p.front)}pt back={None if p.back is None else len(p.back)}pt")
# KiCad'in ham pad verisi
b = s.board
from kipy.board_types import BoardLayer
pads = b.get_pads()
for p in pads:
    ps = p.padstack
    if ps.drill.diameter.x > 1.5e6:
        print("pad", p.number, "type", int(p.pad_type), "drill", ps.drill.diameter.x * 1e-6, "layers", sorted(int(l) for l in ps.layers)[:8],
              "shape", [ (int(c.layer), int(c.shape), c.size.x*1e-6) for c in ps.copper_layers][:2])
        break
# bu konumda zone/bakir var mi
import shapely
x, y = big[0].x, big[0].y
from ipcubed.copper import _flip
from shapely.geometry import Polygon, Point
pt = Point(x, -y)
for lid, zs in cd.zones.items():
    for out, holes, net in zs:
        pg = Polygon(_flip(out), [_flip(h) for h in holes])
        if not pg.is_valid: pg = pg.buffer(0)
        if pg.contains(pt):
            print("bu noktayi kapsayan zone: katman", lid, "net", cd.net_names[net]); break
