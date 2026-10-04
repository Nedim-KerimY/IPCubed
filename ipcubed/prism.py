"""Vektorlestirilmis prizma (extrude) uretimi. Girdi: sahne koordinati (Y yukari); cikti (P, N, T, tag).

tag: vertex basina tamsayi (ag/net kimligi gibi); None ise sifirlar.
"""
from __future__ import annotations

import numpy as np


def _empty():
    return (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint32), np.zeros(0, np.int32))


def merge(parts):
    """[(P,N,T,tag), ...] -> tek mesh."""
    parts = [p for p in parts if p is not None and len(p[0])]
    if not parts:
        return _empty()
    Ps, Ns, Ts, Gs, off = [], [], [], [], 0
    for P, N, T, G in parts:
        Ps.append(P); Ns.append(N); Ts.append(T + off); Gs.append(G); off += len(P)
    return np.concatenate(Ps), np.concatenate(Ns), np.concatenate(Ts), np.concatenate(Gs)


def capsule_prisms(segs: np.ndarray, z0: float, z1: float, tags: np.ndarray | None = None, k: int | None = None, bottom: bool = False):
    """segs (N,5): x1,y1,x2,y2,w. Yuvarlak uclu iz prizmalari: ust kapak + yan duvarlar (alt kapak yok).

    k verilmezse: dar izler (<0.2mm) k=2, genis izler k=4 (yay parcasi sayisi)."""
    N = len(segs)
    if N == 0:
        return _empty()
    if k is None:
        narrow = segs[:, 4] < 0.2
        parts = []
        for mask, kk in ((narrow, 2), (~narrow, 4)):
            if mask.any():
                parts.append(capsule_prisms(segs[mask], z0, z1, None if tags is None else tags[mask], kk, bottom))
        return merge(parts)
    a, b, w = segs[:, :2], segs[:, 2:4], segs[:, 4]
    d = b - a
    th = np.arctan2(d[:, 1], d[:, 0])
    r = w / 2
    ang_a = th[:, None] + np.pi / 2 + np.pi * np.arange(k + 1)[None] / k          # (N,k+1)  a ucu: +90..+270
    ang_b = th[:, None] - np.pi / 2 + np.pi * np.arange(k + 1)[None] / k          # b ucu: -90..+90
    ang = np.concatenate([ang_a, ang_b], axis=1)                                   # (N,m)
    m = 2 * (k + 1)
    ctr = np.concatenate([np.repeat(a[:, None], k + 1, 1), np.repeat(b[:, None], k + 1, 1)], axis=1)   # (N,m,2)
    cs = np.stack([np.cos(ang), np.sin(ang)], -1)                                  # (N,m,2) birim yonler
    ring = ctr + r[:, None, None] * cs

    # vertex dizilimi segment basina: [ust kapak m] [alt halka m] [ust halka m]
    top = np.concatenate([ring, np.full((N, m, 1), z0 if bottom else z1)], -1).reshape(-1, 3)      # kapak: ust katmanda +Z yuzu, alt katmanda DIS (-Z) yuzu
    bot = np.concatenate([ring, np.full((N, m, 1), z0)], -1).reshape(-1, 3)
    wtop = np.concatenate([ring, np.full((N, m, 1), z1)], -1).reshape(-1, 3)
    P = np.concatenate([top.reshape(N, m, 3), bot.reshape(N, m, 3), wtop.reshape(N, m, 3)], 1).reshape(-1, 3)

    nz = np.zeros((N, m, 3)); nz[..., 2] = -1.0 if bottom else 1.0
    nr = np.concatenate([cs, np.zeros((N, m, 1))], -1)
    Nn = np.concatenate([nz, nr, nr], 1).reshape(-1, 3)

    per = 3 * m
    base = (np.arange(N) * per)[:, None, None]
    i = np.arange(1, m - 1)
    cap = (np.stack([np.zeros_like(i), i + 1, i], 1) if bottom else np.stack([np.zeros_like(i), i, i + 1], 1))[None] + base      # fan
    j = np.arange(m); j2 = (j + 1) % m
    # duvar: (bot_j, bot_j2, top_j2), (bot_j, top_j2, top_j)
    w1 = np.stack([m + j, m + j2, 2 * m + j2], 1)
    w2 = np.stack([m + j, 2 * m + j2, 2 * m + j], 1)
    wall = np.concatenate([w1, w2])[None] + base
    T = np.concatenate([cap.reshape(-1, 3), wall.reshape(-1, 3)]).astype(np.uint32)
    G = np.repeat(tags if tags is not None else np.zeros(N, np.int32), per).astype(np.int32)
    return P.astype(np.float32), Nn.astype(np.float32), T, G


