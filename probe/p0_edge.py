from kipy import KiCad
from kipy.board_types import BoardLayer
k = KiCad(timeout_ms=60000)
b = k.get_board()
shapes = b.get_shapes()
print(set(type(s).__name__ for s in shapes))
for s in shapes:
    if s.layer == BoardLayer.BL_Edge_Cuts:
        print(type(s).__name__, [a for a in dir(s) if not a.startswith('_') and a not in ('proto','clone')])
        break
for s in shapes:
    if s.layer == BoardLayer.BL_Edge_Cuts:
        print(type(s).__name__, getattr(s, 'start', None), getattr(s, 'end', None), getattr(s,'mid',None), getattr(s,'center',None))
print("layer enum F_Cu:", int(BoardLayer.BL_F_Cu), "B_Cu:", int(BoardLayer.BL_B_Cu))
fps = b.get_footprints()
from collections import Counter
print(Counter(int(f.layer) for f in fps))
print(b.get_stackup().layers[0].__class__, [a for a in dir(b.get_stackup().layers[0]) if not a.startswith('_')])
print("board origin:", [a for a in dir(b) if 'origin' in a])
print("project:", b.get_project().path if hasattr(b,'get_project') else None)
print("doc:", b.document)
