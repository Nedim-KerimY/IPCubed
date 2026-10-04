import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
old = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb")).silk
src = KiCadSource(); new = src.snapshot()
n = new.silk
cnt = lambda s: (len(s.shapes["top"]), len(s.shapes["bottom"]), len(s.texts["top"]), len(s.texts["bottom"]), {k: len(v) for k, v in s.extra_shapes.items()}, {k: len(v) for k, v in s.extra_texts.items()})
print("eski", cnt(old)); print("yeni", cnt(n)); print("ayni:", cnt(old) == cnt(n))
t = time.perf_counter(); r = src.refresh_geometry(new); print("refresh_geometry", round(time.perf_counter() - t, 2), "s", cnt(r.silk) == cnt(old))
