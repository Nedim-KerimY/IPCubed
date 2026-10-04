import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from concurrent.futures import ProcessPoolExecutor
from ipcubed import workers as w
if __name__ == "__main__":
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    cd, st, sd, ol = snap.copper, snap.stack, snap.silk, snap.outline_lines
    p = ProcessPoolExecutor(3, max_tasks_per_child=4)
    jobs = {"body": p.submit(w._body_worker, ol, st, cd, 0.0, None, sd), "silk": p.submit(w._silk_worker, sd, st, ol), "extras": p.submit(w._extras_worker, cd, st)}
    for l in st.copper():
        jobs[f"cu{l.layer_id}"] = p.submit(w._cu_worker, cd, l.layer_id, l.z0, l.z1, l.side, sd, None, ol)
    t = time.perf_counter()
    for k, f in jobs.items():
        try: f.result(timeout=300); print(k, "ok", round(time.perf_counter() - t, 1), flush=True)
        except Exception as e: print(k, "FAIL", type(e).__name__, str(e)[:100], flush=True)
