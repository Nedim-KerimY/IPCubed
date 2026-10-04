"""Kart outline -> shapely poligon -> extrude edilmis mesh; footprint model matrisleri."""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union


def _faces(lines, snap: float):
    """Edge.Cuts polyline'lari -> kapali yuzler (solid). `snap`: uc noktalari bu ızgaraya yuvarla (mikron boslugu kapat)."""
    def q(v):
        return round(v / snap) * snap

    segs = []
    for l in lines:
        pts = []
        for x, y in l:
            p = (q(x), q(-y))
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) >= 2:
            segs.append(LineString(pts))
    if not segs:
        return [], []
    faces = [Polygon(f.exterior) for f in polygonize(unary_union(segs)) if f.area > 1e-6]
    return faces, segs


def board_clip(outline_lines):
    """(kart poligonu, kart DISI bolge) sahne koordinatinda; dis hat yoksa (None, None).
    'Disari' = sinir kutusu ile kart arasindaki fark: cutout, kenara tasan yuva ve kart disi alan."""
    if not outline_lines:
        return None, None
    board = outline_to_polygon(outline_lines)
    if board is None or board.is_empty:
        return None, None
    minx, miny, maxx, maxy = board.bounds
    pad = 50.0
    outside = shapely.geometry.box(minx - pad, miny - pad, maxx + pad, maxy + pad).difference(board)
    shapely.prepare(outside)
    return board, outside


def _rings(lines, snap: float):
    """Edge.Cuts cizgilerini ZINCIRLERE (kapali halkalar) bagla. Kesisen ama uc paylasmayan zincirler ayri kalir
    (noktalama/bolme YOK): kenari kesen rotali yuva, kart halkasindan bagimsiz bir halka olarak gelir (KiCad gibi)."""
    from shapely.ops import linemerge

    def q(v):
        return round(v / snap) * snap

    segs = []
    for l in lines:
        pts = []
        for x, y in l:
            p = (q(x), q(-y))
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) >= 2:
            segs.append(LineString(pts))
    if not segs:
        return [], []
    merged = linemerge(segs)
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    rings = []
    for ls in parts:
        if ls.is_closed and len(ls.coords) >= 4:
            p = Polygon(ls)
            p = p if p.is_valid else p.buffer(0)
            if p.area > 1e-6:
                rings.append(p)
    return rings, segs


def outline_to_polygon(lines: list[list[tuple[float, float]]]):
    """Edge.Cuts -> kart poligonu (KiCad'in dis hat mantigi). Y, sahne icin negatiflenir (Y yukari).

    1) Zincirler (kapali halkalar) alan sirasina gore: en buyuk = kart. Sonraki halka mevcut karti kesiyor / iceriyorsa
       CUTOUT (cikarilir; kenara tasan rotali yuvalar dahil), hic kesismiyorsa ayri parca ya da cutout icindeki ada (eklenir).
    2) Uclar tam birlesmiyorsa 1 um / 10 um / 50 um tolerans (ice aktarilan kartlar).
    3) Hic halka yoksa: eski yuz (polygonize) yontemi, o da olmazsa tum cizgilerin sinir kutusu."""
    rings = []
    segs = []
    for snap in (0.001, 0.01, 0.05):
        rings, segs = _rings(lines, snap)
        if rings:
            break
    if rings:
        rings.sort(key=lambda p: p.area, reverse=True)
        board = rings[0]
        for r in rings[1:]:
            board = board.difference(r) if board.intersects(r) and board.intersection(r).area > 1e-6 else board.union(r)
        return board if not board.is_empty else None
    faces = []
    for snap in (0.001, 0.01, 0.05):
        faces, segs = _faces(lines, snap)
        if faces:
            break
    if faces:
        faces.sort(key=lambda p: p.area, reverse=True)
        board = faces[0]
        for r in faces[1:]:
            if board.contains(r.representative_point()):
                board = board.difference(r)
        return board
    if not segs:
        return None
    minx, miny, maxx, maxy = unary_union(segs).bounds
    return shapely.geometry.box(minx, miny, maxx, maxy)


def extrude_polygon(poly, z0: float, z1: float):
    """Poligon (delikli olabilir) -> (positions, normals, indices). Ust+alt kapak ve yan duvarlar."""
    import mapbox_earcut as earcut

    geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    P, N, I = [], [], []
    base = 0
    for g in geoms:
        g = shapely.geometry.polygon.orient(g, 1.0)  # dis CCW, delik CW
        rings = [np.asarray(g.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in g.interiors]
        verts = np.concatenate(rings).astype(np.float64)
        ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
        tri = earcut.triangulate_float64(verts, ends).reshape(-1, 3).astype(np.uint32)
        n = len(verts)
        # ust kapak (z1, normal +Z)
        P.append(np.c_[verts, np.full(n, z1)]); N.append(np.tile([0, 0, 1.0], (n, 1))); I.append(tri + base); base += n
        # alt kapak (z0, normal -Z, ters sarim)
        P.append(np.c_[verts, np.full(n, z0)]); N.append(np.tile([0, 0, -1.0], (n, 1))); I.append(tri[:, ::-1] + base); base += n
        # yan duvarlar
        for r in rings:
            m = len(r)
            nxt = np.roll(r, -1, axis=0)
            d = nxt - r
            ln = np.linalg.norm(d, axis=1, keepdims=True)
            ln[ln == 0] = 1
            nrm = np.c_[d[:, 1], -d[:, 0], np.zeros(m)] / np.c_[ln, ln, ln]  # CCW dis halka icin disa
            quad = np.concatenate([
                np.c_[r, np.full(m, z0)], np.c_[nxt, np.full(m, z0)],
                np.c_[nxt, np.full(m, z1)], np.c_[r, np.full(m, z1)],
            ])
            P.append(quad); N.append(np.tile(nrm, (4, 1)))
            a = np.arange(m)
            I.append(np.concatenate([
                np.c_[a, m + a, 2 * m + a] + base,
                np.c_[a, 2 * m + a, 3 * m + a] + base,
            ]).astype(np.uint32))
            base += 4 * m
    return (np.concatenate(P).astype(np.float32), np.concatenate(N).astype(np.float32),
            np.concatenate(I).astype(np.uint32))


def _rx(a): c, s = math.cos(a), math.sin(a); return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]])
def _ry(a): c, s = math.cos(a), math.sin(a); return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])
def _rz(a): c, s = math.cos(a), math.sin(a); return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])
def _t(x, y, z): m = np.eye(4); m[:3, 3] = (x, y, z); return m
def _s(x, y, z): return np.diag([x, y, z, 1.0])


def model_matrix(fp, mref, thickness: float, copper_top: float = 0.0) -> np.ndarray:
    """Footprint + model parametrelerinden dunya matrisi (kolon-vektor, 4x4).

    Sahne: X sag, Y yukari(KiCad -Y), Z yukseklik. Kart z=0 (alt) .. z=thickness (ust).
    """
    ang = math.radians(fp.angle)
    if fp.bottom:
        # alt yuz: Z=0'a, ayna (X ekseni etrafinda cevirme)
        m = _t(fp.x, -fp.y, 0.0) @ _rz(ang) @ _rx(math.pi)
    else:
        m = _t(fp.x, -fp.y, thickness) @ _rz(ang)
    ox, oy, oz = mref.offset
    rx, ry, rz = (math.radians(a) for a in mref.rotation)
    m = m @ _t(ox, oy, oz) @ _rz(-rz) @ _ry(-ry) @ _rx(-rx) @ _s(*mref.scale)
    return m
