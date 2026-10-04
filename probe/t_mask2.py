import sys, os, pickle, time, cProfile, pstats
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.body import build_body
from ipcubed.copper import CopperData, _scene_geom
from ipcubed.silk import layer_geometry
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
cd, st = snap.copper, snap.stack
cuts = {s: _scene_geom(layer_geometry(snap.silk, 42 if s == "top" else 41)) for s in ("top", "bottom")}
small = CopperData(pads=cd.pads, vias=cd.vias, tent_rules=cd.tent_rules)
build_body(snap.outline_lines, st, small, 0.0, None, None, only_mask=True, cuts=cuts)
pr = cProfile.Profile(); pr.enable(); build_body(snap.outline_lines, st, small, 0.0, None, None, only_mask=True, cuts=cuts); pr.disable()
pstats.Stats(pr).sort_stats("tottime").print_stats(8)
