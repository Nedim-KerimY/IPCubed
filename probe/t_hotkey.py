import ctypes, time, sys
from ctypes import wintypes
from PIL import ImageGrab

u = ctypes.windll.user32

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

def key(vk):
    u.keybd_event(vk, 0, 0, 0); time.sleep(0.06); u.keybd_event(vk, 0, 2, 0)

def click(x, y):
    u.SetCursorPos(x, y); time.sleep(0.05)
    u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.04); u.mouse_event(4, 0, 0, 0, 0)

for h in find("Düzenleyici"):
    u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)
    u.ShowWindow(h, 9); u.SetForegroundWindow(h)
time.sleep(1.0)
click(200, 300)            # canvas'in bos siyah bolgesi: odak ver, secimi temizle
time.sleep(0.5)
key(0x33)                  # '3'
print("3 gonderildi")
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 3.5)
ImageGrab.grab(all_screens=True).save(r"C:\Users\erdem\AppData\Local\Temp\hk1.png")
print("yakalandi")
