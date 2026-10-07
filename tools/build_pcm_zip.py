"""Build the KiCad Plugin and Content Manager package: python tools/build_pcm_zip.py [out_dir]

Produces IPCubed-<version>-pcm.zip (metadata.json + plugins/ + resources/ at the archive root) for
KiCad > Plugin and Content Manager > Install from File...
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"__pycache__", ".pytest_cache"}


def build(out_dir: Path) -> Path:
    meta = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    version = meta["versions"][0]["version"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"IPCubed-{version}-pcm.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "metadata.json", "metadata.json")
        for folder in ("plugins", "resources"):
            for p in sorted((ROOT / folder).rglob("*")):
                if p.is_file() and not SKIP & set(p.parts) and p.suffix not in (".pyc", ".pyo"):
                    z.write(p, p.relative_to(ROOT).as_posix())
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"))
