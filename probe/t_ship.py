"""Hafif anlik goruntu + veri dosyasi yolu ile derleme, tam nesneyle derlemeyle ayni sonucu veriyor mu? (offscreen)"""
import os, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def build(snap):
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    cfg = Settings(); cfg.show_comp_top = cfg.show_comp_bottom = False
    vs = ViewerScene(cfg)
    t = time.perf_counter(); vs.load_snapshot(snap); t_submit = time.perf_counter() - t
    while vs.pending():
        vs.poll_loading(); time.sleep(0.02)
    vs.poll_loading()
    tot = time.perf_counter() - t
    counts = {k: len(m.geometry.indices.data) for k, m in vs.layer_meshes.items()}
    vs.close()
    return counts, t_submit, tot


def main():
    import numpy as np
    from ipcubed import compat  # noqa: F401
    from ipcubed.sync import SyncThread
    T = os.environ["TEMP"]
    snap = pickle.load(open(os.path.join(T, "snap.pkl"), "rb"))
    if not getattr(snap.copper, "fp_index", None):
        snap.copper.fp_index = {}
    snap.poses = {}
    snap.data_path = None
    a, sa, ta = build(snap)
    st = SyncThread.__new__(SyncThread); st.ship_files = True; st._n = 0
    t = time.perf_counter(); lite = st._ship(snap); print(f"dosyaya yazma (senkron surecinde) {time.perf_counter()-t:.2f}s; hafif kopya {len(pickle.dumps(lite))/2**20:.1f} MB (eskiden {len(pickle.dumps(snap))/2**20:.1f} MB)")
    b, sb, tb = build(lite)
    print(f"tam nesne : gonderim (ana surec) {sa*1000:.0f} ms, toplam {ta:.1f}s")
    print(f"dosya yolu: gonderim (ana surec) {sb*1000:.0f} ms, toplam {tb:.1f}s")
    print("ayni mesh'ler:", a == b, "" if a == b else {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)})


if __name__ == "__main__":
    main()
