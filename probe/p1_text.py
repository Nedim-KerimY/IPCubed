from kipy import KiCad
from kipy.board_types import BoardLayer
from kipy.proto.common.types import KiCadObjectType as KOT
from collections import Counter
k = KiCad(timeout_ms=60000)
b = k.get_board()
def attrs(o): return [a for a in dir(o) if not a.startswith('_') and a not in ('proto', 'clone')]

fps = b.get_footprints()
f = fps[5]
print("fp", f.reference_field.text.value, "overrides", attrs(f.overrides) if f.overrides is not None else None)
t = f.reference_field.text
print("text attrs", attrs(t))
print("text:", t.value, t.position, t.layer, t.attributes.size if hasattr(t.attributes, 'size') else attrs(t.attributes))
print("attributes attrs", attrs(t.attributes))
print("text proto:", str(t.proto)[:700])
print("reference_field attrs", attrs(f.reference_field))

# silk sayilari
silk = {40, 39}
cnt = Counter()
for fp in fps:
    for it in fp.definition.items:
        if hasattr(it, 'layer') and int(it.layer) in silk:
            cnt[(type(it).__name__, int(it.layer))] += 1
    for tt in fp.texts_and_fields:
        if int(tt.layer) in silk:
            cnt[("text", int(tt.layer))] += 1
print("fp silk:", cnt)
print("board shapes silk:", Counter((type(s).__name__, int(s.layer)) for s in b.get_shapes() if int(s.layer) in silk))
txt = b.get_items([KOT.KOT_PCB_TEXT])
print("board texts", len(txt), Counter(int(x.layer) for x in txt))
tb = b.get_items([KOT.KOT_PCB_TEXTBOX]); print("textboxes", len(tb))
print("get_text sig", b.get_text.__doc__)
import inspect; print(inspect.signature(b.get_text), inspect.signature(b.get_pad_shapes_as_polygons), inspect.signature(b.expand_text_variables))
# pad shapes as polygons on mask layer
pads = b.get_pads()[:3]
try:
    r = b.get_pad_shapes_as_polygons(pads, BoardLayer.BL_F_Mask)
    print("pad mask polys", type(r), len(r), r[0] if r else None)
    r2 = b.get_pad_shapes_as_polygons(pads, BoardLayer.BL_F_Cu)
    print("pad cu polys", r2[0] if r2 else None)
except Exception as e:
    print("pad polys err", e)
