import argparse

if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="ipcubed")
    ap.add_argument("--standalone", action="store_true", help="KiCad penceresine gomme, bagimsiz pencere ac")
    ap.add_argument("--show", action="store_true", help="acilir acilmaz 3D'yi goster")
    ap.add_argument("--persist", action="store_true", help="KiCad kapaninca cikma")
    args = ap.parse_args()
    import os
    import sys
    if os.environ.get("PYTHONPATH"):                   # KiCad'den sizan sistem yollari (bkz. ctl.clean_env): alt surecler de gormesin
        leaked = {os.path.normcase(os.path.abspath(p)) for p in os.environ.pop("PYTHONPATH").split(os.pathsep) if p}
        sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) not in leaked]
    for k in ("MATPLOTLIBRC", "PYTHONHOME"):
        os.environ.pop(k, None)
    if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "python.exe" and not os.environ.get("IPCUBED_FG"):
        # konsol penceresi acilmasin: pythonw ile (konsolsuz) yeniden baslat. Hata ayiklamak icin IPCUBED_FG=1.
        import subprocess
        from pathlib import Path
        pyw = Path(sys.executable).with_name("pythonw.exe")
        if pyw.exists():
            subprocess.Popen([str(pyw), "-m", "ipcubed", *sys.argv[1:]], cwd=str(Path(__file__).resolve().parents[1]),
                             creationflags=0x00000008 | 0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            raise SystemExit(0)
    if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM") and os.environ.get("DISPLAY") \
            and (os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland" or os.environ.get("GDK_BACKEND", "").lower() == "x11"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"        # X11 bindirmesi icin Qt'nin xcb eklentisi (XWayland dahil)
    from PySide6 import QtWidgets  # noqa: F401  Qt'yi rendercanvas'tan once sec
    from .qt_shell import run
    raise SystemExit(run(args))
