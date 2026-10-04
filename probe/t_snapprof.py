import sys, time, cProfile, pstats
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
src = KiCadSource()
pr = cProfile.Profile(); pr.enable(); src.snapshot(); pr.disable()
pstats.Stats(pr).sort_stats("cumulative").print_stats(22)
