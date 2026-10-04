import sys, gc
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import psutil
mb = lambda: round(psutil.Process().memory_info().rss / 2**20)
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
print("baslangic", mb())
src = KiCadSource(); snap = src.snapshot(); gc.collect(); print("snapshot sonrasi", mb())
src._raw_fps = {}; gc.collect(); print("raw_fps birakilinca", mb())
snap.silk = None; gc.collect(); print("silk birakilinca", mb())
snap.copper = None; gc.collect(); print("copper birakilinca", mb())
