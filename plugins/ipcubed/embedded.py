"""Karta GOMULU 3D modeller (`kicad-embed://ad.step`).

Baska CAD'lerden (EasyEDA vb.) ice aktarim ve KiCad 8+ modelleri `.kicad_pcb` icine gomer (zstd + base64). Kart henuz kaydedilmemis
olabilecegi icin dosyadan degil, KiCad'den IPC ile (`board.get_as_string()`, bellekten, diske yazmadan) okunur.
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from .paths import cache_dir

SCHEME = "kicad-embed://"

# (file (name "x.step") (type other) (data |...|) (checksum "..."))  -- veri yalniz ilk ornekte bulunur
_FILE = re.compile(r'\(file\s*\(name\s+"([^"]+)"\)\s*\(type\s+\w+\)(.*?)\(checksum\s+"(\w+)"\)', re.S)
_DATA = re.compile(r"\(data\s*\|([^|]*)\|", re.S)


def is_embedded(raw: str) -> bool:
    return raw.startswith(SCHEME)


def _decode(b64: str) -> bytes | None:
    try:
        blob = base64.b64decode(re.sub(r"\s+", "", b64))
    except Exception:
        return None
    if blob[:4] == b"\x28\xb5\x2f\xfd":                       # zstd cercevesi
        try:
            import zstandard
            return zstandard.ZstdDecompressor().decompressobj().decompress(blob)
        except Exception:
            return None
    return blob                                               # sikistirilmamis


def extract_embedded(board_text: str, only: set[str] | None = None) -> dict[str, str]:
    """Kart metninden gomulu dosyalari cikar, onbellege yaz. -> {ad: yol}. `only`: yalniz bu adlar."""
    root = cache_dir().parent / "embedded"
    out: dict[str, str] = {}
    for m in _FILE.finditer(board_text):
        name, body, checksum = m.group(1), m.group(2), m.group(3)
        if name in out or (only is not None and name not in only):
            continue
        d = _DATA.search(body)
        if not d:
            continue                                          # ayni dosyanin veri icermeyen tekrari
        folder = root / checksum.lower()
        # Windows'ta gecersiz karakterli bir ad (: * ? " < > |) tek dosyayi bozsun, diger gomulu modelleri degil
        target = folder / (re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip(" .") or "model")
        try:
            if not target.exists():
                data = _decode(d.group(1))
                if data is None:
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(target)
        except OSError as e:
            from .log import _log
            _log(f"gomulu model yazilamadi: {name}: {e}")
            continue
        out[name] = str(target)
    return out


def needed_names(model_paths) -> set[str]:
    return {p[len(SCHEME):] for p in model_paths if is_embedded(p)}
