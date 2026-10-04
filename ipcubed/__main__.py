import argparse

if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="ipcubed")
    ap.add_argument("--screenshot", help="pencere acmadan PNG uret (test)")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--view", choices=["iso", "top", "bottom"], default="iso")
    ap.add_argument("--mask", choices=["Green", "Dark green", "Blue", "Red", "Black", "White", "Yellow", "Purple"], help="test: mask color")
    ap.add_argument("--style", choices=["Vivid", "Bright studio", "Realistic dark"], help="test: gorunum stili")
    ap.add_argument("--far", type=float, default=1.0, help="test: kamerayi uzaklastir (carpan)")
    ap.add_argument("--xray", action="store_true", help="test: tum katmanlar, saydam kart")
    ap.add_argument("--standalone", action="store_true", help="KiCad penceresine gomme, bagimsiz pencere ac")
    ap.add_argument("--show", action="store_true", help="acilir acilmaz 3D'yi goster")
    ap.add_argument("--legacy", action="store_true", help="eski glfw/pygfx penceresi")
    args = ap.parse_args()
    if args.screenshot or args.legacy:
        from .app import run
        run(args)
    else:
        import os
        import sys
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
