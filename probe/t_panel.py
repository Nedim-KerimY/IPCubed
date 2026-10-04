import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
from ipcubed import theme
theme.apply_app_font(app)
from ipcubed.panel import SettingsWindow
from ipcubed.settings import Settings
from PIL import Image
T = os.environ["TEMP"]
w = SettingsWindow(Settings(), lambda k: None)
w.resize(372, 900)
for i, name in ((0, "pan_a"), (1, "pan_b"), (2, "pan_c"), (3, "pan_d")):
    w.tabs.setCurrentIndex(i); w.show(); app.processEvents(); app.processEvents()
    w.grab().save(os.path.join(T, name + ".png"))
im = Image.open(os.path.join(T, "pan_a.png")).convert("RGB")
im.crop((0, 0, 219, 156)).resize((876, 624), Image.NEAREST).save(os.path.join(T, "pan_a_crop.png"))
print("ok")

