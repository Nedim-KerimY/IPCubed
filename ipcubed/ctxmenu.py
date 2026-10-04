"""3D gorunum sag tik menusu (KiCad temali). Kabuktan ayri: cevrimdisi (offscreen) render ile test edilebilir."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme


def rec_icon() -> QtGui.QIcon:
    """Kirmizi kayit (canli) noktasi."""
    pm = QtGui.QPixmap(16, 16)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor("#e5322d"))
    p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QtGui.QIcon(pm)


def build_menu(parent, settings_open: bool, embedded: bool, external: bool, cube_on: bool = True, stats_on: bool = False,
               hl_active: bool = False, has_sel: bool = False, can_2d: bool = False, exploded: bool = False):
    """-> (menu, {'settings','refresh','external','return','to2d': QAction | None})"""
    menu = QtWidgets.QMenu(parent)
    theme.style_menu(menu)
    acts: dict = dict.fromkeys(("settings", "cube", "refresh", "stats", "external", "return", "to2d", "nethl", "stophl", "hl2d", "explode"))
    acts["settings"] = menu.addAction("3D Settings…")
    acts["settings"].setCheckable(True)
    acts["settings"].setChecked(settings_open)
    acts["cube"] = menu.addAction("ViewCube")
    acts["cube"].setCheckable(True)
    acts["cube"].setChecked(cube_on)
    acts["refresh"] = menu.addAction("Refresh (full)")
    acts["stats"] = menu.addAction("Performance stats")
    acts["stats"].setCheckable(True)
    acts["stats"].setChecked(stats_on)
    menu.addSeparator()
    acts["explode"] = menu.addAction("Exploded Board View")
    acts["explode"].setCheckable(True)
    acts["explode"].setChecked(exploded)
    if hl_active:
        acts["stophl"] = menu.addAction("Stop Highlighting\tESC")
    else:
        acts["nethl"] = menu.addAction("Net Highlighter")
    if has_sel:
        acts["hl2d"] = menu.addAction("Highlight in 2D")
        acts["hl2d"].setEnabled(can_2d)
    if embedded:
        menu.addSeparator()
        if external:
            acts["return"] = menu.addAction("Return to KiCad")
        else:
            acts["external"] = menu.addAction(rec_icon(), "Open in External Window (LIVE)")
            acts["to2d"] = menu.addAction("Return to 2D\t3")
    return menu, acts
