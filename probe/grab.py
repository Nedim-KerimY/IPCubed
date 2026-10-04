"""grab.py out.png [x0,y0,x1,y1] [--front "baslik parcasi"] : ekran goruntusu (opsiyonel pencereyi one al)"""
import ctypes, sys, time
from ctypes import wintypes
from PIL import ImageGrab

u = ctypes.windll.user32
args = sys.argv[1:]
front = None
if "--front" in args:
    i = args.index("--front"); front = args[i + 1]; del args[i:i + 2]

def find(sub):
    res = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, b, 256)
        if sub.lower() in b.value.lower() and u.IsWindowVisible(h):
            res.append(h)
        return True
    u.EnumWindows(cb, 0)
    return res

if front:
    for h in find(front):
        u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)   # alt hilesi: odak izni
        u.ShowWindow(h, 9); u.SetForegroundWindow(h)
    time.sleep(1.2)

img = ImageGrab.grab(all_screens=True)
if len(args) > 1:
    x0, y0, x1, y1 = map(int, args[1].split(","))
    img = img.crop((x0, y0, x1, y1))
img.save(args[0])
print(img.size)
