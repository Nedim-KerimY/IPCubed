import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from kipy import KiCad
from kipy.proto.common.commands.editor_commands_pb2 import GetItems, GetItemsResponse
from kipy.proto.common.types import KiCadObjectType as K
from kipy.proto.board import board_types_pb2 as bt
kc = KiCad(timeout_ms=60000); b = kc.get_board()
c = GetItems(); c.header.document.CopyFrom(b._doc); c.types.extend([K.KOT_PCB_TRACE, K.KOT_PCB_ARC])
t = time.perf_counter(); r = b._kicad.send(c, GetItemsResponse); t1 = time.perf_counter() - t
t = time.perf_counter()
n = 0; rows = []
tr = bt.Track(); ar = bt.Arc()
for it in r.items:
    if it.Is(tr.DESCRIPTOR):
        it.Unpack(tr); rows.append((tr.start.x_nm, tr.start.y_nm, tr.end.x_nm, tr.end.y_nm, tr.width.value_nm, int(tr.layer), tr.net.name))
    else:
        it.Unpack(ar); rows.append((ar.start.x_nm, ar.start.y_nm, ar.mid.x_nm, ar.mid.y_nm, ar.end.x_nm, ar.end.y_nm, ar.width.value_nm, int(ar.layer), ar.net.name))
print("fetch", round(t1, 2), "unpack", round(time.perf_counter() - t, 2), len(rows), rows[0])
t = time.perf_counter(); x = b.get_tracks(); print("get_tracks", round(time.perf_counter() - t, 2))