def _xyz(xy: np.ndarray, z: float) -> np.ndarray:
    out = np.empty((len(xy), 3), np.float64)
    out[:, :2] = xy
    out[:, 2] = z
    return out


def polygon_prisms(polys, z0: float, z1: float, tags=None, bottom_cap: bool = False, top_cap: bool = True, walls: bool = True):
    """shapely Polygon listesi (sahne koordinati) -> ust kapak (+opsiyonel alt) + yan duvarlar."""
    import mapbox_earcut as earcut
    from shapely.geometry.polygon import orient

    Ps, Ns, Ts, Gs, base = [], [], [], [], 0
    up = np.array([0, 0, 1.0]); down = np.array([0, 0, -1.0])
    walls = walls and z1 - z0 > 1e-9
    for idx, g in enumerate(polys):
        if g is None or g.is_empty:
            continue
        for poly in (g.geoms if g.geom_type in ("MultiPolygon", "GeometryCollection") else [g]):
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            poly = orient(poly, 1.0)
            rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in poly.interiors]
            rings = [r for r in rings if len(r) >= 3]
            if not rings:
                continue
            verts = np.concatenate(rings).astype(np.float64)
            lens = np.array([len(r) for r in rings])
            ends = np.cumsum(lens)
            n = len(verts)
            tag = 0 if tags is None else int(tags[idx])
            if top_cap or bottom_cap:
                tri = earcut.triangulate_float64(verts, ends.astype(np.uint32)).reshape(-1, 3).astype(np.uint32)
                if top_cap:
                    Ps.append(_xyz(verts, z1)); Ns.append(np.broadcast_to(up, (n, 3))); Gs.append(np.full(n, tag))
                    Ts.append(tri + base); base += n
                if bottom_cap:
                    Ps.append(_xyz(verts, z0)); Ns.append(np.broadcast_to(down, (n, 3))); Gs.append(np.full(n, tag))
                    Ts.append(tri[:, ::-1] + base); base += n
            if walls:
                nid = np.arange(1, n + 1)                      # her halka kendi icinde kapanir (tum halkalar tek seferde)
                nid[ends - 1] = ends - lens
                nxt = verts[nid]
                d = nxt - verts
                ln = np.hypot(d[:, 0], d[:, 1])
                ln[ln == 0] = 1
                nrm = np.zeros((n, 3))
                nrm[:, 0] = d[:, 1] / ln
                nrm[:, 1] = -d[:, 0] / ln
                Ps.append(np.concatenate([_xyz(verts, z0), _xyz(nxt, z0), _xyz(nxt, z1), _xyz(verts, z1)]))
                Ns.append(np.tile(nrm, (4, 1))); Gs.append(np.full(4 * n, tag))
                a = np.arange(n)
                Ts.append(np.concatenate([np.stack([a, n + a, 2 * n + a], 1), np.stack([a, 2 * n + a, 3 * n + a], 1)]).astype(np.uint32) + base)
                base += 4 * n
    if not Ps:
        return _empty()
    return (np.concatenate(Ps).astype(np.float32), np.concatenate(Ns).astype(np.float32),
            np.concatenate(Ts).astype(np.uint32), np.concatenate(Gs).astype(np.int32))