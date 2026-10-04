import sys, pickle, cProfile, pstats, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
import os
pk = os.path.join(os.environ["TEMP"], "snap.pkl")
if not os.path.exists(pk):
    snap = KiCadSource().snapshot(); pickle.dump(snap, open(pk, "wb"))
snap = pickle.load(open(pk, "rb"))
from ipcubed.copper import build_copper_layer, _hole_union
from ipcubed.body import build_body
cd, st, sd = snap.copper, snap.stack, snap.silk
t=time.perf_counter(); _hole_union(cd); print("hole_union", round(time.perf_counter()-t,2))
l = [x for x in st.copper() if x.layer_id == 4][0]
pr = cProfile.Profile(); pr.enable()
build_copper_layer(cd, l.layer_id, l.z0, l.z1, l.side, sd, None, snap.outline_lines)
pr.disable(); pstats.Stats(pr).sort_stats("cumulative").print_stats(14)
print(len(cd.pads), len(cd.vias.xyd), {k: len(v) for k, v in cd.tracks.items()}, {k: len(v) for k, v in cd.zones.items()})
