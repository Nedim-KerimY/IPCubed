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
    if not preflight(mb):
        _drop_lock()
        return False
    _set_lock("install", _spawn_installer(show))       # kilit el degistirir: arada bosluk yok
    return False


# ------------------------------------------------------------------------------ indirmeden once: bu bilgisayarda calisir mi?
MAX_REL_PATH = 151      # bilesenlerdeki en uzun dosya yolu (site-packages a gore; PySide6 qml), CI testi tam olarak dogrular
MIN_PYTHON = (3, 11)    # numpy 2.4 / cadquery-ocp-novtk 8: cp311+ wheel'leri


def smart_app_control_state() -> int | None:
    """Windows Akilli Uygulama Denetimi: 0 kapali, 1 ACIK (imzasiz DLL'leri engeller), 2 degerlendirme; Windows degilse None.
    IPCUBED_FAKE_SAC=1: diyalogu denemek icin acik varsay."""
    if os.environ.get("IPCUBED_FAKE_SAC"):
        return int(os.environ["IPCUBED_FAKE_SAC"])
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as k:
            return int(winreg.QueryValueEx(k, "VerifiedAndReputablePolicyState")[0])
    except OSError:
        return None


SAC_TEXT = ("Windows Smart App Control is turned ON on this PC.\n\n"
            "It blocks IPCubed's open-source components (Qt, OpenCascade, wgpu...) because they are not code-signed, "
            "so the 3D view would not start.\n\n"
            "Please turn it off:\nWindows Security > App & browser control > Smart App Control settings > Off\n\n"
            "Note: Windows may not let you turn Smart App Control back on without resetting Windows. "
            "On a company-managed PC, ask your IT administrator instead.\n\n"
            "Click \"I disabled it\" when you are done.")


def _sac_choice(text: str) -> str:
    """-> 'done' | 'open' | 'cancel'. wx (KiCad'in Python'unda hazir) ile ozel dugme adlari; yoksa standart Windows kutusu."""
    try:
        import wx
        app = wx.App(False) if not wx.App.Get() else None  # noqa: F841
        dlg = wx.MessageDialog(None, text, TITLE, wx.YES_NO | wx.CANCEL | wx.ICON_WARNING | wx.STAY_ON_TOP)
        dlg.SetYesNoCancelLabels("I disabled it", "Open Windows Security", "Cancel")
        r = dlg.ShowModal()
        dlg.Destroy()
        return {wx.ID_YES: "done", wx.ID_NO: "open"}.get(r, "cancel")
    except Exception:  # noqa: BLE001
        pass
    import ctypes
    MB_YESNOCANCEL, MB_ICONWARNING, MB_SETFOREGROUND, MB_TOPMOST = 0x3, 0x30, 0x10000, 0x40000
    r = ctypes.windll.user32.MessageBoxW(None, text + "\n\n(Yes = I disabled it, No = open Windows Security)", TITLE,
                                         MB_YESNOCANCEL | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST)
    return {6: "done", 7: "open"}.get(r, "cancel")


def _sac_gate() -> bool:
    """Akilli Uygulama Denetimi aciksa kullanicidan kapatmasini iste. Kapatildi (ya da hic acik degil) -> True, iptal -> False."""
    fake = bool(os.environ.get("IPCUBED_FAKE_SAC"))
    text = SAC_TEXT
    while smart_app_control_state() == 1:
        c = _sac_choice(text)
        if c == "cancel":
            return False
        if c == "open":
            try:
                os.startfile("windowsdefender://appbrowser")      # Windows Guvenligi > Uygulama ve tarayici denetimi
            except OSError:
                pass
            continue
        if fake:
            return True
        text = "Smart App Control still appears to be ON.\n\n" + SAC_TEXT     # kapatmadan "kapattim" denirse
    return True


