"""KiCad 10 (Windows, koyu tema) ile ayni gorunum: renkler, yazi tipi, menu/panel stilleri.

Renkler KiCad'in kendi penceresinden olculdu (yan panel #2b2b2b, arac cubugu #333333, liste #363636); menu ise Windows 11 koyu
acilir menusu olculerinde (KiCad menuleri sistemin yerel menusunu kullanir): yuvarlak kose, 4px ic bosluk, 32px satir.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

BG = "#2b2b2b"            # panel / menu zemini
BG_ALT = "#333333"        # arac cubugu, girdi alanlari
BG_LIST = "#363636"       # liste / sekme icerigi
BORDER = "#454545"
SEP = "#484848"
HOVER = "#3d3d3d"         # menu satiri uzerine gelince
TEXT = "#ffffff"
TEXT_DIM = "#9d9d9d"
ACCENT = "#3a9be6"        # secili/isaretli (KiCad mavi vurgu)
PANEL_BG = "#202020"      # KiCad yan panelinin zemini (liste ve basliklarin ardi)
BAND = "#2b2b2b"          # panel basligi / bolum bandi
LIST_SEL = "#454545"      # liste secili satir
INPUT_BORDER = "#9b9b9b"  # KiCad acilir kutu / giris kenarligi
TAB_BLACK = "#000000"     # secili olmayan sekme
TAB_LINE = "#4d4d4d"

FONT_FAMILIES = ["Segoe UI", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans", "Helvetica Neue", "Arial"]    # Windows, Linux, macOS
FONT_FAMILY = FONT_FAMILIES[0]
MONO_FAMILIES = ["Consolas", "DejaVu Sans Mono", "Menlo", "Monaco", "monospace"]
FONT_PT = 9
FONT_CSS = ", ".join(f'"{f}"' for f in FONT_FAMILIES) + ", sans-serif"


def make_font(px: int | None = None, mono: bool = False, weight=None) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamilies(MONO_FAMILIES if mono else FONT_FAMILIES)
    if px:
        f.setPixelSize(px)
    else:
        f.setPointSize(FONT_PT)
    if weight is not None:
        f.setWeight(weight)
    return f


def apply_app_font(app: QtWidgets.QApplication):
    f = make_font()
    f.setStyleStrategy(QtGui.QFont.PreferAntialias)
    app.setFont(f)


MENU_QSS = f"""
QMenu {{
    background: {BG}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{
    background: transparent; padding: 6px 28px 6px 34px; margin: 0px; border-radius: 4px; min-height: 18px;
}}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::item:disabled {{ color: {TEXT_DIM}; }}
QMenu::icon {{ padding-left: 10px; }}
QMenu::indicator {{ left: 9px; width: 14px; height: 14px; }}
QMenu::separator {{ height: 1px; background: {SEP}; margin: 4px 2px; }}
"""


def style_menu(menu: QtWidgets.QMenu):
    """Yuvarlak, golgesiz, KiCad/Windows koyu menusu."""
    menu.setWindowFlags(menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
    menu.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    menu.setStyleSheet(MENU_QSS)


def ensure_icons() -> dict:
    """QSS icin onay kutusu / ok resimleri (QSS cizgi ile onay isareti ciziemez): KiCad stili, bir kez uretilir."""
    from .paths import config_dir
    d = config_dir() / "icons"
    d.mkdir(parents=True, exist_ok=True)
    out = {}

    def save(name, draw):
        path = d / name
        pm = QtGui.QPixmap(15, 15)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        draw(p)
        p.end()
        pm.save(str(path))
        out[name.split(".")[0]] = str(path).replace("\\", "/")

    def box_on(p):
        p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(ACCENT)); p.drawRoundedRect(0.5, 0.5, 14, 14, 3, 3)
        pen = QtGui.QPen(QtGui.QColor("#ffffff"), 1.8, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        p.setPen(pen); p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolyline([QtCore.QPointF(3.6, 7.8), QtCore.QPointF(6.3, 10.4), QtCore.QPointF(11.2, 4.6)])

    def box_off(p):
        p.setPen(QtGui.QPen(QtGui.QColor("#aaaaaa"), 1.1)); p.setBrush(QtGui.QColor("#242424"))
        p.drawRoundedRect(0.8, 0.8, 13.4, 13.4, 3, 3)

    def chevron(p):
        p.setPen(QtGui.QPen(QtGui.QColor("#cfcfcf"), 1.2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        p.drawPolyline([QtCore.QPointF(3.5, 5.5), QtCore.QPointF(7.5, 9.5), QtCore.QPointF(11.5, 5.5)])

    save("check_on.png", box_on)
    save("check_off.png", box_off)
    save("chevron.png", chevron)
    return out
