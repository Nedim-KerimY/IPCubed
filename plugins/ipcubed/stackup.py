"""Kart stackup'i: katman sirasi, kalinliklar ve z araliklari (mm, kart alti z=0)."""
from __future__ import annotations

from dataclasses import dataclass, field

NM = 1e-6
BL_F_CU, BL_B_CU = 3, 34
BL_F_SILK, BL_B_SILK, BL_F_MASK, BL_B_MASK = 40, 39, 42, 41
T_COPPER, T_DIELECTRIC, T_SILK, T_MASK, T_PASTE = 1, 2, 3, 4, 5


@dataclass
class StackLayer:
    kind: str            # copper | dielectric | mask | silk | paste
    name: str
    layer_id: int
    thickness: float     # mm
    z0: float = 0.0
    z1: float = 0.0
    side: str | None = None      # top | bottom (outer katmanlar icin)

    @property
    def key(self) -> str:
        if self.kind == "copper":
            return f"cu:{self.layer_id}"
        if self.kind == "dielectric":
            return f"diel:{self.layer_id}"
        return f"{self.kind}:{self.side}"


@dataclass
class Stackup:
    layers: list[StackLayer] = field(default_factory=list)       # ustten alta
    thickness: float = 1.6                                       # bakir + dielektrik
    mask_t: float = 0.01
    silk_t: float = 0.01
    finish: str = ""                                             # yuzey kaplama (ENIG, HASL...)

    def copper(self) -> list[StackLayer]:
        return [l for l in self.layers if l.kind == "copper"]

    def by_id(self, lid: int):
        return next((l for l in self.layers if l.kind == "copper" and l.layer_id == lid), None)


FINISH_COLORS = [   # (anahtar kelimeler, renk, gorunen ad)
    (("enig", "immersion gold", "gold"), "#e8c46a", "ENIG / gold"),
    (("hard gold",), "#f0cf66", "Hard gold"),
    (("hasl", "hal", "lead", "solder", "tin"), "#c9ccd1", "HASL / tin (silver)"),
    (("silver",), "#dcdfe2", "Immersion silver"),
    (("osp", "none", "copper", "organic"), "#d98a4f", "OSP / bare copper"),
]


def finish_color(name: str) -> str:
    """Kartin yuzey kaplama turunden varsayilan renk."""
    n = (name or "").lower()
    for keys, color, _ in FINISH_COLORS:
        if any(k in n for k in keys):
            return color
    return FINISH_COLORS[0][1]


def default_stackup() -> Stackup:
    s = Stackup()
    s.layers = [StackLayer("copper", "F.Cu", BL_F_CU, 0.035, side="top"),
                StackLayer("dielectric", "Dielectric 1", 1, 1.51),
                StackLayer("copper", "B.Cu", BL_B_CU, 0.035, side="bottom")]
    return _assign_z(s)


def _assign_z(s: Stackup) -> Stackup:
    z = 0.0
    n = 0
    for l in reversed(s.layers):
        if l.kind in ("copper", "dielectric"):
            l.z0, l.z1 = z, z + l.thickness
            z = l.z1
    s.thickness = z
    top, bot = s.thickness, 0.0
    for l in s.layers:
        if l.kind == "mask":
            l.z0, l.z1 = (top, top + l.thickness) if l.side == "top" else (bot - l.thickness, bot)
        elif l.kind in ("silk", "paste"):
            base = top + s.mask_t if l.side == "top" else bot - s.mask_t
            l.z0 = l.z1 = base
    return s


def fetch_stackup(board) -> Stackup:
    try:
        st = board.get_stackup()
    except Exception:
        return default_stackup()
    s = Stackup()
    try:
        s.finish = str(getattr(st.finish, "type_name", "") or "")
    except Exception:
        s.finish = ""
    layers = list(st.layers)
    if not layers:
        d = default_stackup()
        d.finish = s.finish
        return d
    seen_copper_first = False
    n_diel = 0
    last_copper_idx = max((i for i, l in enumerate(layers) if int(l.type) == T_COPPER), default=-1)
    for i, l in enumerate(layers):
        t = int(l.type)
        lid = int(l.layer)
        th = l.thickness * NM
        if t == T_COPPER:
            side = "top" if not seen_copper_first else ("bottom" if i == last_copper_idx else None)
            seen_copper_first = True
            s.layers.append(StackLayer("copper", l.user_name or f"Cu{lid}", lid, th or 0.035, side=side))
        elif t == T_DIELECTRIC:
            n_diel += 1
            s.layers.append(StackLayer("dielectric", f"Dielectric {n_diel}", n_diel, th or 0.1))
        elif t == T_MASK:
            side = "top" if lid == BL_F_MASK else "bottom"
            s.mask_t = th or s.mask_t
            s.layers.append(StackLayer("mask", l.user_name or "Mask", lid, th or 0.01, side=side))
        elif t == T_SILK:
            side = "top" if lid == BL_F_SILK else "bottom"
            s.layers.append(StackLayer("silk", l.user_name or "Silk", lid, th or 0.01, side=side))
        elif t == T_PASTE:
            side = "top" if lid == 38 else "bottom"
            s.layers.append(StackLayer("paste", l.user_name or "Paste", lid, th, side=side))
    return _assign_z(s)
