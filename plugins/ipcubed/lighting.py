"""Proseduel studyo ortam haritasi (yansima/aydinlatma icin). Dunya Z-yukari: +Z gokyuzu, -Z zemin."""
from __future__ import annotations

import math

import numpy as np

from . import compat  # noqa: F401
import pygfx as gfx


def _dirs(face: int, n: int):
    """Kup yuzu piksel merkezleri -> birim yon vektorleri (OpenGL kup eslemesi)."""
    u = (np.arange(n) + 0.5) / n * 2 - 1
    sc, tc = np.meshgrid(u, u)           # tc satir (yukaridan asagi)
    if face == 0:   d = np.stack([np.ones_like(sc), -tc, -sc], -1)
    elif face == 1: d = np.stack([-np.ones_like(sc), -tc, sc], -1)
    elif face == 2: d = np.stack([sc, np.ones_like(sc), tc], -1)
    elif face == 3: d = np.stack([sc, -np.ones_like(sc), -tc], -1)
    elif face == 4: d = np.stack([sc, -tc, np.ones_like(sc)], -1)
    else:           d = np.stack([-sc, -tc, -np.ones_like(sc)], -1)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def _radiance(d: np.ndarray) -> np.ndarray:
    """Studyo: yumusak gokyuzu gradyani, koyu zemin, iki genis softbox + ince kenar isigi. (0..1 sRGB)."""
    # KOYU taban + parlak, KESKIN softbox'lar: yansima yalnizca vurgu noktalarinda gorunur.
    # Acik gri bir gokyuzu tum yuzeylere beyazimsi "sis" ortusu ekler (lake/metal yansimasi).
    z = d[..., 2]
    sky = 0.035 + 0.075 * np.clip(z, 0, 1) ** 1.2
    ground = 0.02 + 0.03 * np.clip(1 + z, 0, 1)
    base = np.where(z >= 0, sky, ground)
    L = np.stack([base * 0.92, base * 1.0, base * 1.12], -1)           # hafif soguk ton

    def lobe(axis, power, gain, tint=(1, 1, 1)):
        a = np.asarray(axis, float); a = a / np.linalg.norm(a)
        w = np.clip((d @ a), 0, 1) ** power * gain
        return w[..., None] * np.asarray(tint)[None, None, :]

    L = L + lobe((0.35, -0.55, 1.0), 60, 1.0)                         # ana softbox (sag-on ust), keskin
    L = L + lobe((-0.65, 0.30, 0.55), 40, 0.60, (0.85, 0.93, 1.0))    # dolgu (soguk), keskin
    L = L + lobe((0.10, 1.0, 0.30), 70, 0.45)                         # arka kenar isigi
    return np.clip(L, 0, 1)


def make_environment(size: int = 64) -> gfx.Texture:
    faces = []
    for f in range(6):
        rgb = (_radiance(_dirs(f, size)) * 255).astype(np.uint8)
        faces.append(np.concatenate([rgb, np.full((size, size, 1), 255, np.uint8)], -1))
    data = np.ascontiguousarray(np.stack(faces))                    # (6,S,S,4)
    return gfx.Texture(data, dim=2, size=(size, size, 6), generate_mipmaps=True)
