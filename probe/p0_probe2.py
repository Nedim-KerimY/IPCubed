import time, hashlib
from kipy import KiCad
from kipy.proto.common.types import KiCadObjectType as KOT

def t(label, fn, n=1):
    t0 = time.perf_counter()
    for _ in range(n):
        r = fn()
    dt = (time.perf_counter() - t0) * 1000 / n
    try: ln = len(r)
    except Exception: ln = "-"
    print(f"{label:40s} {dt:9.1f} ms  n={ln}")
    return r

k = KiCad(timeout_ms=60000)
b = k.get_board()
pads = t("get_pads", b.get_pads, 3)
p = pads[0]
print("pad attrs:", [a for a in dir(p) if not a.startswith('_')][:60])
print("pad.id", p.id, "pos", p.position, "parent?", getattr(p, 'parent', None))
t("get_selection", b.get_selection, 5)
fps = b.get_footprints()
f = fps[0]
print("fp attrs:", [a for a in dir(f) if not a.startswith('_')][:80])
ids = [x.id for x in fps[:50]]
t("get_items_by_id x50 fp", lambda: b.get_items_by_id(ids))
t("get_items_by_id x1 fp", lambda: b.get_items_by_id(ids[:1]), 5)
t("get_item_bounding_box x1", lambda: b.get_item_bounding_box(fps[0]), 5)
# footprint instance'in tek basina maliyeti: definition erisimi lokal mi?
t0 = time.perf_counter(); _ = [x.definition for x in fps]; print("definition erisimi (lokal):", (time.perf_counter()-t0)*1000, "ms")

# pad hash maliyeti
def sig():
    h = hashlib.blake2b(digest_size=8)
    for p in b.get_pads():
        h.update(p.position.x.to_bytes(8,'little',signed=True)); h.update(p.position.y.to_bytes(8,'little',signed=True))
    return h.hexdigest()
t("pad-hash polling", sig, 3)
print("pad net:", p.net.name if hasattr(p,'net') else None)
# stackup
s = b.get_stackup()
print("stackup:", [(l.type if hasattr(l,'type') else None, getattr(l,'thickness',None), getattr(l,'material_name',None)) for l in s.layers][:20])
print("board thickness attrs:", [a for a in dir(s) if not a.startswith('_')])
