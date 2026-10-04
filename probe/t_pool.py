import sys, os, pickle, faulthandler
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from ipcubed.scene_builder import make_pool
from ipcubed import workers as w
if __name__ == "__main__":
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    for mt in (True, False):
        from concurrent.futures import ProcessPoolExecutor
        p = ProcessPoolExecutor(2, max_tasks_per_child=4) if mt else ProcessPoolExecutor(2)
        l = [x for x in snap.stack.copper() if x.layer_id == 4][0]
        f = p.submit(w._cu_worker, snap.copper, l.layer_id, l.z0, l.z1, l.side, snap.silk, None, snap.outline_lines)
        try: r = f.result(timeout=120); print("max_tasks", mt, "ok", list(r))
        except Exception as e: print("max_tasks", mt, "FAIL", type(e).__name__, e)
        p.shutdown()
