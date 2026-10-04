"""KiCad eklentisini kur: python -m ipcubed.install [--uninstall]

- <KiCad belgeler>/<surum>/plugins/ipcubed/ altina plugin.json + toggle.py + ikonlar
- viewer'i baslatmak icin launch.json (python yolu + calisma klasoru)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .ctl import config_dir

PLUGIN_ID = "io.github.ipcubed"
FOLDER = "ipcubed"


def documents_dir() -> Path:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)      # CSIDL_PERSONAL
        return Path(buf.value) / "KiCad"
    if sys.platform == "darwin":
        return Path.home() / "Documents" / "KiCad"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "kicad"


def plugin_dirs(version: str | None = None) -> list[Path]:
    base = documents_dir()
    vers = [version] if version else sorted((d.name for d in base.glob("[0-9]*.*") if d.is_dir()), reverse=True)
    return [base / v / "plugins" / FOLDER for v in vers[:1]]


def make_icon(path: Path, dark: bool):
    from PIL import Image, ImageDraw
    S = 48
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fg = (235, 238, 242, 255) if dark else (40, 44, 52, 255)
    acc = (61, 139, 253, 255)
    # izometrik kup
    top = [(24, 6), (42, 15), (24, 24), (6, 15)]
    left = [(6, 15), (24, 24), (24, 43), (6, 34)]
    right = [(42, 15), (24, 24), (24, 43), (42, 34)]
    d.polygon(top, fill=acc)
    d.polygon(left, outline=fg, fill=(*fg[:3], 60))
    d.polygon(right, outline=fg, fill=(*fg[:3], 110))
    d.line(top + [top[0]], fill=fg, width=2)
    im.save(path)


def install(version: str | None = None) -> list[Path]:
    src = Path(__file__).with_name("ctl.py")
    out = []
    for dest in plugin_dirs(version):
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest / "toggle.py")
        make_icon(dest / "icon-light.png", dark=False)
        make_icon(dest / "icon-dark.png", dark=True)
        (dest / "plugin.json").write_text(json.dumps({
            "$schema": "https://go.kicad.org/api/schemas/v1",
            "identifier": PLUGIN_ID,
            "name": "3D Live",
            "description": "PCB duzenleyicinin uzerinde hizli, canli 3D gorunum (hizli 3D gorunum).",
            "runtime": {"type": "python", "min_version": "3.9"},
            "actions": [{
                "identifier": "toggle3d",
                "name": "3D Live",
                "description": "3D gorunumu ac/kapat",
                "show-button": True,
                "scopes": ["pcb"],
                "entrypoint": "toggle.py",
                "icons-light": ["icon-light.png"],
                "icons-dark": ["icon-dark.png"],
            }],
        }, indent=2), encoding="utf-8")
        out.append(dest)
    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "launch.json").write_text(json.dumps({
        "python": sys.executable,
        "cwd": str(Path(__file__).resolve().parents[1]),
    }, indent=2), encoding="utf-8")
    return out


def uninstall(version: str | None = None):
    for dest in plugin_dirs(version):
        shutil.rmtree(dest, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--version", help="KiCad surumu (orn. 10.0); bos ise en yenisi")
    a = ap.parse_args()
    if a.uninstall:
        uninstall(a.version)
        print("kaldirildi")
    else:
        for p in install(a.version):
            print("kuruldu:", p)
        print("KiCad'i yeniden baslatin.")
