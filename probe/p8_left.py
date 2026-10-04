import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from collections import Counter
from kipy import KiCad
from kipy.board_types import BoardLayer
b = KiCad(timeout_ms=60000).get_board()
EC = int(BoardLayer.BL_Edge_Cuts)
print("Edge.Cuts layer id:", EC)
sh = [s for s in b.get_shapes() if int(s.layer) == EC]
print("board-level Edge.Cuts sekilleri:", Counter(type(s).__name__ for s in sh))
NM = 1e-6
left = []
for s in sh:
    t = type(s).__name__
    if t == "BoardSegment":
        xs = (s.start.x * NM, s.end.x * NM)
        if min(xs) < 111:
            left.append((t, round(s.start.x * NM, 2), round(s.start.y * NM, 2), round(s.end.x * NM, 2), round(s.end.y * NM, 2)))
print("x<111 olan board-level segmentler:", len(left)); print(left[:10])
fp_cnt = Counter()
fp_left = 0
for f in b.get_footprints():
    for it in f.definition.items:
        if hasattr(it, "layer") and int(it.layer) == EC:
            fp_cnt[type(it).__name__] += 1
            fp_left += 1
print("footprint icindeki Edge.Cuts:", dict(fp_cnt), fp_left)
print("kart sinir kutusu (KiCad):", end=" ")
try:
    bb = b.get_item_bounding_box(sh)
    print(bb)
except Exception as e:
    print("yok", e)
