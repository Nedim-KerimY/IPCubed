import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from concurrent.futures import ProcessPoolExecutor
from ipcubed import workers as w
from ipcubed.paths import resolve_model_path
if __name__ == "__main__":
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    paths = {}
    for fp in snap.footprints:
        for m in fp.models:
            p = resolve_model_path(m.raw_path, snap.project_dir, embedded=snap.embedded)
            if p: paths[p] = 1
    p = ProcessPoolExecutor(2)
    fs = {q: p.submit(w._load_worker, str(q)) for q in paths}
    for q, f in fs.items():
        try: f.result(timeout=300)
        except Exception as e: print("FAIL", q.name, type(e).__name__); break
    else: print("hepsi tamam")
