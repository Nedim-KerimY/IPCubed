from PySide6 import QtWidgets
from ipcubed.panel import SettingsPanel, ColorButton
from ipcubed.settings import Settings
app = QtWidgets.QApplication([])
cfg = Settings()
print("cfg", cfg.mask_color, cfg.copper_color)
p = SettingsPanel(cfg, lambda k: None)
p.resize(260, 700); p.show(); app.processEvents()
img = p.grab().toImage()
for name, b in p._colors.items():
    pos = b.mapTo(p, b.rect().center())
    c = img.pixelColor(pos)
    print(name, getattr(cfg, name), "->", c.name(), "| style:", b.styleSheet()[:60])
