from kipy import KiCad
from kipy.board_types import BoardLayer
import kipy.board as kb
k = KiCad(timeout_ms=60000)
b = k.get_board()
def attrs(o): return [a for a in dir(o) if not a.startswith('_') and a not in ('proto', 'clone')]

# stackup
st = b.get_stackup()
print("STACKUP edge/finish:", st.finish if hasattr(st,'finish') else None)
for i, l in enumerate(st.layers):
    print(i, "type", int(l.type), "layer", int(l.layer), "thick", l.thickness, "mat", repr(l.material_name), "user", repr(l.user_name), "enabled", l.enabled,
          "color", str(getattr(l, 'color', None)).replace(chr(10),' '))
    if l.type == 4 or l.type == 3:
        print("   mask/silk attrs", attrs(l.soldermask) if l.type == 4 else attrs(l.silkscreen))
print("stackup attrs", attrs(st))

# yardimcilar
print("Board methods:", [a for a in attrs(b) if 'text' in a.lower() or 'setting' in a.lower() or 'rule' in a.lower() or 'shape' in a.lower() or 'layer' in a.lower()])
print("BoardLayer names:", {n: v for n, v in dict(BoardLayer.items()).items() if 'Silk' in n or 'Mask' in n or 'In1' in n or 'In2_' in n or 'Paste' in n})

# pad mask
p = b.get_pads()[0]
print("pad attrs", attrs(p)); print("padstack attrs", attrs(p.padstack))
print("zone_settings", attrs(p.padstack.zone_settings) if hasattr(p.padstack, 'zone_settings') else None)
print("proto padstack fields:", [f.name for f in p.padstack.proto.DESCRIPTOR.fields])
print("proto pad fields:", [f.name for f in p.proto.DESCRIPTOR.fields])
ps = p.padstack.proto
print("mask settings", ps.solder_mask_settings if hasattr(ps, 'solder_mask_settings') else None)
print("proto padstack:", str(ps)[:600])

# footprint definition items
f = next(f for f in b.get_footprints() if f.reference_field.text.value == "U14") if any(f.reference_field.text.value == "U14" for f in b.get_footprints()) else b.get_footprints()[0]
d = f.definition
print("definition attrs", attrs(d))
items = d.items
from collections import Counter
print("def items", Counter((type(i).__name__, int(i.layer) if hasattr(i, 'layer') else None) for i in items).most_common(12))
print("fp texts", [(t.text.value, int(t.layer)) for t in f.texts_and_fields][:5] if hasattr(f, 'texts_and_fields') else None)
print("get_text_as_shapes?", hasattr(b, 'get_text_as_shapes'), [a for a in dir(kb.Board) if 'text' in a.lower()])

