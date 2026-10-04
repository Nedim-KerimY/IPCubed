from kipy import KiCad
from collections import Counter
b = KiCad(timeout_ms=60000).get_board()
pads = b.get_pads()
c = Counter()
for p in pads:
    ps = p.padstack
    lay = {int(l) for l in ps.layers}
    c[("front", int(ps.front_outer_layers.proto.solder_mask_mode), 42 in lay)] += 1
    c[("back", int(ps.back_outer_layers.proto.solder_mask_mode), 41 in lay)] += 1
print("pad (yuz, solder_mask_mode, F/B.Mask layers'ta mi):")
for k, v in sorted(c.items()):
    print("  ", k, v)
vias = b.get_vias()
cv = Counter()
for v in vias:
    ps = v.padstack
    cv[(int(v.type), int(ps.front_outer_layers.proto.covering_mode), int(ps.back_outer_layers.proto.covering_mode),
        int(ps.front_outer_layers.proto.plugging_mode), 42 in {int(l) for l in ps.layers})] += 1
print("via (type, front_covering, back_covering, front_plugging, F.Mask layers'ta):", cv)