def preflight(mb: int | None) -> bool:
    """Indirmeden once bilinen engeller: Python surumu, Akilli Uygulama Denetimi, disk alani, Windows yol uzunlugu siniri."""
    if sys.version_info < MIN_PYTHON:
        info(f"IPCubed needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer, but this KiCad uses Python "
             f"{sys.version_info[0]}.{sys.version_info[1]} ({sys.executable}).\n\n"
             "On Linux, KiCad uses the system Python: Ubuntu 22.04 has 3.10. Ubuntu 24.04, Debian 12+ and current Fedora "
             "work.", error=True)
        return False
    if not _sac_gate():
        return False
    if _update() and _viewers_running():
        info("An IPCubed 3D view is still running (another KiCad window?).\n\n"
             "Its files cannot be replaced while it runs. Close all KiCad windows, open KiCad again, "
             "then press 3D Live to update the components.", error=True)
        return False
    import shutil
    need = max(1.5, 3.5 * (mb or 200) / 1000)            # GB: indirme + acilmis paketler (~3x) + pip gecici dosyalari
    try:
        free = shutil.disk_usage(sys.prefix).free / 1e9
    except OSError:
        free = need
    if free < need:
        info(f"There is not enough free disk space for IPCubed's components.\n\n"
             f"Needed: about {need:.1f} GB, free: {free:.1f} GB on the drive of\n{sys.prefix}\n\n"
             "Free up some space, then press 3D Live again.", error=True)
        return False
    if sys.platform == "win32" and len(str(Path(sys.prefix) / "Lib" / "site-packages")) + 1 + MAX_REL_PATH > 259 \
            and not _long_paths_enabled():
        info("The folder KiCad uses for plugin components has a very long path, and Windows long path support is off, "
             "so some component files could not be written.\n\n"
             f"Folder: {sys.prefix}\n\n"
             "Turn on long paths (as administrator, in PowerShell):\n"
             "New-ItemProperty -Path HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem -Name LongPathsEnabled "
             "-Value 1 -PropertyType DWORD -Force\n\nthen restart Windows and press 3D Live again.", error=True)
        return False
    missing = missing_x11_libs()
    if missing:
        info("Qt (the 3D view's window toolkit) needs some X11 system libraries that are not installed on this computer:\n"
             f"{', '.join(missing)}\n\nInstall them, then press 3D Live again:\n"
             f"    {X11_APT}\n    (Fedora: {X11_DNF})", error=True)
        return False
    return True


# Qt 6.5+ xcb eklentisinin istedigi sistem kutuphaneleri (minimal kurulumlarda, Ubuntu masaustunde bile libxcb-cursor0 eksik olabilir)
X11_LIBS = ("xcb-cursor", "xkbcommon-x11", "xcb-icccm", "xcb-keysyms", "xcb-xkb", "xcb-render-util", "xcb-image",
            "xcb-randr", "xcb-shape")
X11_APT = ("sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 libxcb-render-util0 "
           "libxcb-image0 libxcb-randr0 libxcb-shape0")
X11_DNF = "sudo dnf install xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-renderutil xcb-util-image libxkbcommon-x11"


def missing_x11_libs() -> list[str]:
    """Linux + X11 (XWayland dahil): Qt'nin xcb eklentisi icin eksik sistem kutuphaneleri. 200 MB indirmeden ONCE soyle."""
    if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        return []
    import ctypes.util
    try:
        return [f"lib{n}" for n in X11_LIBS if ctypes.util.find_library(n) is None]
    except Exception:  # noqa: BLE001  ldconfig yok vb.: bilinmiyorsa engelleme
        return []


