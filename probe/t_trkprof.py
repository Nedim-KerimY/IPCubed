import sys, os, pickle, time, dataclasses, cProfile, pstats
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed import workers as w
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
cd = snap.copper; cd.fp_index = {}
light = dataclasses.replace(cd, pads=[dataclasses.replace(p, front=None, back=None, inner=None) for p in cd.pads], tracks={3: cd.tracks[3]}, zones={})
l = [x for x in snap.stack.copper() if x.layer_id == 3][0]
t = time.perf_counter(); pickle.loads(pickle.dumps(light)); print("light pickle rt", round((time.perf_counter()-t)*1000), "ms", round(len(pickle.dumps(light))/2**20,1), "MB")
w._track_worker(light, 3, l.z0, l.z1, snap.outline_lines, "top")
pr = cProfile.Profile(); pr.enable(); t = time.perf_counter(); r = w._track_worker(light, 3, l.z0, l.z1, snap.outline_lines, "top"); print("track job", round((time.perf_counter()-t)*1000), "ms"); pr.disable()
t = time.perf_counter(); b = pickle.dumps(r); pickle.loads(b); print("sonuc pickle", round((time.perf_counter()-t)*1000), "ms", round(len(b)/2**20,1), "MB")
pstats.Stats(pr).sort_stats("cumulative").print_stats(8)
