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


def launch(*args: str) -> None:
    py = Path(sys.executable)
    if sys.platform == "win32" and py.with_name("pythonw.exe").exists():
        py = py.with_name("pythonw.exe")          # konsol penceresi acilmasin
    kw: dict = {"cwd": str(Path(__file__).resolve().parents[1]), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL}
    cmd = [str(py), "-m", "ipcubed", *args]
    if sys.platform == "win32":
        try:
            subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200 | 0x01000000, **kw)     # DETACHED | NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200, **kw)                # breakaway izni yoksa
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)


def main(cmd: str = "toggle") -> int:
    if send(cmd):
        return 0
    if cmd == "quit":
        return 0
    # calismiyor: baslat; 3D veri yuklenince kendisi acilir (ilk aciliste kutuphaneleri yuklemek uzun surebilir, bekleme yok)
    launch(*(["--show"] if cmd in ("toggle", "show") else []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "toggle"))
