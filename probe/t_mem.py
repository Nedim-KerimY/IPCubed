import sys, os, pickle, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
def main():
    from ipcubed import compat
    from ipcubed.scene_builder import ViewerScene
    from ipcubed.settings import Settings
    snap = pickle.load(open(os.path.join(os.environ["TEMP"], "snap.pkl"), "rb"))
    vs = ViewerScene(Settings()); vs.load_snapshot(snap)
    while vs.pending(): vs.poll_loading(); time.sleep(0.05)
    vs.poll_loading()
    mb = lambda n: round(n / 2**20)
    geo = tags = tris = 0
    for k, m in vs.layer_meshes.items():
        g = m.geometry
        geo += sum(a.data.nbytes for a in (g.positions, g.normals) if a is not None)
        tris += g.indices.data.nbytes
    tags = sum(v.nbytes for v in vs.layer_tags.values())
    md = sum(d.positions.nbytes + d.normals.nbytes + d.colors.nbytes + d.indices.nbytes for d in vs.mesh_data.values())
    print(f"katman pos+normal {mb(geo)}MB, indeks {mb(tris)}MB, etiket(tag) {mb(tags)}MB, model verisi {mb(md)}MB")
    gm = 0
    for g in vs.groups.values():
        for m in g.meshes:
            gm += sum(a.data.nbytes for a in (m.geometry.positions, m.geometry.normals, m.geometry.colors) if a is not None)
    print(f"model mesh (CPU kopya) {mb(gm)}MB; vertex sayisi katman: {sum(len(m.geometry.positions.data) for m in vs.layer_meshes.values())}")
    import psutil
    print("islem RSS", mb(psutil.Process().memory_info().rss), "MB")
    vs.close()
if __name__ == "__main__":
    main()
