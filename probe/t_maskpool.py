import sys, os, pickle, time, dataclasses
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
def main():
    from ipcubed.scene_builder import make_pool
    from ipcubed import workers as w
    from ipcubed.copper import _scene_geom
    from ipcubed.silk import layer_geometry
    s = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb")); s.copper.fp_index = {}
    cuts = {sd: _scene_geom(layer_geometry(s.silk, 42 if sd == "top" else 41)) for sd in ("top", "bottom")}
    small = dataclasses.replace(s.copper, tracks={}, zones={})
    pool = make_pool(1)
    for i in range(3):
        t = time.perf_counter()
        pool.submit(w._mask_worker, s.outline_lines, s.stack, small, 0.0, None, cuts, None, [10]).result()
        print(f"maske isi {i}: {(time.perf_counter()-t)*1000:.0f} ms")
    pool.shutdown()
if __name__ == "__main__":
    main()
