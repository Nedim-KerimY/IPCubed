import sys, faulthandler, time
faulthandler.enable()
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
from ipcubed import scene_builder as sb
src = KiCadSource(); snap = src.snapshot()
cd, st, sd = snap.copper, snap.stack, snap.silk
print("tracks", len(cd.tracks.xyz) if hasattr(cd.tracks, 'xyz') else '?', flush=True)
for name, fn in [("body", lambda: sb._body_worker(snap.outline_lines, st, cd, 0.0, None, sd)),
                 ("silk", lambda: sb._silk_worker(sd, st, snap.outline_lines)),
                 ("extras", lambda: sb._extras_worker(cd, st))] + [
                 (f"cu{l.layer_id}", (lambda l=l: sb._cu_worker(cd, l.layer_id, l.z0, l.z1, l.side, sd, None, snap.outline_lines))) for l in st.copper()]:
    t = time.perf_counter(); print(name, flush=True)
    r = fn(); print("  ok", round(time.perf_counter() - t, 1), "s", flush=True)
