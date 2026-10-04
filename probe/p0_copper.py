import time
from kipy import KiCad
from kipy.board_types import BoardLayer
k = KiCad(timeout_ms=60000)
b = k.get_board()
def attrs(o): return [a for a in dir(o) if not a.startswith('_') and a not in ('proto','clone')]
tr = b.get_tracks()
from collections import Counter
print(Counter(type(t).__name__ for t in tr))
print("Track", attrs(tr[0]))
arc = next((t for t in tr if type(t).__name__ == 'ArcTrack'), None)
if arc: print("Arc", attrs(arc))
print("layers", Counter(int(t.layer) for t in tr))
v = b.get_vias()[0]; print("Via", attrs(v))
print(" via pos/diam", v.position, getattr(v,'diameter',None), v.padstack.type if hasattr(v.padstack,'type') else None)
p = b.get_pads()[0]; ps = p.padstack
print("Pad.padstack", attrs(ps))
print(" copper_layers", [attrs(l)[:12] for l in ps.copper_layers[:1]] if hasattr(ps,'copper_layers') else None)
print(" pad type", p.pad_type, "layers", ps.layers if hasattr(ps,'layers') else None)
cl = ps.copper_layers[0]
print(" cl", cl.layer, cl.shape, cl.size, getattr(cl,'corner_rounding_ratio',None), "angle", ps.angle, "drill", ps.drill.diameter if hasattr(ps,'drill') else None)
z = b.get_zones()
print("zone", attrs(z[0]))
zz = next(x for x in z if x.filled)
print("filled", zz.filled, "layers", zz.layers)
t0 = time.perf_counter()
fp = zz.filled_polygons
print("filled_polygons type", type(fp), (list(fp)[:1] if hasattr(fp,'__iter__') else None), (time.perf_counter()-t0)*1000, "ms")
d = zz.filled_polygons
for key in list(d)[:1]:
    polys = d[key]
    print("layer key", key, "n polys", len(polys), attrs(polys[0]))
    print(" outline nodes", len(polys[0].outline), type(polys[0].outline))
print("soldermask-related:", [a for a in attrs(p) if 'mask' in a.lower()], [a for a in attrs(ps) if 'mask' in a.lower()])
print("pad exp?", p.proto.pad if False else "")
