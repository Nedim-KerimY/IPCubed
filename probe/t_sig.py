import sys, time, hashlib
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from kipy import KiCad
from kipy.proto.common.commands.editor_commands_pb2 import GetItems, GetItemsResponse
from kipy.proto.common.types import KiCadObjectType as K

kc = KiCad(timeout_ms=60000)
b = kc.get_board()
print(b.name)


def raw(types):
    c = GetItems()
    c.header.document.CopyFrom(b._doc)
    c.types.extend(types)
    return b._kicad.send(c, GetItemsResponse)


for name, types in [("tracks", [K.KOT_PCB_TRACE, K.KOT_PCB_ARC]), ("vias", [K.KOT_PCB_VIA]),
                    ("zones", [K.KOT_PCB_ZONE]), ("shapes", [K.KOT_PCB_SHAPE]), ("text", [K.KOT_PCB_TEXT, K.KOT_PCB_TEXTBOX]),
                    ("pads", [K.KOT_PCB_PAD])]:
    t = time.perf_counter()
    r = raw(types)
    t1 = time.perf_counter() - t
    t = time.perf_counter()
    data = r.SerializeToString()
    h = hashlib.blake2b(data, digest_size=8).hexdigest()
    t2 = time.perf_counter() - t
    print(f"{name:7s} n={len(r.items):6d} bytes={len(data):9d} fetch={t1*1000:6.1f}ms hash={t2*1000:5.1f}ms {h}")
t = time.perf_counter(); s = b.get_as_string(); print("as_string", len(s), round((time.perf_counter() - t) * 1000), "ms")
