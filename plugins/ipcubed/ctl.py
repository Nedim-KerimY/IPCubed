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


def instance_key() -> str:
    """Her KiCad ornegine ayri viewer. Anahtar, KiCad'in API soketi: ilk ornek 'api.sock', sonrakiler 'api-<pid>.sock'."""
    import re
    sock = os.environ.get("KICAD_API_SOCKET", "")
    if not sock:
        return ""
    return re.sub(r"[^A-Za-z0-9_-]", "_", re.split(r"[\\/]", sock.split("://", 1)[-1])[-1].rsplit(".", 1)[0])


def port_path() -> Path:
    k = instance_key()
    return config_dir() / (f"port-{k}" if k else "port")


def kicad_pid() -> int | None:
    """Viewer'in bagli oldugu KiCad sureci (3D Live'i calistiran). Bilinmiyorsa None: herhangi bir KiCad."""
    try:
        return int(os.environ["IPCUBED_KICAD_PID"])
    except (KeyError, ValueError):
        return None


def send(cmd: str, timeout: float = 2.0) -> bool:
    try:
        port = int(port_path().read_text().strip())
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
    env["PYTHONIOENCODING"] = "utf-8"             # viewer.log hep UTF-8 (Windows'ta yerel kod sayfasi hata metnini bozuyordu)
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
    blocked = _app_control_block(text)
    if blocked:
        hint = ("Windows blocked one of IPCubed's components (" + blocked + ").\n"
                "Smart App Control (or your organization's application control policy) only lets signed or well-known "
                "programs load, and IPCubed's open-source libraries are not code-signed.\n\n"
                "To use IPCubed, turn Smart App Control off: Windows Security > App & browser control > "
                "Smart App Control settings > Off, then press 3D Live again.\n"
                "Note: Windows may not let you turn Smart App Control back on without resetting Windows. "
                "On a company-managed PC, ask your IT administrator instead.\n\n")
    elif 'platform plugin "xcb"' in text or "xcb-cursor" in text:
        hint = ("Qt is missing X11 system libraries. Install them, then press 3D Live again:\n"
                "    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 "
                "libxcb-render-util0 libxcb-image0 libxcb-randr0 libxcb-shape0\n"
                "    (Fedora: sudo dnf install xcb-util-cursor xcb-util-wm xcb-util-keysyms libxkbcommon-x11)\n\n")
    from .setup_deps import info
    info(f"The IPCubed 3D viewer could not start.\n\n{hint}Details ({log}):\n{text[-1500:]}", error=True)


def _app_control_block(text: str) -> str:
    """Windows Akilli Uygulama Denetimi / WDAC bir DLL'i engellediyse engellenen modulun adi, yoksa ''.
    Hata metni Windows dilinde gelir: mesaj, sistemin kendi metniyle (FormatMessage) karsilastirilir."""
    if "DLL load failed" not in text and "WinError 4551" not in text:
        return ""
    msgs = ["Application Control policy has blocked this file", "Smart App Control", "WinError 4551"]
    if sys.platform == "win32":
        import ctypes
        for code in (4551, 4556):              # ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION (+ yeni Windows'taki esdegeri)
            try:
                m = ctypes.FormatError(code).strip().rstrip(".")
            except Exception:  # noqa: BLE001
                continue
            if m and "Unknown error" not in m:
                msgs.append(m)
    import re

    def norm(t):                           # kod sayfasi bozulmalarina dayanikli: yalniz ASCII harf/rakam
        return re.sub(r"[^a-z0-9]", "", t.lower())
    flat = norm(text)
    if not any(norm(m) and norm(m) in flat for m in msgs):
        return ""
    mod = re.search(r"DLL load failed while importing (\w+)", text)
    return mod.group(1) if mod else "a native library"


def main(cmd: str = "toggle") -> int:
    if os.environ.get("KICAD_API_SOCKET"):        # eklenti olarak calisiyoruz: ust surec bu 3D Live'a basilan KiCad
        os.environ.setdefault("IPCUBED_KICAD_PID", str(os.getppid()))
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
