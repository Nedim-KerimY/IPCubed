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


SETUP_REV = b"2"        # kurulum yontemi degisti (2: temiz ortam + --ignore-installed): eski kurulumlar bir kez tamamlanir


def _deps_hash() -> str:
    return hashlib.sha256(DEPS.read_bytes() + SETUP_REV).hexdigest()[:16]


def _marker() -> Path:
    return Path(sys.prefix) / "ipcubed-components.json"        # sanal ortamla birlikte silinir


def _lock() -> Path:
    """Tek kilit, iki asama: 'dialog:<pid>' (onay diyalogu acik) ve 'install:<pid>' (indirme suruyor)."""
    return Path(sys.prefix) / "ipcubed-setup.lock"


def _read_lock():
    try:
        kind, pid = _lock().read_text().strip().split(":")
        return kind, int(pid)
    except (OSError, ValueError):
        return None


def _take_lock(kind: str) -> bool:
    """Atomik al (O_EXCL): ayni anda iki 3D Live tiklamasi iki diyalog / iki pip kurulumu acmasin. Olu surecin kilidi silinir."""
    for _ in range(2):
        try:
            fd = os.open(_lock(), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            cur = _read_lock()
            if cur is not None and _pid_alive(cur[1]):
                return False
            try:
                _lock().unlink()
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w") as f:
            f.write(f"{kind}:{os.getpid()}")
        return True
    return False


def _set_lock(kind: str, pid: int):
    _lock().write_text(f"{kind}:{pid}")


def _drop_lock():
    try:
        _lock().unlink()
    except OSError:
        pass


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
    """Kilidi tutan surec hala bizim (Python) surecimiz mi? Zombi = olu; PID baska programa verildiyse = olu."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000 | 0x1000, False, pid)        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            if k32.WaitForSingleObject(h, 0) != 0x102:              # WAIT_TIMEOUT degil: sonlanmis
                return False
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(len(buf))
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return "python" in buf.value.lower()
            return True
        finally:
            k32.CloseHandle(h)
    proc = Path(f"/proc/{pid}")
    if proc.exists():                                               # Linux
        try:
            stat = (proc / "stat").read_text()
            if stat[stat.rindex(")") + 2] in "ZX":                  # zombi / olu
                return False
            return b"python" in (proc / "cmdline").read_bytes().lower()
        except (OSError, ValueError, IndexError):
            return False
    try:                                                            # macOS / diger POSIX
        out = subprocess.run(["ps", "-o", "stat=,command=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    except OSError:
        out = ""
    if not out:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        return True
    return not out.startswith("Z") and "python" in out.lower()


def installing() -> bool:
    cur = _read_lock()
    return cur is not None and cur[0] == "install" and _pid_alive(cur[1])


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
    if not _take_lock("dialog"):
        if installing():
            info("IPCubed is still downloading its components.\n\nThe 3D view will open automatically when it is done.\n\n"
                 f"Progress: {log_path()}")
        return False                       # onay diyalogu zaten ekranda
    try:
        return _ask_and_install(show)
    except BaseException:
        _drop_lock()
        raise


def _ask_and_install(show: bool) -> bool:
    mb = download_mb()
    upd = _update()
    size = (f"up to {mb} MB" if upd else f"about {mb} MB") if mb else "a few hundred MB"   # guncellemede cogu zaten kurulu
    head = ("This IPCubed update requires updated components to run" if upd
            else "IPCubed requires additional components to run")
    if not ask(f"{head} ({size} download: Qt, OpenCascade, wgpu...).\n\n"
               "Would you like to download them now?\n\n"
               "This is needed only once. The 3D view opens automatically when it is done."):
        _drop_lock()
        return False
    _set_lock("install", _spawn_installer(show))       # kilit el degistirir: arada bosluk yok
    return False


def _spawn_installer(show: bool) -> int:
    cmd = [sys.executable, "-m", "ipcubed.setup_deps", "--install"] + (["--show"] if show else [])
    from .ctl import clean_env
    kw: dict = {"cwd": str(HERE.parent), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                "env": clean_env()}
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000           # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
        try:
            return subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw).pid     # BREAKAWAY_FROM_JOB: KiCad'in is nesnesinden cik
        except OSError:
            return subprocess.Popen(cmd, creationflags=flags, **kw).pid
    return subprocess.Popen(cmd, start_new_session=True, **kw).pid


def _kicad_running() -> bool:
    try:
        import psutil                      # bilesenlerle birlikte kuruldu
    except ImportError:
        return True
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if (n.startswith("kicad") or n.startswith("pcbnew")) and "cli" not in n:
            return True
    return False


def install(show: bool) -> int:
    """Arka plan kurucusu: pip ile deps.txt'yi bu sanal ortama kur; basarida isaret dosyasi + 3D'yi ac, hatada diyalog."""
    _set_lock("install", os.getpid())
    log = log_path()
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} IPCubed components -> {sys.prefix}\n")
            f.flush()
            from .ctl import clean_env
            # --ignore-installed: KiCad'in ortami sistem paketlerini de gorur (--system-site-packages); hepsi bu ortama kurulur ki
            # sistemdeki baska surumler (ya da sonradan yukseltilenler) viewer'i bozmasin
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                                "--only-binary", ":all:", "--ignore-installed", "--progress-bar", "off", "-r", str(DEPS)],
                               stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=clean_env())
            f.write(f"\n{time.strftime('%H:%M:%S')} pip exit code {r.returncode}\n")
        if r.returncode == 0:
            _marker().write_text(json.dumps({"deps": _deps_hash(), "time": time.time()}))
    finally:
        _drop_lock()                       # diyalogdan ONCE: hata mesaji acikken 3D Live yeniden denesin
    if r.returncode != 0:
        info(f"Downloading IPCubed components failed.\n\nDetails: {log}\n\n"
             "Check your internet connection, then press 3D Live again to retry.", error=True)
        return r.returncode
    from .ctl import launch, send
    if not _kicad_running():                # indirme surerken KiCad kapatildi: sahipsiz viewer baslatma (sonraki 3D Live acar)
        return 0
    if not send("ping", timeout=0.5):
        launch(*(["--show"] if show else []))
    return 0


if __name__ == "__main__":
    if "--install" in sys.argv:
        raise SystemExit(install("--show" in sys.argv))
    print("ready" if ready() else "missing", download_mb(), "MB")
