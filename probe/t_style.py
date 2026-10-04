import ctypes
from ctypes import wintypes
u = ctypes.windll.user32
u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]; u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
res = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, _):
    b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, b, 256)
    if "3D Live" in b.value:
        r = wintypes.RECT(); u.GetWindowRect(h, ctypes.byref(r))
        print(hex(h), b.value, "style", hex(u.GetWindowLongPtrW(h, -16) & 0xffffffff), "ex", hex(u.GetWindowLongPtrW(h, -20) & 0xffffffff), (r.left, r.top, r.right, r.bottom))
    return True
u.EnumWindows(cb, 0)
