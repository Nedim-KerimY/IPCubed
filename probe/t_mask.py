import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.body import build_body
from ipcubed.copper import CopperData, _scene_geom
from ipcubed.silk import layer_geometry
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
cd, st = snap.copper, snap.stack
t = time.perf_counter(); cuts = {s: _scene_geom(layer_geometry(snap.silk, 42 if s == "top" else 41)) for s in ("top", "bottom")}; print("cuts", round(time.perf_counter() - t, 2))
small = CopperData(pads=cd.pads, vias=cd.vias, tent_rules=cd.tent_rules)
t = time.perf_counter(); r = build_body(snap.outline_lines, st, small, 0.0, None, None, only_mask=True, cuts=cuts); print("yalniz maske", round(time.perf_counter() - t, 2), "s", list(r))
t = time.perf_counter(); r = build_body(snap.outline_lines, st, cd, 0.0, None, snap.silk); print("tam govde", round(time.perf_counter() - t, 2), "s")
