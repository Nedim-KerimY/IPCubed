import ctypes, time, sys
from ctypes import wintypes
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
from ipcubed.embed import WinEmbedder
exec(open(r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d\probe\t_hotkey.py").read().split("for h in find")[0])  # find/key/click

e = WinEmbedder()
top = e._find_pcbnew()
print("top", top, "pid proc")
for h in find("Düzenleyici"):
    u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)
    u.ShowWindow(h, 9); u.SetForegroundWindow(h)
time.sleep(1.0)
click(200, 300)
time.sleep(0.5)

class GTI(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]
tid = u.GetWindowThreadProcessId(top, None)
i = GTI(); i.cbSize = ctypes.sizeof(GTI)
print("GetGUIThreadInfo", u.GetGUIThreadInfo(tid, ctypes.byref(i)))
print("focus", i.hwndFocus, e._cls(i.hwndFocus) if i.hwndFocus else None, "active", i.hwndActive)
e._locate()
print("canvas_hwnd", e.canvas_hwnd, "focused?", e.canvas_focused())
chain = []
h = i.hwndFocus
while h:
    chain.append((h, e._cls(h)))
    h = u.GetParent(h)
print("focus chain", chain)
