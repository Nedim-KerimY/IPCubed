"""Sag tik menusu hizalamasi: kaydirici etiketleri / deger sutunu, diger satirlarla ayni hizada mi? (offscreen, piksel olcumu)"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")


def main():
    import numpy as np
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication([])
    from ipcubed import theme
    theme.apply_app_font(app)
    from ipcubed.ctxmenu import build_menu
    out = r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\out\menu_align.png"
    m, A = build_menu(None, False, True, False, exploded=True, poly_opacity=0.6, pth_opacity=0.4)
    m.show(); app.processEvents()
    pm = m.grab(); pm.save(out)
    from PySide6 import QtGui
    img = pm.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :3].astype(int)
    bright = a.sum(2) > 520                                     # acik metin pikselleri
    rows = {}
    for act in m.actions():
        if act.isSeparator():
            continue
        g = m.actionGeometry(act)
        if isinstance(act, QtWidgets.QWidgetAction):
            lab = act.defaultWidget().findChild(QtWidgets.QLabel)
            name = lab.text()
            # widget icindeki etiket: ekran konumu
            x0 = act.defaultWidget().mapTo(m, lab.pos()).x()
            ys = slice(g.top(), g.bottom())
            cols = np.where(bright[ys, :].any(0))[0]
            rows[name] = (int(cols[cols >= x0 - 2].min()) if len(cols) else None, g.top(), g.bottom())
        else:
            ys = slice(g.top(), g.bottom())
            cols = np.where(bright[ys, 30:].any(0))[0] + 30
            rows[act.text().split("\t")[0]] = (int(cols.min()) if len(cols) else None, g.top(), g.bottom())
    for k, v in rows.items():
        print(f"{k:32s} metin sol x = {v[0]}  (satir {v[1]}..{v[2]})")
    # sag kenar: kisayol sutunu (Return to 2D -> '3') ve kaydirici deger etiketi
    for act in m.actions():
        if act.isSeparator():
            continue
        g = m.actionGeometry(act)
        cols = np.where(bright[g.top():g.bottom(), :].any(0))[0]
        print(f"{(act.text() or 'slider').split(chr(9))[0][:24]:26s} en sag acik piksel x = {int(cols.max()) if len(cols) else None}")
    m.hide()


if __name__ == "__main__":
    main()

