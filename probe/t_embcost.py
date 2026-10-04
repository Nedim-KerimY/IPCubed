import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed.embed import make_embedder
e = make_embedder()
t = time.perf_counter()
for _ in range(20): e.editor_present()
print("editor_present ms:", round((time.perf_counter() - t) / 20 * 1000, 2))
t = time.perf_counter()
for _ in range(2000): e.hotkey_pressed()
print("hotkey_pressed us:", round((time.perf_counter() - t) / 2000 * 1e6, 1))
