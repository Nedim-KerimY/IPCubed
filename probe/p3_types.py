from kipy import KiCad
from collections import Counter
k = KiCad(timeout_ms=60000)
b = k.get_board()
fps = b.get_footprints()
c = Counter()
fonts = Counter()
vals = []
for f in fps:
    for it in f.definition.items:
        c[(type(it).__name__, int(it.layer) if hasattr(it, "layer") else None)] += 1
    for t in f.texts_and_fields:
        tx = getattr(t, "text", t)
        a = tx.attributes
        fonts[(a.font_name, bool(a.bold), bool(a.italic), type(t).__name__)] += 1
        if "${" in tx.value or "~{" in tx.value or "^{" in tx.value or "_{" in tx.value:
            vals.append(tx.value)
print("fp item types (silk/none):", [x for x in c.most_common(40) if x[0][1] in (39, 40, None)])
print("fp text fonts:", fonts)
bt = b.get_text()
print("board texts fonts:", Counter((t.attributes.font_name, bool(t.attributes.bold)) for t in bt))
print("board markup:", [t.value for t in bt if any(m in t.value for m in ("~{", "${", "^{", "_{"))][:6])
print("fp texts w/ vars/markup:", Counter(vals).most_common(8))
