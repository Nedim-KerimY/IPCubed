import time
from kipy import KiCad
from kipy.board_types import BoardLayer
k = KiCad(timeout_ms=120000)
b = k.get_board()
pads = b.get_pads()
vias = b.get_vias()
print("pads", len(pads), "vias", len(vias))
def attrs(o): return [a for a in dir(o) if not a.startswith('_') and a not in ('clone', 'proto')]
print("outer layer attrs", attrs(pads[0].padstack.front_outer_layers))
fo = pads[0].padstack.front_outer_layers
print(str(fo.proto)[:300].replace("\n", " "))
for L in (3, 4, 34):
    t = time.perf_counter()
    r = b.get_pad_shapes_as_polygons(pads, L)
    dt = time.perf_counter() - t
    n = sum(1 for x in r if x is not None)
    print(f"layer {L}: {dt:.2f}s, non-None {n}/{len(r)}")
t = time.perf_counter()
r = b.get_pad_shapes_as_polygons(pads, BoardLayer.BL_F_Mask)
print("F_Mask", time.perf_counter() - t, sum(1 for x in r if x is not None))
t = time.perf_counter()
r = b.get_pad_shapes_as_polygons(vias if False else pads[:1], 3)
# vias: padstack hakkinda
v = vias[0]
print("via outer", str(v.padstack.front_outer_layers.proto).replace("\n", " "), str(v.padstack.back_outer_layers.proto).replace("\n", " "))
from collections import Counter
print("pad front mask modes", Counter(str(p.padstack.front_outer_layers.proto).replace("\n", " ") for p in pads).most_common(4))
print("via front mask modes", Counter(str(v.padstack.front_outer_layers.proto).replace("\n", " ") for v in vias).most_common(4))
print("pads with 42 in layers", sum(1 for p in pads if 42 in [int(l) for l in p.padstack.layers]), "with 41", sum(1 for p in pads if 41 in [int(l) for l in p.padstack.layers]))
print("net code attr:", pads[0].net.code if hasattr(pads[0].net, 'code') else attrs(pads[0].net))
