"""Measure the download size of plugins/ipcubed/deps.txt per platform -> plugins/ipcubed/dep_sizes.json

python tools/dep_sizes.py   (needs network; run again when deps.txt changes)
The 3D Live button shows this number in its "download components?" dialog.
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / "plugins" / "ipcubed" / "deps.txt"
OUT = ROOT / "plugins" / "ipcubed" / "dep_sizes.json"
TARGETS = {                                    # key -> (pip --platform tags, python version)
    "win32": (["win_amd64"], "3.11"),
    "linux": (["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux1_x86_64"], "3.12"),
    "darwin": (["macosx_14_0_arm64", "macosx_11_0_arm64", "macosx_11_0_universal2"], "3.11"),
}


def _size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length") or 0)


def measure(platforms, py) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "report.json"
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--dry-run", "--ignore-installed", "--only-binary", ":all:",
               "--python-version", py, "--target", tmp, "--report", str(rep), "-r", str(DEPS)]
        for p in platforms:
            cmd += ["--platform", p]
        subprocess.run(cmd, check=True)
        urls = [i["download_info"]["url"] for i in json.loads(rep.read_text())["install"]]
    with ThreadPoolExecutor(16) as ex:
        return sum(ex.map(_size, urls))


if __name__ == "__main__":
    out = {}
    for key, (plats, py) in TARGETS.items():
        out[key] = round(measure(plats, py) / 2**20)
        print(key, out[key], "MB")
    OUT.write_text(json.dumps({"download_mb": out}, indent=2) + "\n")
