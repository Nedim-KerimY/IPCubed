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


def _parent_and_name(pid: int):
    """(ust surec, ad) ya da None. Yalnizca standart kutuphane: bilesenler (psutil) henuz kurulmamis olabilir."""
    if sys.platform == "win32":
        return _win_procs().get(pid)
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        name = Path(f"/proc/{pid}/comm").read_text().strip()
        return int(stat[stat.rindex(")") + 2:].split()[1]), name
    except (OSError, ValueError, IndexError):
        pass
    try:                                                    # macOS / diger POSIX
        out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.split(None, 1)
        return int(out[0]), Path(out[1].strip()).name
    except (OSError, ValueError, IndexError):
        return None


def _win_procs() -> dict:
    """pid -> (ust pid, exe adi): Toolhelp32 anlik goruntusu."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)              # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    out = {}
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


def find_kicad_ancestor(names=("kicad", "pcbnew"), max_hops: int = 6) -> int | None:
    """3D Live'a basilan KiCad sureci: ust surec zincirinde adi kicad/pcbnew ile baslayan ilk surec.
    os.getppid() yetmez: Windows'ta sanal ortamin python.exe'si asil yorumlayiciyi alt surec olarak baslatan bir
    yonlendiricidir, yani ust surec KiCad degil o yonlendiricidir. Bulunamazsa None (herhangi bir KiCad)."""
    pid = os.getppid()
    for _ in range(max_hops):
        info = _parent_and_name(pid)
        if info is None:
            return None
        ppid, name = info
        n = name.lower()
        if n.startswith(names) and "cli" not in n:
            return pid
        if ppid in (0, pid):
            return None
        pid = ppid
    return None


def ask(cmd: str, timeout: float = 2.0) -> str | None:
    """Calisan viewer'a komut; cevap satiri ya da None (viewer yok)."""
    try:
        port = int(port_path().read_text().strip())
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall((cmd + "\n").encode())
            s.settimeout(timeout)
            r = s.recv(256).decode("utf-8", "replace").strip()
            return r if r.startswith("ok") else None
    except (OSError, ValueError):
        return None


def send(cmd: str, timeout: float = 2.0) -> bool:
    return ask(cmd, timeout) is not None


def viewer_id() -> str:
    """Viewer kimligi: bagli KiCad sureci + eklenti kurulumu (yeniden kurulunca dosya zamani degisir)."""
    try:
        stamp = int(Path(__file__).stat().st_mtime)
    except OSError:
        stamp = 0
    return f"{os.environ.get('IPCUBED_KICAD_PID', '')}:{stamp}:{Path(__file__).resolve().parent}"


def own_viewer(timeout: float = 2.0) -> bool | None:
    """Calisan viewer bu KiCad'in ve bu kurulumun mu? None: viewer yok. Eski surumler 'id' bilmez (yalniz 'ok'): yabanci."""
    r = ask("id", timeout)
    if r is None:
        return None
    return r == "ok id " + viewer_id()


def retire_foreign_viewer() -> None:
    """Baska bir KiCad'e (or. kapanirken asili kalmis eski KiCad) ya da eski kuruluma ait viewer komutlari alip kendi (artik
    olmayan) editorunu arardi: 3D hic acilmaz, 'cannot find the PCB editor window' derdi. Onu kapat, yenisi baslasin."""
    import time
    send("quit", timeout=1.0)
    t_end = time.monotonic() + 6
    while time.monotonic() < t_end and send("ping", timeout=0.3):
        time.sleep(0.3)


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
        full = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        full = ""
    if "IPCUBED_GPU_UNSUPPORTED" in full:           # viewer kendi nedenini yazdi: kullanilabilir GPU yok
        from .setup_deps import info
        info("The IPCubed 3D view cannot start on this computer.\n\n"
             + full.split("IPCUBED_GPU_UNSUPPORTED", 1)[1].strip()[:1500] + f"\n\nDetails: {log}", error=True)
        return
    tail = full.strip().splitlines()[-6:]
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
    import re
    # cffi (wgpu) bildirir: "cannot load library '...wgpu_native-release.dll': error 0x11c7" (0x11c7 = 4551, 0x11cc = 4556)
    cffi = re.search(r"cannot load library '([^']+)': error (0x11c7|0x11cc|4551|4556)\b", text, re.IGNORECASE)
    if cffi:
        return Path(cffi.group(1).replace("\\", "/")).name
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

    def norm(t):                           # kod sayfasi bozulmalarina dayanikli: yalniz ASCII harf/rakam
        return re.sub(r"[^a-z0-9]", "", t.lower())
    flat = norm(text)
    if not any(norm(m) and norm(m) in flat for m in msgs):
        return ""
    mod = re.search(r"DLL load failed while importing (\w+)", text)
    return mod.group(1) if mod else "a native library"


def main(cmd: str = "toggle") -> int:
    if os.environ.get("KICAD_API_SOCKET"):        # eklenti olarak calisiyoruz: ust surec bu 3D Live'a basilan KiCad
        kp = find_kicad_ancestor()
        if kp is not None:
            os.environ.setdefault("IPCUBED_KICAD_PID", str(kp))
    own = own_viewer()
    if own:
        send(cmd)
        return 0
    if own is False:
        if cmd == "quit":
            return 0
        retire_foreign_viewer()
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
