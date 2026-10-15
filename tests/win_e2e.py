"""Windows end-to-end test with a real KiCad 10, driven like a user.

python tests/win_e2e.py --kicad "C:\\Program Files\\KiCad\\10.0" --zip dist/IPCubed-pcm.zip --out e2e-out [--scale 125]

1. first KiCad start: dismiss the setup wizard, then enable the KiCad API in kicad_common.json
2. install the PCM zip into Documents\\KiCad\\10.0\\3rdparty\\plugins\\io_github_ipcubed (what "Install from File" does)
3. open a demo board, find the 3D Live toolbar button on screen and click it
4. accept IPCubed's download dialog, wait for the components and the viewer
5. check: the 3D view covers the PCB canvas, a mouse drag rotates it, '2' hides it, '3' in the canvas shows it again
Screenshots, IPCubed's logs and results.json go to --out. Exit code 1 if a check fails.
"""
import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from ctypes import wintypes as wt
from pathlib import Path

import numpy as np
import psutil
from PIL import Image, ImageGrab

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # physical pixels: screenshots = click coordinates
u = ctypes.windll.user32
H = wt.HWND
for name, args in {"IsWindowVisible": [H], "IsWindow": [H], "GetWindowTextW": [H, wt.LPWSTR, ctypes.c_int],
                   "GetClassNameW": [H, wt.LPWSTR, ctypes.c_int], "GetWindowThreadProcessId": [H, ctypes.POINTER(wt.DWORD)],
                   "GetWindowRect": [H, ctypes.POINTER(wt.RECT)], "ShowWindow": [H, ctypes.c_int], "SetForegroundWindow": [H],
                   "PostMessageW": [H, wt.UINT, wt.WPARAM, wt.LPARAM], "GetDlgItem": [H, ctypes.c_int],
                   "GetWindow": [H, wt.UINT], "GetDpiForWindow": [H]}.items():
    getattr(u, name).argtypes = args
u.GetDlgItem.restype = H
u.GetWindow.restype = H
ENUM = ctypes.WINFUNCTYPE(wt.BOOL, H, wt.LPARAM)
BM_CLICK, WM_CLOSE = 0x00F5, 0x0010

OUT = Path("e2e-out")
T0 = time.monotonic()
results: dict = {"checks": {}, "info": {}}


def log(*a):
    line = f"[{time.monotonic() - T0:7.1f}s] " + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(OUT / "driver.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check(name: str, ok: bool, detail=""):
    results["checks"][name] = {"ok": bool(ok), "detail": detail}
    log(("PASS" if ok else "FAIL"), name, detail)


_shot_n = 0


def shot(name: str):
    global _shot_n
    _shot_n += 1
    p = OUT / f"{_shot_n:02d}-{name}.png"
    try:
        ImageGrab.grab(all_screens=True).save(p)
    except Exception as e:  # noqa: BLE001
        log("screenshot failed:", e)
    return p


# ---------------------------------------------------------------- win32
def windows(parent=None) -> list:
    out = []
    cb = ENUM(lambda h, _: (out.append(h), True)[1])
    if parent:
        u.EnumChildWindows(parent, cb, 0)
    else:
        u.EnumWindows(cb, 0)
    return [h for h in out if h and u.IsWindowVisible(h)]


def title(h) -> str:
    b = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, b, 512)
    return b.value


def cls(h) -> str:
    b = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, b, 256)
    return b.value


def wpid(h) -> int:
    p = wt.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def rect(h):
    r = wt.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def dialog_text(h) -> str:
    return " | ".join(t for c in windows(h) if (t := title(c).strip()) and cls(c) in ("Static", "Edit", "RICHEDIT50W"))


def press(h, labels) -> bool:
    """Click a button of dialog h whose text (without '&') is one of labels. PostMessage: a modal dialog it opens must not block us."""
    want = {x.lower() for x in labels}
    for c in windows(h):
        if cls(c) == "Button" and title(c).replace("&", "").strip().lower() in want:
            u.PostMessageW(c, BM_CLICK, 0, 0)
            return True
    return False


def foreground(h):
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(h)


