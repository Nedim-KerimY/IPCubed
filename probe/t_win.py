"""pcbnew penceresini ve alt pencerelerini (canvas / appearance paneli) bul."""
import ctypes
from ctypes import wintypes
import psutil

u = ctypes.windll.user32
pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower().startswith("pcbnew")}
print("pcbnew pids", pids)

top = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def enum_top(h, _):
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value in pids and u.IsWindowVisible(h):
        top.append(h)
    return True
u.EnumWindows(enum_top, 0)

def title(h):
    b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, b, 256); return b.value
def cls(h):
    b = ctypes.create_unicode_buffer(256); u.GetClassNameW(h, b, 256); return b.value
def rect(h):
    r = wintypes.RECT(); u.GetWindowRect(h, ctypes.byref(r)); return (r.left, r.top, r.right - r.left, r.bottom - r.top)

for h in top:
    print("TOP", hex(h), repr(title(h)), cls(h), rect(h))
    kids = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_child(c, _):
        if u.IsWindowVisible(c):
            kids.append(c)
        return True
    u.EnumChildWindows(h, enum_child, 0)
    big = sorted(kids, key=lambda c: -(rect(c)[2] * rect(c)[3]))[:14]
    for c in big:
        print("   child", hex(c), cls(c), repr(title(c))[:30], rect(c))
