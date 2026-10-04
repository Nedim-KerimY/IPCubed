import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
from ipcubed.copper import fetch_copper
src = KiCadSource(); b = src.board
ids = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 34]
t = time.perf_counter(); cd = fetch_copper(b, ids); print("ilk", round(time.perf_counter() - t, 2), "s", len(cd.pads), "pad, kiid dolu:", sum(1 for p in cd.pads if p.kiid))
# yapay bayatlik: ilk 5 pad'in onceki kaydini 0.5 mm kaydir -> pad 'tasinmis' gorunur, poligon ayni kalir -> yeniden istenmeli
import copy
prev = copy.deepcopy(cd)
for p in prev.pads[:5]:
    p.x += 0.5
t = time.perf_counter(); cd2 = fetch_copper(b, ids, prev=prev); print("prev'li", round(time.perf_counter() - t, 2), "s")
