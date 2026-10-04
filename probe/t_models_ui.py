import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
from ipcubed.panel import SettingsWindow
from ipcubed.settings import Settings

idx = [
    dict(name="0402 cap.STEP", path="x", items=[("k%d" % i, 0, f"C{i}", i % 2 == 0) for i in (1, 2, 10, 3)]),
    dict(name="BM04B-GHS-TBT.step", path="y", items=[("u1", 0, "J1", False), ("u2", 0, "J2", False)]),
    dict(name="RCLAMP.step", path="z", items=[("d1", 0, "D5", True)]),
]
got = []
w = SettingsWindow(Settings(), lambda k: None, None, lambda h: got.append(set(h)))
w.set_models(idx, {("k2", 0)})
t = w.model_tree
print("gruplar:", t.topLevelItemCount(), "| ust durum (ilk grup, 1 gizli cocuk):", t.topLevelItem(0).checkState(0))
# grup isaretini kaldir -> hepsi gizlenir
t.topLevelItem(1).setCheckState(0, QtCore.Qt.Unchecked)
print("grup kapatinca gizli:", sorted(got[-1]))
# tek cocuk ac
t.topLevelItem(1).child(0).setCheckState(0, QtCore.Qt.Checked)
print("tek cocuk acinca gizli:", sorted(got[-1]), "| grup durumu:", t.topLevelItem(1).checkState(0))
# arama
w.model_search.setText("c10")
vis = [(t.topLevelItem(i).text(0), [t.topLevelItem(i).child(j).text(0) for j in range(t.topLevelItem(i).childCount()) if not t.topLevelItem(i).child(j).isHidden()]) for i in range(t.topLevelItemCount()) if not t.topLevelItem(i).isHidden()]
print("arama 'c10':", vis)
w.model_search.setText("")
w._set_visible_models(False)
print("hepsini gizle ->", len(got[-1]), "gizli;", w.model_info.text())
