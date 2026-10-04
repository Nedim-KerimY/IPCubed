"""Calisan viewer'a komut gonder (yalnizca standart kutuphane; KiCad eklentisi de bunu kullanir).

kullanim: python ctl.py toggle|show|hide|quit
Viewer calismiyorsa `launch.json` icindeki python ile baslatir.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
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


def launch() -> None:
    try:
        cfg = json.loads((config_dir() / "launch.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):                 # launch.json yok (Linux/macOS kurulumu): bu paketle ayni Python'u kullan
        cfg = {"python": sys.executable, "cwd": str(Path(__file__).resolve().parents[1])}
    kw: dict = {"cwd": cfg["cwd"], "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    cmd = [cfg["python"], "-m", "ipcubed"]
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
    launch()
    for _ in range(80):                 # ~20 sn
        time.sleep(0.25)
        if send(cmd if cmd != "toggle" else "show"):
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "toggle"))
