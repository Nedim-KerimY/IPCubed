from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
from ipcubed.embed import WinEmbedder
e = WinEmbedder()
loc = e._locate()
print(loc)
tab, content = loc["tab"], loc["content"]
hh = content[1] - tab[1]
print("header h", hh, "edge", e._detect_tab_edge(tab, hh) - tab[0])
from PIL import ImageGrab
img = ImageGrab.grab(bbox=(tab[0], tab[1], tab[0] + tab[2], tab[1] + hh), all_screens=True).convert("RGB")
img = img.resize((img.width * 4, img.height * 4)); img.save(r"C:\Users\erdem\AppData\Local\Temp\strip.png")
w, h = img.size
print([img.getpixel((x, h // 2)) for x in (5, 400, 700, 800, 850)])
