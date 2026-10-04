"""Yuzey kaplama turu degisince (stack plani) renk aninda degisiyor mu, geometri yeniden uretilmeden? (offscreen)"""
import copy, dataclasses, os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    from ipcubed import compat  # noqa: F401
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    from ipcubed.sync import SyncThread
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}; snap.data_path = None
    snap.stack.finish = "ENIG"
    st = SyncThread.__new__(SyncThread); st.ship_files = True; st._n = 0
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False; cfg.pad_color = None
    vs = ViewerScene(cfg)
    vs.load_snapshot(st._ship(snap))
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    fin = [k for k in vs.layer_meshes if vs._kind(k) == "finish"]
    c0 = vs.layer_meshes[fin[0]].material.color.hex
    ids0 = {k: id(m) for k, m in vs.layer_meshes.items()}
    s2 = dataclasses.replace(snap, stack=copy.deepcopy(snap.stack)); s2.stack.finish = "HAL SnPb"
    plan = {"cu": set(), "tracks": set(), "zones": set(), "body": False, "body_tiles": set(), "vias": False,
            "barrel": False, "silk": False, "pads": False, "full": False, "stack": True}
    t = time.perf_counter()
    vs.update_partial(st._ship(s2), plan); vs.apply_settings()
    dt = time.perf_counter() - t
    c1 = vs.layer_meshes[fin[0]].material.color.hex
    changed = [k for k, m in vs.layer_meshes.items() if ids0.get(k) != id(m)]
    print(f"{fin[0]}: {c0} -> {c1} in {dt*1000:.1f} ms, rebuilt: {changed}, pending: {vs.pending()}")
    vs.close()


if __name__ == "__main__":
    main()
