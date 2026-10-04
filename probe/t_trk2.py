import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from ipcubed.kicad_source import KiCadSource
from ipcubed import workers as w
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
src = KiCadSource()
t = time.perf_counter(); s2, ch = src.refresh_tracks(snap); print(f"refresh_tracks (KiCad'den) {time.perf_counter()-t:.2f}s degisen katman: {ch}")
l = [x for x in snap.stack.copper() if x.layer_id == 5][0]
t = time.perf_counter(); r = w._track_worker(snap.copper, l.layer_id, l.z0, l.z1, snap.outline_lines); dt = time.perf_counter() - t
print(f"iz mesh (katman 5, {len(snap.copper.tracks[5])} iz): {dt:.2f}s, ucgen {len(r['cut:5'][2])}")
t = time.perf_counter(); r2 = w._cu_worker(snap.copper, l.layer_id, l.z0, l.z1, l.side, snap.silk, None, snap.outline_lines); print(f"tam katman {time.perf_counter()-t:.2f}s tr={len(r2['cut:5'][2])} cu={len(r2['cu:5'][2])}")
