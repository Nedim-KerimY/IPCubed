import math
from kipy import KiCad
k = KiCad(timeout_ms=60000)
b = k.get_board()
fps = {f.reference_field.text.value: f for f in b.get_footprints()}
NM = 1e-6
pads_abs = {}
for p in b.get_pads():
    pads_abs.setdefault(p.parent.value, []).append(p)

for ref in ("U11", "L3", "C26"):
    f = fps[ref]
    print("==", ref, "pos", (f.position.x * NM, f.position.y * NM), "angle", f.orientation.degrees, "layer", int(f.layer))
    items = [i for i in f.definition.items if type(i).__name__ == "BoardShape" and int(i.layer) in (39, 40)]
    xs, ys = [], []
    for it in items:
        g = it.proto.shape
        kind = g.WhichOneof("geometry")
        if kind == "segment":
            xs += [g.segment.start.x_nm * NM, g.segment.end.x_nm * NM]; ys += [g.segment.start.y_nm * NM, g.segment.end.y_nm * NM]
    if xs:
        print(" silk seg bbox x", round(min(xs), 2), round(max(xs), 2), "y", round(min(ys), 2), round(max(ys), 2))
    ab = pads_abs.get(f.id.value, [])
    if ab:
        print(" board pads abs: first", [(p.number, round(p.position.x * NM, 2), round(p.position.y * NM, 2)) for p in ab[:3]])
    dp = list(f.definition.pads)
    print(" definition pads first", [(p.number, round(p.position.x * NM, 2), round(p.position.y * NM, 2)) for p in dp[:3]], "n", len(dp))