def click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u.mouse_event(0x2, 0, 0, 0, 0)
    time.sleep(0.05)
    u.mouse_event(0x4, 0, 0, 0, 0)


def drag(x0, y0, x1, y1, steps=25):
    u.SetCursorPos(int(x0), int(y0))
    time.sleep(0.15)
    u.mouse_event(0x2, 0, 0, 0, 0)
    for i in range(1, steps + 1):
        u.SetCursorPos(int(x0 + (x1 - x0) * i / steps), int(y0 + (y1 - y0) * i / steps))
        time.sleep(0.03)
    u.mouse_event(0x4, 0, 0, 0, 0)


def key(vk):
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)


def tree_pids(root_pids) -> set:
    out = set()
    for p in root_pids:
        try:
            pr = psutil.Process(p)
            out.add(p)
            out.update(c.pid for c in pr.children(recursive=True))
        except psutil.Error:
            pass
    return out


def wait(pred, timeout, every=1.0, what=""):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = pred()
        if r:
            return r
        time.sleep(every)
    log("timeout:", what)
    return None


# ---------------------------------------------------------------- KiCad
def kicad_windows(proc):
    pids = tree_pids([proc.pid])
    return [h for h in windows() if wpid(h) in pids]


def main_window(proc):
    for h in kicad_windows(proc):
        if "PCB Editor" in title(h) and rect(h)[2] > 400:
            return h
    return None


def handle_kicad_dialogs(proc) -> bool:
    """Setup wizard / first-run dialogs of KiCad itself (never IPCubed's). True if something was dismissed."""
    done = False
    for h in kicad_windows(proc):
        t = title(h)
        if t == "KiCad Setup":
            log("KiCad setup wizard -> Cancel")
            press(h, ["Cancel"])
            done = True
        elif cls(h) == "#32770" or t in ("Confirmation", "Warning", "Error", "Information"):
            txt = dialog_text(h)
            log(f"KiCad dialog '{t}': {txt[:300]}")
            shot("kicad-dialog")
            press(h, ["Yes", "OK", "Close", "Continue"]) or press(h, ["Cancel", "No"])
            done = True
    return done


def start_pcbnew(kicad: Path, board: Path | None) -> psutil.Popen:
    env = dict(os.environ, IPCUBED_DEBUG="1")
    args = [str(kicad / "bin" / "pcbnew.exe")] + ([str(board)] if board else [])
    log("start:", args)
    return psutil.Popen(args, env=env)


def close_kicad(proc):
    for h in kicad_windows(proc):
        u.PostMessageW(h, WM_CLOSE, 0, 0)
    try:
        proc.wait(20)
    except psutil.TimeoutExpired:
        log("pcbnew did not close -> kill")
        for p in tree_pids([proc.pid]):
            try:
                psutil.Process(p).kill()
            except psutil.Error:
                pass


def canvas_of(top):
    gl = [c for c in windows(top) if cls(c) == "wxGLCanvas"]
    return max((rect(c) for c in gl), key=lambda r: r[2] * r[3]) if gl else None


# ---------------------------------------------------------------- toolbar button
def find_button(top, icon: Path):
    """Template-match the plugin icon in the top toolbar area of the KiCad window. -> (x, y, score) in screen pixels."""
    x, y, w, h = rect(top)
    img = np.asarray(ImageGrab.grab((x, y, x + w, y + min(h, 220)), all_screens=True).convert("RGB"), dtype=np.float32)
    gray = img.mean(axis=2)
    src = Image.open(icon).convert("RGBA")
    bg = float(np.median(gray))               # toolbar background under the icon's transparent pixels
    best = (1e9, 0, 0, 1.0)
    for scale in (1.0, 1.25, 1.5, 2.0):
        s = round(src.width * scale)
        ic = np.asarray(src.resize((s, s), Image.BILINEAR), dtype=np.float32)
        a = ic[..., 3:4] / 255.0
        tpl = (ic[..., :3] * a + bg * (1 - a)).mean(axis=2)
        if gray.shape[0] < s or gray.shape[1] < s:
            continue
        win = np.lib.stride_tricks.sliding_window_view(gray, (s, s))
        for r in range(win.shape[0]):
            d = np.abs(win[r] - tpl).mean(axis=(1, 2))
            c = int(d.argmin())
            if d[c] < best[0]:
                best = (float(d[c]), r, c, scale)
    score, r, c, scale = best
    s = round(src.width * scale)
    Image.fromarray(img[r:r + s, c:c + s].astype(np.uint8)).resize((s * 4, s * 4), Image.NEAREST).save(OUT / "button-match.png")
    return x + c + s // 2, y + r + s // 2, score, scale


