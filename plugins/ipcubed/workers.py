"""Process-pool isci islevleri. pygfx/wgpu IMPORT ETMEZ: her isci sureci hafif kalir (bellek + baslangic suresi).

Buyuk veri (bakir: iz/zone/pad, silk) her ise ayri ayri pickle edilip gonderilmez: senkron sureci veriyi BIR KEZ bir dosyaya yazar,
islere yalniz dosya yolu gider ve her isci dosyayi bir kez okuyup onbellege alir. Boylece ana (render) surec hic buyuk pickle
yapmaz (eskiden yenileme basina ~15 is x ~10 MB = ana surecte GIL tutan ~1.5 sn).
"""
from __future__ import annotations

import pickle
from pathlib import Path

from .model_loader import load_model

_DATA: dict = {}


def _load(path: str) -> dict:
    d = _DATA.get(path)
    if d is None:
        with open(path, "rb") as f:
            d = pickle.load(f)
        _DATA.clear()                      # yalniz son anlik goruntu tutulur
        _DATA[path] = d
    return d


def _cd(x):
    """Bakir verisi: nesne ya da anlik goruntu dosyasi yolu."""
    return _load(x)["copper"] if isinstance(x, str) else x


def _sd(x):
    return _load(x)["silk"] if isinstance(x, str) else x


def _body_worker(outline, stack, cd, exp, tent, sd=None, tiles=None):
    from .body import build_body
    return build_body(outline, stack, _cd(cd), exp, tent, _sd(sd), tiles=tiles)


def _warm_imports():
    """Hizli isciyi isit: modulleri onceden yukle (ilk canli is ~0.3 sn import beklemesin)."""
    from . import body, copper, prism, silk  # noqa: F401
    return True


def _body_tiles_cuts(outline, stack, cd, exp, tent, cuts, tiles):
    """Govde + maske, yalniz verilen karolar; maske-katmani cutout'lari hazir verilir."""
    from .body import build_body
    return build_body(outline, stack, _cd(cd), exp, tent, None, cuts=cuts, tiles=tiles)


def _mask_worker(outline, stack, cd, exp, tent, cuts, sd=None, tiles=None):
    """Canli pad tasima: yalniz lehim maskesi (dokunulan karolar). cuts yoksa sd'den hesaplanir."""
    from .body import build_body
    return build_body(outline, stack, _cd(cd), exp, tent, _sd(sd), only_mask=True, cuts=cuts, tiles=tiles)


def _cuts_worker(sd):
    """Maske katmanindaki grafik/yazi cutout'lari (sahne koordinati) - bir kez hesaplanip hizli maske islerinde kullanilir."""
    from .copper import _scene_geom
    from .silk import layer_geometry
    sd = _sd(sd)
    if sd is None:
        return {}
    return {side: _scene_geom(layer_geometry(sd, 42 if side == "top" else 41)) for side in ("top", "bottom")}


def _track_worker(cd, lid, z0, z1, outline=None, side=None):
    """Yalniz iz mesh'i (iz duzenlemesinde hizli yol): {'cut:<id>': mesh}."""
    from .copper import build_copper_layer
    return {f"cut:{lid}": build_copper_layer(_cd(cd), lid, z0, z1, side, None, None, outline, mode="tracks")["tr"]}


def _via_worker(cd, layers, zmap, tent=None):
    """Tum via halkalari + tupleri (ayri mesh'ler, numpy)."""
    from .copper import build_via_meshes
    return build_via_meshes(_cd(cd), layers, zmap, tent)


def _zone_worker(cd, lid, z0, z1, side, outline=None):
    """Yalniz zone dolgusu mesh'i (zone degisiminde hizli yol): {'cuz:<id>': mesh}."""
    from .copper import build_copper_layer
    return {f"cuz:{lid}": build_copper_layer(_cd(cd), lid, z0, z1, side, None, None, outline, mode="zones")["zn"]}


def _cu_worker(cd, lid, z0, z1, side, sd=None, tent=None, outline=None):
    from .copper import build_copper_layer
    r = build_copper_layer(_cd(cd), lid, z0, z1, side, _sd(sd), tent, outline)
    out = {f"cu:{lid}": r["cu"], f"cut:{lid}": r["tr"], f"cuz:{lid}": r["zn"]}
    if r.get("finish") is not None:
        out[f"finish:{side}"] = r["finish"]
    return out


def _extras_worker(cd, stack):
    from .copper import build_barrels
    zmap = {l.layer_id: (l.z0, l.z1) for l in stack.copper()}
    return {"barrel": build_barrels(_cd(cd), zmap)}


def _silk_worker(sd, stack, outline=None):
    from .silk import build_silk
    sd = _sd(sd)
    out = {}
    if sd is None:
        return out
    for side in ("top", "bottom"):
        z = stack.thickness + stack.mask_t + 0.002 if side == "top" else -stack.mask_t - 0.002
        m = build_silk(sd, side, z, outline)
        if m is not None:
            out[f"silk:{side}"] = m
    return out


def _load_worker(path: str):
    m = load_model(Path(path))
    return None if m is None else (m.positions, m.normals, m.colors, m.indices)