def _viewers_running() -> bool:
    """Bu ortamdan calisan bir IPCubed viewer'i var mi (guncellemede dosyalari kilitli olur)? psutil yoksa bilinemez: False."""
    try:
        import psutil
    except ImportError:
        return False
    for p in psutil.process_iter(["cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
        except psutil.Error:
            continue
        if "-m" in cmd and "ipcubed" in cmd and p.pid != os.getpid():
            return True
    return False


def _long_paths_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return bool(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except OSError:
        return False


def _spawn_installer(show: bool) -> int:
    cmd = [sys.executable, "-m", "ipcubed.setup_deps", "--install"] + (["--show"] if show else [])
    from .ctl import clean_env
    err = open(crash_log_path(), "w", encoding="utf-8", errors="replace")   # kurucu ice aktarmada bile coker ise iz kalsin
    kw: dict = {"cwd": str(HERE.parent), "stdin": subprocess.DEVNULL, "stdout": err, "stderr": err, "env": clean_env()}
    try:
        return _popen_detached(cmd, kw).pid
    finally:
        err.close()


def crash_log_path() -> Path:
    return log_path().with_name("install-errors.log")


def _popen_detached(cmd, kw) -> subprocess.Popen:
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000           # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
        try:
            return subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)     # BREAKAWAY_FROM_JOB: KiCad'in is nesnesinden cik
        except OSError:
            return subprocess.Popen(cmd, creationflags=flags, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def _kicad_running() -> bool:
    try:
        import psutil                      # bilesenlerle birlikte kuruldu
    except ImportError:
        return True
    from .ctl import kicad_pid
    pid = kicad_pid()
    if pid is not None:
        try:
            return psutil.Process(pid).is_running() and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if (n.startswith("kicad") or n.startswith("pcbnew")) and "cli" not in n:
            return True
    return False


# ------------------------------------------------------------------------------ indirme ilerlemesi
_NICE = {"pyside6_essentials": "Qt (PySide6)", "pyside6": "Qt (PySide6)", "shiboken6": "Qt (Shiboken)",
         "cadquery_ocp_novtk": "OpenCascade", "cadquery_ocp": "OpenCascade", "wgpu": "wgpu (GPU)", "pygfx": "pygfx",
         "numpy": "NumPy", "matplotlib": "Matplotlib", "shapely": "Shapely", "pillow": "Pillow"}
_UNIT = {"bytes": 1, "byte": 1, "kB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}      # pip boyutlari 1000 tabanli


class _Progress:
    """pip ciktisindan (--progress-bar raw: 'Progress N of M') toplam indirme ilerlemesi. Toplam: dep_sizes.json tahmini."""

    def __init__(self, total_mb):
        self.total = (total_mb or 0) * 1000 ** 2
        self.done = 0                      # biten dosyalarin baytlari
        self.cur = self.cur_total = 0      # suren dosya
        self.pending = 0                   # suren dosyanin "Downloading x (boyut)" satirindaki boyutu
        self.name = ""
        self.phase = "prepare"             # prepare -> download -> install

    def feed(self, line: str):
        import re
        line = line.strip()
        m = re.match(r"Progress (\d+) of (\d+)", line)
        if m:
            self.cur, self.cur_total = int(m.group(1)), int(m.group(2))
            return
        m = re.match(r"(Downloading|Using cached) (\S+) \(([\d.]+) (\w+)\)", line)
        if m and not m.group(2).endswith(".metadata"):
            self._finish()
            size = int(float(m.group(3)) * _UNIT.get(m.group(4), 1))
            if m.group(1) == "Using cached":
                self.done += size
            else:
                self.pending, self.phase = size, "download"
                base = m.group(2).split("-")[0].lower()
                self.name = _NICE.get(base, base)
        elif line.startswith("Installing collected packages"):
            self._finish()
            self.phase = "install"

    def _finish(self):
        if self.pending or self.cur_total:
            self.done += max(self.pending, self.cur_total)
        self.pending = self.cur = self.cur_total = 0

    def fraction(self) -> float:
        got = self.done + self.cur
        if got > self.total * 0.98:        # tahmin kucuk kaldi (yeni surumler buyumus): cubuk %98'de takilmasin
            self.total = int(got * 1.08)
        return min(0.99, got / self.total) if self.total else 0.0

    def message(self) -> str:
        if self.phase == "install":
            return "Installing components...\nThis can take a minute."
        if self.phase == "prepare":
            return "Preparing the download..."
        mb = (self.done + self.cur) / 1000 ** 2
        return f"Downloading {self.name}...\n{mb:.0f} of ~{self.total / 1000 ** 2:.0f} MB"


def _pip_version() -> tuple:
    """Bu ortamdaki pip surumu (ornek (24, 0)); okunamazsa (0,). Linux'ta sistem Python'unun pip'i eski olabilir.
    Alt surec acmadan okunur (yavas degil; kullanici adinda Turkce harf olunca kod sayfasi cozme hatasi da olmaz)."""
    try:
        from importlib.metadata import version
        return tuple(int(x) for x in version("pip").split(".")[:2])
    except Exception:  # noqa: BLE001
        return (0,)


# Kullanicinin pip ayarlari bilesenleri BU ortamin disina gondermesin (KiCad kendi pip'ini --isolated calistirir).
# Dizin/proxy ayarlari (PIP_INDEX_URL, PIP_PROXY, PIP_CERT...) kalir: sirket aglarinda gerekir.
_PIP_REDIRECT_ENV = ("PIP_TARGET", "PIP_PREFIX", "PIP_ROOT", "PIP_USER", "PIP_REQUIRE_VIRTUALENV", "PIP_SRC", "PIP_EDITABLE")


def _pip_env() -> dict:
    from .ctl import clean_env
    env = {k: v for k, v in clean_env().items() if k.upper() not in _PIP_REDIRECT_ENV}
    env["PIP_USER"] = "0"                  # pip.ini'deki "user = true" a karsi (ortam degiskeni yapilandirma dosyasini ezer)
    return env


def _pinned() -> dict[str, str]:
    """deps.txt: paket adi (normallestirilmis) -> sabit surum (yalniz '==' ile sabitlenenler; ortam isaretleri dikkate alinir)."""
    import re
    out = {}
    for line in DEPS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        req, _, marker = line.partition(";")
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)\s*==\s*([^\s,]+)", req.strip())
        if not m or (marker.strip() and not _marker_ok(marker.strip())):
            continue
        out[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return out


def _marker_ok(marker: str) -> bool:
    """Basit ortam isaretleri (sys_platform / platform_system =/!=); bilinmeyen isaret: kurulacak varsay."""
    import platform
    import re
    env = {"sys_platform": sys.platform, "platform_system": platform.system()}
    for key, op, val in re.findall(r"(sys_platform|platform_system)\s*(==|!=)\s*['\"]([^'\"]+)['\"]", marker):
        if (env[key] == val) != (op == "=="):
            return False
    return True


def _stale_packages() -> list[str]:
    """Guncellemede: bu ortama (sys.prefix) daha once kurulmus ve deps.txt'de surumu degismis paketler. --ignore-installed eski
    surumu silmez (iki surumun dosyalari karisir); bunlar once kaldirilir. Sistem paketlerine dokunulmaz."""
    import re
    from importlib.metadata import distributions
    want = _pinned()
    prefix = Path(sys.prefix).resolve()
    stale = []
    for d in distributions():
        try:
            name = re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower()
            loc = Path(str(d.locate_file(""))).resolve()
        except Exception:  # noqa: BLE001
            continue
        if name in want and d.version != want[name] and prefix in loc.parents:
            stale.append(name)
    return sorted(set(stale))


def _installed_here(module: str = "PySide6") -> bool:
    """pip gercekten BU ortama mi kurdu? (pip.ini'de target/prefix varsa baska yere kurup 0 ile cikar.)"""
    import importlib
    import importlib.util
    importlib.invalidate_caches()
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.origin:
        return False
    return Path(sys.prefix).resolve() in Path(spec.origin).resolve().parents


def _kill_tree(p: subprocess.Popen):
    """pip'i durdur. Windows: sanal ortamin python.exe'si asil yorumlayiciyi ALT surec olarak baslatir -> agaci oldur."""
    if p.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000)
    else:
        p.terminate()


def _show_progress(prog: _Progress, proc: subprocess.Popen, finished) -> bool:
    """wx ilerleme diyalogu (KiCad'in Python'unda hazir; Qt henuz kurulmadi). Iptal edildiyse True. wx yoksa diyalogsuz bekler."""
    try:
        import wx
    except Exception:  # noqa: BLE001  wx yok (bazi Linux kurulumlari): eski davranis, sessiz kurulum
        finished.wait()
        return False
    app = wx.App(False)  # noqa: F841
    dlg = wx.ProgressDialog(TITLE, "Preparing the download...\n", maximum=1000,
                            style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_SMOOTH | wx.PD_AUTO_HIDE)
    dlg.SetSize(wx.Size(max(dlg.GetSize().width, 440), dlg.GetSize().height))
    dlg.Raise()
    cancelled = False
    try:
        while not finished.wait(0.1):
            if prog.phase == "install":
                ok, _ = dlg.Pulse(prog.message())
            else:
                f = prog.fraction()
                ok, _ = dlg.Update(int(f * 1000), prog.message() + (f"  ({f * 100:.0f}%)" if prog.phase == "download" else ""))
            if not ok:
                cancelled = True
                _kill_tree(proc)
                finished.wait(10)
                break
    finally:
        dlg.Destroy()
    return cancelled


def install(show: bool) -> int:
    """Arka plan kurucusu. Beklenmeyen her hata (wx, dosya, surec...) kullaniciya gosterilir ve install.log'a yazilir:
    "Download"a basip hicbir sey gormemek olmasin."""
    try:
        return _install(show)
    except BaseException:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        try:
            with open(log_path(), "a", encoding="utf-8") as f:
                f.write(f"\n{time.strftime('%H:%M:%S')} installer error:\n{tb}")
        except OSError:
            pass
        _drop_lock()
        info(f"Installing IPCubed components failed unexpectedly.\n\n{tb.strip().splitlines()[-1][:400]}\n\n"
             f"Details: {log_path()}\n\nPress 3D Live again to retry.", error=True)
        return 1


def _install(show: bool) -> int:
    """pip ile deps.txt'yi bu sanal ortama kur (ilerleme diyalogu ile); basarida isaret dosyasi + 3D'yi ac, hatada diyalog."""
    import threading
    _set_lock("install", os.getpid())
    log = log_path()
    cancelled = False
    proc = None
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} IPCubed components -> {sys.prefix}\n")
            f.flush()
            pip = [sys.executable, "-m", "pip"]
            pipv = _pip_version()
            # --progress-bar raw: diyalog icin, pip 24.1+ (eski pip "Usage" hatasiyla cikar)
            bar = "raw" if pipv >= (24, 1) else "off"
            f.write(f"pip {'.'.join(map(str, pipv))}, progress {bar}\n")
            stale = _stale_packages() if _update() else []
            if stale:                          # guncelleme: eski surumlerin dosyalari yeni surumlerle karismasin
                f.write(f"removing old versions: {' '.join(stale)}\n")
                f.flush()
                r = subprocess.run(pip + ["uninstall", "-y", "--disable-pip-version-check", *stale], stdout=f,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=_pip_env(),
                                   creationflags=0x08000000 if sys.platform == "win32" else 0)
                f.write(f"uninstall exit code {r.returncode}\n")
                f.flush()
            # --ignore-installed: KiCad'in ortami sistem paketlerini de gorur (--system-site-packages); hepsi bu ortama kurulur ki
            # sistemdeki baska surumler (ya da sonradan yukseltilenler) viewer'i bozmasin.
            proc = subprocess.Popen(pip + ["install", "--no-input", "--disable-pip-version-check",
                                           "--only-binary", ":all:", "--ignore-installed", "--progress-bar", bar, "-r", str(DEPS)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=_pip_env(),
                                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                                    creationflags=0x08000000 if sys.platform == "win32" else 0)
            prog = _Progress(download_mb())
            finished = threading.Event()

            def pump():
                try:
                    for line in proc.stdout:
                        prog.feed(line)
                        if not line.startswith("Progress "):     # ham ilerleme satirlari gunlugu sisirmesin
                            f.write(line)
                            f.flush()
                    proc.wait()
                finally:
                    finished.set()

            threading.Thread(target=pump, daemon=True).start()
            cancelled = _show_progress(prog, proc, finished)
            finished.wait()
            rc = proc.returncode if proc.returncode is not None else proc.wait()
            f.write(f"\n{time.strftime('%H:%M:%S')} pip exit code {rc}{' (cancelled)' if cancelled else ''}\n")
        r = subprocess.CompletedProcess(proc.args, rc)
        misplaced = r.returncode == 0 and not cancelled and not _installed_here()
        if r.returncode == 0 and not cancelled and not misplaced:
            _marker().write_text(json.dumps({"deps": _deps_hash(), "time": time.time()}))
    except BaseException:
        if proc is not None:
            _kill_tree(proc)               # kurucu coktu: pip yarim kalmis ortami yazmaya devam etmesin
        raise
    finally:
        _drop_lock()                       # diyalogdan ONCE: hata mesaji acikken 3D Live yeniden denesin
    if cancelled:
        return 1                           # kullanici iptal etti: hata diyalogu yok; 3D Live yeniden sorar
    if misplaced:
        info("pip reported success, but the components were not installed into KiCad's plugin environment\n"
             f"({sys.prefix}).\n\nYour pip configuration probably redirects installs (pip.ini / pip.conf with "
             "\"target\", \"prefix\" or \"user\"). Remove that setting, then press 3D Live again.\n\n"
             f"Details: {log}", error=True)
        return 1
    if r.returncode != 0:
        try:                               # pip'in kendi hata satiri (internet, disk, engellenen dosya...): kullanici neyin bozuldugunu gorsun
            errs = [l.strip() for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("ERROR")]
        except OSError:
            errs = []
        why = f"{errs[-1][:400]}\n\n" if errs else ""
        info(f"Downloading IPCubed components failed.\n\n{why}Details: {log}\n\n"
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
