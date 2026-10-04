import sys, faulthandler
faulthandler.enable()
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed import compat
from ipcubed.kicad_source import KiCadSource
from ipcubed.paths import resolve_model_path
from ipcubed.model_loader import load_model
src = KiCadSource(); snap = src.snapshot()
paths = {}
for fp in snap.footprints:
    for m in fp.models:
        p = resolve_model_path(m.raw_path, snap.project_dir, embedded=snap.embedded)
        if p: paths[p] = 1
print(len(paths), "model")
for p in paths:
    print(p.name, flush=True)
    load_model(p)
