import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from PySide6 import QtWidgets, QtCore, QtGui
app = QtWidgets.QApplication([])
from ipcubed import theme
from ipcubed.ctxmenu import build_menu
theme.apply_app_font(app)
for ext, name in ((False, "menu_a"), (True, "menu_b")):
    host = QtWidgets.QWidget(); host.resize(380, 200)
    host.setStyleSheet("background:#1a2230")          # 3D arka plani gibi: yuvarlak kose / saydamlik kontrolu
    menu, A = build_menu(host, True, True, ext)
    menu.setAttribute(QtCore.Qt.WA_DontShowOnScreen, False)
    menu.popup(QtCore.QPoint(20, 20))
    app.processEvents()
    pm = menu.grab()
    bg = QtGui.QPixmap(pm.width() + 40, pm.height() + 40); bg.fill(QtGui.QColor("#33425c"))
    p = QtGui.QPainter(bg); p.drawPixmap(20, 20, pm); p.end()
    bg = bg.scaled(bg.width() * 2, bg.height() * 2, QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation)
    bg.save(os.path.join(os.environ["TEMP"], name + ".png"))
    print(name, pm.width(), pm.height())
    menu.close()

