import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np, shapely
from ipcubed.geometry import board_clip
from ipcubed.copper import _hole_union
from ipcubed.prism import capsule_prisms
snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
cd = snap.copper
board, outside = board_clip(snap.outline_lines)
hu = _hole_union(cd)
tot = hit_tot = 0; t_hit = t_caps = 0
for L, segs in cd.tracks.items():
    s = segs.copy(); s[:, [1, 3]] *= -1
    t = time.perf_counter()
    lines = shapely.linestrings(np.stack([s[:, 0:2], s[:, 2:4]], 1))
    hit = shapely.dwithin(lines, hu, s[:, 4] / 2)
    if outside is not None: hit |= shapely.dwithin(lines, outside, s[:, 4] / 2)
    t_hit += time.perf_counter() - t
    t = time.perf_counter(); capsule_prisms(s[~hit][:, :5], 0, 0.035); t_caps += time.perf_counter() - t
    tot += len(s); hit_tot += hit.sum()
print(f"iz {tot}, kirpilacak {hit_tot} ({100*hit_tot/tot:.1f}%), carpisma testi {t_hit:.1f}s, kapsul uretimi {t_caps:.1f}s (tum katmanlar)")
