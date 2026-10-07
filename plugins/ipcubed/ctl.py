"""Calisan viewer'a komut gonder (yalnizca standart kutuphane; KiCad eklentisinin `toggle.py`'si bunu kullanir).

kullanim: python -m ipcubed.ctl toggle|show|hide|quit
Viewer calismiyorsa bu Python ile (KiCad'in eklenti icin kurdugu sanal ortam) arka planda baslatir. KiCad'in verdigi
KICAD_API_SOCKET / KICAD_API_TOKEN ortam degiskenleri alt surece aktarilir.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ipcubed"


def send(cmd: str, timeout: float = 2.0) -> bool:
    try:
        port = int((config_dir() / "port").read_text().strip())
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall((cmd + "\n").encode())
            s.settimeout(timeout)
            return s.recv(16).startswith(b"ok")
    except (OSError, ValueError):
        return False


# KiCad, eklenti surecine kendi Python yollarini verir (Linux: PYTHONPATH=/usr/lib/python3/dist-packages, MATPLOTLIBRC=/etc/
# matplotlib). Bunlar eklentinin sanal ortaminin ONUNE gecer: baska Python surumu icin derlenmis sistem paketleri (Pillow vb.)
# yuklenir ve cokerek silkscreen'i (matplotlib) bozar. Viewer, kurucu ve pip bunlar olmadan calisir.
_LEAKY_ENV = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "MATPLOTLIBRC", "MPLBACKEND")


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _LEAKY_ENV}
    env["PYTHONNOUSERSITE"] = "1"                 # ~/.local site-packages da karismasin
    return env


def launch(*args: str, check: bool = True) -> None:
    """Viewer'i arka planda baslat. check: ilk saniyelerde coker ise (eksik sistem kutuphanesi vb.) kullaniciya nedenini goster."""
    py = Path(sys.executable)
    if sys.platform == "win32" and py.with_name("pythonw.exe").exists():
        py = py.with_name("pythonw.exe")          # konsol penceresi acilmasin
    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    log = cfg / "viewer.log"
    err = open(log, "w", encoding="utf-8", errors="replace")
    kw: dict = {"cwd": str(Path(__file__).resolve().parents[1]), "stdin": subprocess.DEVNULL, "stdout": err, "stderr": err,
                "env": clean_env()}
    cmd = [str(py), "-m", "ipcubed", *args]
    if sys.platform == "win32":
        try:
            p = subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200 | 0x01000000, **kw)     # DETACHED | NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB
        except OSError:
            p = subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200, **kw)                # breakaway izni yoksa
    else:
        p = subprocess.Popen(cmd, start_new_session=True, **kw)
    err.close()
    if check:
        _check_started(p, log)


def _check_started(p, log: Path, timeout: float = 30.0) -> None:
    """Viewer kontrol sunucusunu acana kadar bekle; once kapanirsa hata diyalogu."""
    import time
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if p.poll() is not None:
            break
        if send("ping", timeout=0.3):
            return
        time.sleep(0.5)
    if p.poll() in (None, 0):              # hala aciliyor (yavas disk) ya da zaten calisan kopyaya devretti
        return
    try:
        tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
    except OSError:
        tail = []
    text = "\n".join(tail)
    hint = ""
    if 'platform plugin "xcb"' in text or "xcb-cursor" in text:
        hint = ("Qt is missing X11 system libraries. Install them, then press 3D Live again:\n"
                "    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 "
                "libxcb-render-util0 libxcb-image0 libxcb-randr0 libxcb-shape0\n"
                "    (Fedora: sudo dnf install xcb-util-cursor xcb-util-wm xcb-util-keysyms libxkbcommon-x11)\n\n")
    from .setup_deps import info
    info(f"The IPCubed 3D viewer could not start.\n\n{hint}Details ({log}):\n{text[-1500:]}", error=True)


def main(cmd: str = "toggle") -> int:
    if send(cmd):
        return 0
    if cmd == "quit":
        return 0
    show = cmd in ("toggle", "show")
    from .setup_deps import ensure
    if not ensure(show):                # bilesenler yok: kullaniciya sorulur, onaylanirsa kurulum bitince 3D kendisi acilir
        return 0
    # calismiyor: baslat; 3D veri yuklenince kendisi acilir (ilk aciliste kutuphaneleri yuklemek uzun surebilir, bekleme yok)
    launch(*(["--show"] if show else []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "toggle"))
