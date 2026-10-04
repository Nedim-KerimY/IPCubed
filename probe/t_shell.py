import sys
from PySide6 import QtCore, QtWidgets


def main():
    app = QtWidgets.QApplication([])
    from ipcubed.qt_shell import ViewerShell
    sh = ViewerShell(embed=False, show_now=True)

    def probe():
        c = sh.cfg
        print("cfg", c.mask_color, c.copper_color)
        sh.container.show()
        app.processEvents()
        img = sh.panel.grab().toImage()
        for name, b in sh.panel._colors.items():
            pos = b.mapTo(sh.panel, b.rect().center())
            print(name, getattr(c, name), "->", img.pixelColor(pos).name())
        r = sh.core.rig
        print("rig", r.mode, r.s, "aspect", r.aspect, "canvas", sh.canvas.get_logical_size(), sh.canvas.get_pixel_ratio())
        print("cam pos", sh.core.camera.local.position, "fov", sh.core.camera.fov)
        mc = sh.core.vs.board_mesh.geometry.colors.data[0]
        print("board vertex color[0]", mc, "wall?", sh.core.vs.board_mesh.geometry.normals.data[0])
        app.quit()

    QtCore.QTimer.singleShot(14000, probe)
    app.exec()
    sh.core.close()


if __name__ == "__main__":
    main()