# ---------------------------------------------------------------- IPCubed
def ipcubed_procs(kind="viewer"):
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        cmd = " ".join(p.info["cmdline"] or [])
        if "python" not in (p.info["name"] or "").lower():
            continue
        if kind == "viewer" and "-m ipcubed" in cmd and "setup_deps" not in cmd and "spawn_main" not in cmd:
            out.append(p)
        elif kind == "installer" and "setup_deps" in cmd:
            out.append(p)
        elif kind == "any" and ("ipcubed" in cmd or "toggle.py" in cmd):
            out.append(p)
    return out


def ipcubed_dialogs():
    pids = {p.pid for p in ipcubed_procs("any")}
    pids = tree_pids(pids)
    return [h for h in windows() if wpid(h) in pids and (title(h) == "IPCubed" or cls(h) == "#32770")]


def overlay_window():
    pids = tree_pids({p.pid for p in ipcubed_procs("viewer")})
    cands = [h for h in windows() if wpid(h) in pids and rect(h)[2] > 250 and rect(h)[3] > 150 and cls(h) != "#32770"]
    return max(cands, key=lambda h: rect(h)[2] * rect(h)[3]) if cands else None


def collect_logs(kicad: Path):
    dst = OUT / "logs"
    dst.mkdir(exist_ok=True)
    la = Path(os.environ["LOCALAPPDATA"])
    for f in list((la / "ipcubed").glob("*")) + [Path(os.environ["TEMP"]) / "ipcubed.log"]:
        if f.is_file() and f.suffix in (".log", ".json", ".txt", "") and f.stat().st_size < 20_000_000:
            shutil.copy(f, dst / f.name)
    envs = list((la / "KiCad").glob("*/python-environments/io.github.ipcubed"))
    results["info"]["venv"] = [str(e) for e in envs]
    for e in envs:
        py = e / "Scripts" / "python.exe"
        if py.exists():
            r = subprocess.run([str(py), "-m", "pip", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            (dst / "pip-list.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
            (dst / "pyvenv.cfg").write_text((e / "pyvenv.cfg").read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    with open(dst / "windows.txt", "w", encoding="utf-8") as f:
        for h in windows():
            try:
                name = psutil.Process(wpid(h)).name()
            except psutil.Error:
                name = "?"
            f.write(f"{h:#x} pid={wpid(h)} {name} class={cls(h)} rect={rect(h)} title={title(h)!r}\n")


# ---------------------------------------------------------------- display
def set_display(scale: int):
    try:
        import win32api
        import win32con
        dm = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
        dm.PelsWidth, dm.PelsHeight = 1920, 1080
        dm.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
        log("ChangeDisplaySettings 1920x1080 ->", win32api.ChangeDisplaySettings(dm, 0))
    except Exception as e:  # noqa: BLE001
        log("resolution change failed:", e)
    if scale != 100:
        # SPI_SETLOGICALDPIOVERRIDE: steps relative to the recommended scale (100% here): 1 = 125%, 2 = 150%
        steps = {125: 1, 150: 2, 175: 3}.get(scale, 1)
        log("SPI_SETLOGICALDPIOVERRIDE", steps, "->", u.SystemParametersInfoW(0x009F, steps, None, 1))
        time.sleep(3)
    r = subprocess.run([sys.executable, "-c", "import ctypes;u=ctypes.windll.user32;"
                        "u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4));"
                        "print(u.GetDpiForSystem(), u.GetSystemMetrics(0), u.GetSystemMetrics(1))"],
                       capture_output=True, text=True)
    results["info"]["display(dpi,w,h)"] = r.stdout.strip()
    log("display for new processes (dpi, w, h):", r.stdout.strip(), r.stderr.strip()[-200:])


# ---------------------------------------------------------------- main
def run(a):
    kicad = Path(a.kicad)
    set_display(a.scale)

    # 1. first start: the setup wizard writes default settings; then turn the API on
    cfg = Path(os.environ["APPDATA"]) / "kicad" / "10.0"
    p = start_pcbnew(kicad, None)
    wait(lambda: handle_kicad_dialogs(p) and False or (main_window(p) and not any(title(h) == "KiCad Setup" for h in kicad_windows(p))),
         120, 2, "first pcbnew window")
    time.sleep(3)
    handle_kicad_dialogs(p)
    shot("first-start")
    close_kicad(p)
    cfg.mkdir(parents=True, exist_ok=True)
    f = cfg / "kicad_common.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    d.setdefault("api", {})["enable_server"] = True
    f.write_text(json.dumps(d, indent=2), encoding="utf-8")
    log("API enabled in", f)

    # 2. install like PCM "Install from File"
    docs = Path(os.environ["USERPROFILE"]) / "Documents"
    dest = docs / "KiCad" / "10.0" / "3rdparty" / "plugins" / "io_github_ipcubed"
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(a.zip) as z:
        for n in z.namelist():
            if n.startswith("plugins/") and not n.endswith("/"):
                t = dest / n[len("plugins/"):]
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(z.read(n))
    log("plugin installed to", dest)

    # 3. demo board, click 3D Live
    demos = kicad / "share" / "kicad" / "demos"
    src = demos / "pic_programmer"
    if not src.exists():
        src = next(demos.glob("*/*.kicad_pcb")).parent
    board_dir = Path(os.environ["TEMP"]) / "e2e-board"
    shutil.rmtree(board_dir, ignore_errors=True)
    shutil.copytree(src, board_dir)
    board = next(board_dir.glob("*.kicad_pcb"))
    p = start_pcbnew(kicad, board)
    top = wait(lambda: handle_kicad_dialogs(p) and False or main_window(p), 120, 2, "PCB editor")
    check("kicad_opens_board", top is not None)
    if not top:
        return
    u.ShowWindow(top, 3)
    foreground(top)
    time.sleep(15)
    handle_kicad_dialogs(p)
    shot("board")
    results["info"]["kicad_rect"] = rect(top)
    results["info"]["kicad_dpi"] = u.GetDpiForWindow(top)

    icon = dest / "icon-light.png"
    found = None
    for _ in range(24):                       # KiCad may enable the button only after it prepared the plugin's Python
        bx, by, score, sc = find_button(top, icon)
        log(f"button match at ({bx},{by}) score={score:.1f} scale={sc}")
        if score < 25:
            found = (bx, by)
            break
        time.sleep(5)
    check("toolbar_button_found", found is not None, f"score={score:.1f}")
    if not found:
        shot("no-button")
        return
    t_click = time.monotonic()
    foreground(top)
    click(*found)
    log("clicked 3D Live")

    # 4. download dialog
    seen = set()
    dlg = None
    for _ in range(3):
        dlg = wait(lambda: next((h for h in ipcubed_dialogs() if h not in seen), None), 300, 1, "IPCubed dialog")
        if not dlg:
            break
        seen.add(dlg)
        txt = dialog_text(dlg)
        log("IPCubed dialog:", txt[:500])
        shot("ipcubed-dialog")
        if "download" in txt.lower() and ("would you like" in txt.lower() or "requires" in txt.lower()):
            results["info"]["seconds_click_to_dialog"] = round(time.monotonic() - t_click, 1)
            u.PostMessageW(u.GetDlgItem(dlg, 6), BM_CLICK, 0, 0)  # IDYES = Download
            log("pressed Download")
            break
        press(dlg, ["OK", "Yes"])
    check("download_dialog", dlg is not None)
    if not dlg:
        return

    # 5. components + viewer
    t_dl = time.monotonic()
    n = 0
    viewer = None
    while time.monotonic() - t_dl < 900:
        viewer = ipcubed_procs("viewer")
        if viewer:
            break
        for h in ipcubed_dialogs():
            if h not in seen and ("error" in title(h).lower() or "could not" in dialog_text(h).lower()
                                  or "failed" in dialog_text(h).lower()):
                seen.add(h)
                log("IPCubed error dialog:", dialog_text(h)[:800])
                shot("error-dialog")
        if n < 6 and time.monotonic() - t_dl > 10 + 20 * n:
            shot(f"downloading-{n}")
            n += 1
        time.sleep(2)
    results["info"]["seconds_download_to_viewer"] = round(time.monotonic() - t_dl, 1)
    check("viewer_started", bool(viewer))
    if not viewer:
        return
    ov = wait(overlay_window, 240, 1, "3D window")
    check("3d_window_shown", ov is not None)
    if not ov:
        shot("no-3d-window")
        return
    time.sleep(12)
    shot("3d")

    # 6. geometry: the 3D view must cover the PCB canvas
    cv, orr = canvas_of(top), rect(ov)
    results["info"].update(canvas_rect=cv, overlay_rect=orr, overlay_dpi=u.GetDpiForWindow(ov))
    if cv:
        ix = max(0, min(cv[0] + cv[2], orr[0] + orr[2]) - max(cv[0], orr[0]))
        iy = max(0, min(cv[1] + cv[3], orr[1] + orr[3]) - max(cv[1], orr[1]))
        cov = ix * iy / max(1, cv[2] * cv[3])
        check("overlay_covers_canvas", cov > 0.95, f"coverage={cov:.2f} canvas={cv} overlay={orr}")
    # KiCad resized: the overlay must follow
    u.ShowWindow(top, 9)                      # restore
    time.sleep(4)
    cv2, orr2 = canvas_of(top), rect(ov)
    check("overlay_follows_resize", cv2 is not None and all(abs(a_ - b_) <= 4 for a_, b_ in zip(cv2, orr2)),
          f"canvas={cv2} overlay={orr2}")
    u.ShowWindow(top, 3)
    time.sleep(4)
    shot("3d-after-resize")

    # 7. mouse: dragging rotates the view
    x, y, w, h = rect(ov)
    box = (x + w // 4, y + h // 4, x + 3 * w // 4, y + 3 * h // 4)
    before = np.asarray(ImageGrab.grab(box, all_screens=True), dtype=np.float32)
    drag(x + w // 2, y + h // 2, x + w // 2 + w // 5, y + h // 2 + h // 8)
    time.sleep(2)
    after = np.asarray(ImageGrab.grab(box, all_screens=True), dtype=np.float32)
    diff = float(np.abs(after - before).mean())
    check("mouse_drag_rotates", diff > 2.0, f"mean pixel change={diff:.1f}")
    shot("after-drag")

    # 8. keys: 2 -> 2D, 3 in the PCB canvas -> 3D
    foreground(ov)
    time.sleep(0.5)
    key(0x32)
    time.sleep(4)
    hidden = not (u.IsWindow(ov) and u.IsWindowVisible(ov))
    check("key_2_hides_3d", hidden)
    shot("after-key-2")
    if cv:
        foreground(top)
        click(cv[0] + cv[2] - 40, cv[1] + 40)    # focus the canvas (empty corner)
        time.sleep(1)
        key(0x33)
        shown = wait(lambda: overlay_window(), 20, 0.5, "3D after key 3")
        check("key_3_shows_3d", shown is not None)
        time.sleep(3)
        shot("after-key-3")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kicad", required=True)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", default="e2e-out")
    ap.add_argument("--scale", type=int, default=100)
    a = ap.parse_args()
    global OUT
    OUT = Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    results["info"]["scale_requested"] = a.scale
    try:
        run(a)
    except Exception:  # noqa: BLE001
        log("driver crashed:\n" + traceback.format_exc())
        results["checks"]["driver"] = {"ok": False, "detail": traceback.format_exc()[-500:]}
        shot("crash")
    try:
        collect_logs(Path(a.kicad))
    except Exception:  # noqa: BLE001
        log("collect_logs failed:\n" + traceback.format_exc())
    (OUT / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log(json.dumps(results, indent=2, default=str))
    return 0 if results["checks"] and all(c["ok"] for c in results["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
