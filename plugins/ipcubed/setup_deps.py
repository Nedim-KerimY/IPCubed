"""IPCubed bilesenlerini (deps.txt) kullanici onayiyla kur. YALNIZCA standart kutuphane: bilesenler henuz yokken calisir.

KiCad eklentinin requirements.txt'sini sormadan kurar; bu yuzden o dosya bos, agir bilesenler (Qt, OpenCascade, wgpu...)
3D Live dugmesine ilk basista bir onay diyalogundan sonra eklentinin sanal ortamina (sys.prefix) kurulur.

  python -m ipcubed.setup_deps --install [--show]    (diyalogdan sonra arka planda calisan kurucu)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPS = HERE / "deps.txt"
TITLE = "IPCubed"


def _deps_hash() -> str:
    return hashlib.sha256(DEPS.read_bytes()).hexdigest()[:16]


def _marker() -> Path:
    return Path(sys.prefix) / "ipcubed-components.json"        # sanal ortamla birlikte silinir


def _lock() -> Path:
    return Path(sys.prefix) / "ipcubed-installing.lock"


def log_path() -> Path:
    from .ctl import config_dir
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "install.log"


def ready() -> bool:
    """Bilesenler bu deps.txt surumuyle kurulmus mu? (Hizli: ice aktarma yok.)"""
    try:
        return json.loads(_marker().read_text()).get("deps") == _deps_hash()
    except (OSError, ValueError):
        return False


def _update() -> bool:
    """Eski bir deps.txt ile kurulmus (eklenti guncellendi)."""
    return _marker().exists()


def download_mb() -> int | None:
    try:
        sizes = json.loads((HERE / "dep_sizes.json").read_text())["download_mb"]
    except (OSError, ValueError, KeyError):
        return None
    key = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    return sizes.get(key)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)         # SYNCHRONIZE
        if not h:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == 0x102    # WAIT_TIMEOUT: hala calisiyor
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def installing() -> bool:
    try:
        pid = int(_lock().read_text().strip())
    except (OSError, ValueError):
        return False
    return _pid_alive(pid)


# ------------------------------------------------------------------------------ diyaloglar (Qt yok: platformun kendi araci)
def _have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def ask(text: str, yes: str = "Download", no: str = "Cancel") -> bool:
    """Evet/Hayir diyalogu. Hicbir diyalog araci yoksa (cok nadir, Linux) True: aksi halde eklenti hic kullanilamaz."""
    if sys.platform == "win32":
        import ctypes
        MB_YESNO, MB_ICONQUESTION, MB_SETFOREGROUND, MB_TOPMOST = 0x4, 0x20, 0x10000, 0x40000
        return ctypes.windll.user32.MessageBoxW(None, text, TITLE, MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST) == 6
    if sys.platform == "darwin":
        script = (f'display dialog {json.dumps(text)} with title {json.dumps(TITLE)} '
                  f'buttons {{{json.dumps(no)}, {json.dumps(yes)}}} default button {json.dumps(yes)} with icon note')
        return subprocess.run(["osascript", "-e", script], capture_output=True).returncode == 0
    if _have("zenity"):
        return subprocess.run(["zenity", "--question", "--title", TITLE, "--text", text, "--ok-label", yes,
                               "--cancel-label", no, "--width", "420"]).returncode == 0
    if _have("kdialog"):
        return subprocess.run(["kdialog", "--title", TITLE, "--yesno", text, "--yes-label", yes, "--no-label", no]).returncode == 0
    r = _tk(text, ask=True)
    if r is not None:
        return r
    if _have("xmessage"):
        return subprocess.run(["xmessage", "-center", "-title", TITLE, "-buttons", f"{yes}:0,{no}:1", text]).returncode == 0
    return True


def info(text: str, error: bool = False):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, (0x10 if error else 0x40) | 0x10000 | 0x40000)
    elif sys.platform == "darwin":
        script = f'display dialog {json.dumps(text)} with title {json.dumps(TITLE)} buttons {{"OK"}} default button "OK"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
    elif _have("zenity"):
        subprocess.run(["zenity", "--error" if error else "--info", "--title", TITLE, "--text", text, "--width", "420"])
    elif _have("kdialog"):
        subprocess.run(["kdialog", "--title", TITLE, "--error" if error else "--msgbox", text])
    elif _tk(text, ask=False) is None and _have("xmessage"):
        subprocess.run(["xmessage", "-center", "-title", TITLE, "-buttons", "OK:0", text])


def _tk(text: str, ask: bool):
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
    except Exception:  # noqa: BLE001  tkinter yok ya da ekran yok
        return None
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        if ask:
            return messagebox.askyesno(TITLE, text, parent=root)
        messagebox.showinfo(TITLE, text, parent=root)
        return True
    finally:
        root.destroy()


# ------------------------------------------------------------------------------ 3D Live dugmesi
def ensure(show: bool) -> bool:
    """Bilesenler hazirsa True. Degilse kullaniciya sor, onaylarsa arka planda kurmaya basla (bitince 3D acilir) -> False."""
    if ready():
        return True
    if installing():
        info("IPCubed is still downloading its components.\n\nThe 3D view will open automatically when it is done.\n\n"
             f"Progress: {log_path()}")
        return False
    mb = download_mb()
    size = f"about {mb} MB" if mb else "a few hundred MB"
    head = ("This IPCubed update requires updated components to run" if _update()
            else "IPCubed requires additional components to run")
    if not ask(f"{head} ({size} download: Qt, OpenCascade, wgpu...).\n\n"
               "Would you like to download them now?\n\n"
               "This is needed only once. The 3D view opens automatically when it is done."):
        return False
    _spawn_installer(show)
    return False


def _spawn_installer(show: bool):
    cmd = [sys.executable, "-m", "ipcubed.setup_deps", "--install"] + (["--show"] if show else [])
    kw: dict = {"cwd": str(HERE.parent), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000           # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
        try:
            subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)     # BREAKAWAY_FROM_JOB: KiCad'in is nesnesinden cik
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)


def install(show: bool) -> int:
    """Arka plan kurucusu: pip ile deps.txt'yi bu sanal ortama kur; basarida isaret dosyasi + 3D'yi ac, hatada diyalog."""
    lock = _lock()
    lock.write_text(str(os.getpid()))
    log = log_path()
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} IPCubed components -> {sys.prefix}\n")
            f.flush()
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                                "--only-binary", ":all:", "--progress-bar", "off", "-r", str(DEPS)],
                               stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            f.write(f"\n{time.strftime('%H:%M:%S')} pip exit code {r.returncode}\n")
        if r.returncode != 0:
            info(f"Downloading IPCubed components failed.\n\nDetails: {log}\n\n"
                 "Check your internet connection, then press 3D Live again to retry.", error=True)
            return r.returncode
        _marker().write_text(json.dumps({"deps": _deps_hash(), "time": time.time()}))
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    from .ctl import launch, send
    if not send("ping", timeout=0.5):
        launch(*(["--show"] if show else []))
    return 0


if __name__ == "__main__":
    if "--install" in sys.argv:
        raise SystemExit(install("--show" in sys.argv))
    print("ready" if ready() else "missing", download_mb(), "MB")
