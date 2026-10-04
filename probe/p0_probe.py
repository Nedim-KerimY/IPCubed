"""Faz 0: kipy API'sinin neyi ne hizla verdigini olc."""
import time
from kipy import KiCad

def t(label, fn):
    t0 = time.perf_counter()
    r = fn()
    dt = (time.perf_counter() - t0) * 1000
    try:
        n = len(r)
    except Exception:
        n = "-"
    print(f"{label:34s} {dt:9.1f} ms   n={n}")
    return r

k = KiCad(timeout_ms=60000)
print("KiCad", k.get_version())
board = t("get_board", k.get_board)
print("board name:", board.name)

fps = t("get_footprints", board.get_footprints)
tracks = t("get_tracks", board.get_tracks)
vias = t("get_vias", board.get_vias)
pads = t("get_pads", board.get_pads)
zones = t("get_zones", board.get_zones)
shapes = t("get_shapes", board.get_shapes)
t("get_stackup", board.get_stackup)

# Edge.Cuts
from kipy.board_types import BoardLayer
edge = [s for s in shapes if s.layer == BoardLayer.BL_Edge_Cuts]
print("Edge.Cuts shapes:", len(edge))
for s in edge[:5]:
    print("  ", type(s).__name__)

# Footprint ornek
fp = fps[0]
print("fp0:", fp.reference_field.text.value, fp.position, fp.orientation, fp.layer)
d = fp.definition
print("models:", [(m.filename, m.offset, m.rotation, m.scale, m.visible) for m in d.models])

# model istatistikleri
from collections import Counter
c = Counter()
nomodel = 0
t0 = time.perf_counter()
for f in fps:
    ms = f.definition.models
    if not ms:
        nomodel += 1
    for m in ms:
        c[m.filename] += 1
print(f"model tarama {1000*(time.perf_counter()-t0):.1f} ms; benzersiz model={len(c)}, modelsiz fp={nomodel}")
for fn, n in c.most_common(12):
    print(f"  {n:4d} x {fn}")

# hafif ozet (diff icin) ne kadar suruyor
t("get_items(FOOTPRINT)", lambda: board.get_items([__import__('kipy.proto.common.types', fromlist=['x']).KiCadObjectType.KOT_PCB_FOOTPRINT]))
