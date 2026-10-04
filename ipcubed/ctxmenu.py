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


def _slider_action(menu, text: str, value: float, cb):
    """Menu icinde etiketli kaydirici (0-100 %). Menu acik kalir; surukleyince cb(deger 0..1) canli cagrilir."""
    w = QtWidgets.QWidget(menu)
    w.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    w.setStyleSheet(
        "QWidget { background: transparent; color: #e8eaed; }"
        f"QSlider::groove:horizontal {{ height: 4px; background: #4a4a4a; border-radius: 2px; }}"
        f"QSlider::sub-page:horizontal {{ background: {theme.ACCENT}; border-radius: 2px; }}"
        "QSlider::handle:horizontal { background: #ffffff; width: 12px; margin: -5px 0; border-radius: 6px; }")
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(58, 4, 14, 4)
    lay.setSpacing(10)
    lab = QtWidgets.QLabel(text)
    sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(int(round(value * 100)))
    sl.setMinimumWidth(110)
    val = QtWidgets.QLabel(f"{sl.value()}%")
    val.setMinimumWidth(34)
    val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

    def changed(v):
        val.setText(f"{v}%")
        if cb is not None:
            cb(v / 100.0)
    sl.valueChanged.connect(changed)
    lay.addWidget(lab); lay.addWidget(sl, 1); lay.addWidget(val)
    act = QtWidgets.QWidgetAction(menu)
    act.setDefaultWidget(w)
    return act


def build_menu(parent, settings_open: bool, embedded: bool, external: bool, cube_on: bool = True, stats_on: bool = False,
               hl_active: bool = False, has_sel: bool = False, can_2d: bool = False, exploded: bool = False,
               show_diel: bool = True, poly_opacity: float = 1.0, on_poly=None, hl_polygons: bool = True):
    """-> (menu, {'settings','refresh','external','return','to2d': QAction | None})"""
    menu = QtWidgets.QMenu(parent)
    theme.style_menu(menu)
    acts: dict = dict.fromkeys(("settings", "cube", "refresh", "stats", "external", "return", "to2d", "nethl", "stophl", "hl2d", "explode", "diel", "hlpoly"))
    acts["settings"] = menu.addAction("3D Settingsâ€¦")
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
    if exploded:
        acts["diel"] = menu.addAction("Show Dielectric")
        acts["diel"].setCheckable(True)
        acts["diel"].setChecked(show_diel)
        menu.addAction(_slider_action(menu, "Polygon Opacity", poly_opacity, on_poly))
    if hl_active:
        acts["stophl"] = menu.addAction("Stop Highlighting\tESC")
        acts["hlpoly"] = menu.addAction(f"Highlight Polygons: {'True' if hl_polygons else 'False'}")
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
