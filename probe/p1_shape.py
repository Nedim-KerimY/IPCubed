from kipy import KiCad
from collections import Counter
k = KiCad(timeout_ms=60000)
b = k.get_board()
def attrs(o): return [a for a in dir(o) if not a.startswith('_') and a not in ('clone',)]
fps = b.get_footprints()
seen = {}
for fp in fps[:200]:
    for it in fp.definition.items:
        if type(it).__name__ == 'BoardShape' and int(it.layer) in (39, 40):
            kind = it.proto.shape.WhichOneof('geometry') if hasattr(it.proto, 'shape') else None
            if kind not in seen:
                seen[kind] = it
print("geometry kinds:", list(seen))
for kind, it in seen.items():
    print("==", kind, [a for a in attrs(it) if a != 'proto'])
    print(str(it.proto)[:420].replace("\n", " "))
# via tenting
v = b.get_vias()[0]
print("via attrs", attrs(v)); print("via padstack proto:", str(v.padstack.proto)[:500].replace("\n", " "))
print("front/back outer", v.padstack.front_outer_layers, v.padstack.back_outer_layers)
p = b.get_pads()[0]
print("pad outer layers", p.padstack.front_outer_layers, p.padstack.back_outer_layers)
print("fp overrides solder_mask:", [ (f.reference_field.text.value, f.overrides.solder_mask) for f in fps if f.overrides.solder_mask is not None and str(f.overrides.solder_mask) != 'None'][:4])
ov = fps[0].overrides
print("overrides attrs", attrs(ov.solder_mask) if ov.solder_mask is not None else None)
