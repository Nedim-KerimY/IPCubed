from kipy import KiCad
from collections import Counter
b = KiCad(timeout_ms=60000).get_board()
vias = b.get_vias()
c = Counter()
for v in vias:
    ps = v.padstack
    fo, bo = ps.front_outer_layers.proto, ps.back_outer_layers.proto
    c[(int(v.type), "front_mask_mode", int(fo.solder_mask_mode), "back", int(bo.solder_mask_mode),
       "cover", int(fo.covering_mode), "plug", int(fo.plugging_mode))] += 1
print(c)
st = b.get_stackup()
def col(l):
    c = l.color
    return [a for a in dir(c) if not a.startswith('_')]
for l in st.layers:
    if int(l.type) in (3, 4, 2) and l.layer in (40, 42, 41, 39, 1):
        print(int(l.type), int(l.layer), l.user_name, "color", {a: getattr(l.color, a) for a in col(l) if not callable(getattr(l.color, a))}, "mat", l.material_name)
        break
print("color attrs:", col(st.layers[0]))
for l in st.layers:
    if int(l.type) in (3, 4):
        cc = l.color
        print(int(l.type), int(l.layer), l.user_name, str(cc.proto).replace("\n", " ") if hasattr(cc, 'proto') else cc)
for l in st.layers:
    if int(l.type) == 2:
        print("diel", str(l.color.proto).replace("\n", " ") if hasattr(l.color, 'proto') else l.color, l.material_name); break
