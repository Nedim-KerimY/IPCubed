"""Platformdan bagimsiz dizin ve model yolu cozumleme."""
from __future__ import annotations

import functools
import os
import re
import sys
from pathlib import Path


def _migrate(base: Path):
    """Eski adla ('kicadview') olusturulmus ayar/onbellek klasorunu yeni ada tasi (ayarlar ve model onbellegi korunur)."""
    old, new = base / "kicadview", base / "ipcubed"
    if old.is_dir() and not new.exists():
        try:
            old.rename(new)
        except OSError:
            pass


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    _migrate(base)
    d = base / "ipcubed" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    _migrate(base)
    d = base / "ipcubed"
    d.mkdir(parents=True, exist_ok=True)
    return d


_VAR = re.compile(r"\$\{([^}]+)\}|\$\(([^)]+)\)")
_MODEL_EXT = {".step", ".stp", ".stpz", ".igs", ".iges", ".wrl", ".wrz"}
_name_index: dict[Path, dict[str, Path]] = {}


def kicad_config_dirs() -> list[Path]:
    """KiCad kullanici ayar klasorleri (surum klasorleri, yeniden eskiye)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "kicad"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences" / "kicad"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kicad"
    if not base.is_dir():
        return []
    def ver(d: Path):                     # sayisal: metin olarak "9.0" > "10.0" olurdu ve KiCad 9 ayarlari 10'unkileri ezerdi
        return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", d.name))
    return sorted((d for d in base.iterdir() if d.is_dir() and d.name[:1].isdigit()), key=ver, reverse=True)


@functools.lru_cache(maxsize=1)
def kicad_path_vars() -> dict[str, str]:
    """kicad_common.json -> environment.vars (kullanici yol degiskenleri)."""
    import json
    out: dict[str, str] = {}
    for d in reversed(kicad_config_dirs()):
        try:
            data = json.loads((d / "kicad_common.json").read_text(encoding="utf-8"))
            out.update(data.get("environment", {}).get("vars") or {})
        except Exception:
            pass
    return out


_INDEX_SKIP = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv", ".history", "backups"}
_INDEX_MAX_ENTRIES = 40000        # buyuk depo / OneDrive klasorunde tarama arayuzu saniyelerce dondurmesin


def _index_for(root: Path) -> dict[str, Path]:
    idx = _name_index.get(root)
    if idx is None:
        idx = {}
        seen = 0
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if d.lower() not in _INDEX_SKIP and not d.startswith(".")]
            seen += len(filenames) + len(dirnames)
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in _MODEL_EXT:
                    idx.setdefault(fn.lower(), Path(dirpath) / fn)
            if seen > _INDEX_MAX_ENTRIES:
                break
        _name_index[root] = idx
    return idx


@functools.lru_cache(maxsize=1)
def default_model_dirs() -> tuple[Path, ...]:
    """KiCad'in kendi 3D kutuphanesi: viewer'a KICADn_3DMODEL_DIR ulasmasa da (eski/baska surec ortami) bulunur.
    Bagli KiCad'in programindan (owner pid) turetilir + bilinen kurulum yerleri."""
    cands: list[Path] = []
    try:
        from .ctl import kicad_pid
        import psutil
        pid = kicad_pid()
        if pid:
            exe = Path(psutil.Process(pid).exe())
            cands += [exe.parent.parent / "share" / "kicad" / "3dmodels",                 # Windows: <KiCad>\bin\..
                      exe.parent.parent / "SharedSupport" / "3dmodels"]                  # macOS: KiCad.app/Contents/MacOS/..
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "KiCad"
        try:
            cands += [d / "share" / "kicad" / "3dmodels" for d in sorted(pf.iterdir(), reverse=True)]
        except OSError:
            pass
    elif sys.platform == "darwin":
        cands.append(Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels"))
    else:
        cands += [Path("/usr/share/kicad/3dmodels"), Path("/usr/local/share/kicad/3dmodels")]
    out = []
    for c in cands:
        if c not in out and c.is_dir():
            out.append(c)
    return tuple(out)


def resolve_model_path(raw: str, project_dir: Path | None, env: dict[str, str] | None = None,
                       embedded: dict[str, str] | None = None) -> Path | None:
    """`${KIPRJMOD}/lib/x.step` gibi yollari gercek dosyaya cevir. `kicad-embed://ad` icin gomulu dosya haritasi. Bulunamazsa None."""
    if raw.startswith("kicad-embed://"):
        hit = (embedded or {}).get(raw[len("kicad-embed://"):])
        return Path(hit) if hit and Path(hit).is_file() else None
    p = _resolve_exact(raw, project_dir, env)
    if p is not None or project_dir is None or not Path(project_dir).is_dir():
        return p
    # son care: dosya adiyla proje klasorunde ara (tanimsiz degisken / baska makinenin mutlak yolu)
    name = re.split(r"[\\/]", raw)[-1].lower()
    return _index_for(project_dir).get(name)


def _resolve_exact(raw: str, project_dir: Path | None, env: dict[str, str] | None = None) -> Path | None:
    env = {**kicad_path_vars(), **os.environ, **(env or {})}
    if project_dir is not None:
        env["KIPRJMOD"] = str(project_dir)

    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))

    p = Path(_VAR.sub(sub, raw))
    if p.is_file():
        return p
    # KiCad surum degiskenleri (KICAD9_3DMODEL_DIR vb.) farkli surumde tanimsiz olabilir; hic tanimli degilse kurulumun kendi
    # 3D kutuphanesi denenir
    if "3DMODEL_DIR" in raw:
        tail = _VAR.sub("", raw).lstrip("/\\")
        dirs = [Path(v) for k, v in env.items() if k.endswith("3DMODEL_DIR") and v] + list(default_model_dirs())
        for d in dirs:
            cand = d / tail
            if cand.is_file():
                return cand
    return None
