"""Kart govdesi: dielektrik levhalar ve lehim maskeleri (acikliklari pad/via'dan eksilmis, ayri mesh)."""
from __future__ import annotations

import numpy as np

from .copper import CopperData, _drill_shape, hole_segs, pad_polygon, via_mask_open
from .geometry import outline_to_polygon
from .prism import polygon_prisms
from .stackup import Stackup

BIG_HOLE = 0.55          # mm: lehim maskesi govdesinde yalniz bu buyuklukteki / NPTH delikler acilir


def _big_holes(cd: CopperData):
    return [_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle)
            for p in cd.pads if p.drill_w >= BIG_HOLE or (p.npth and p.drill_w > 0)]


def _npth_holes(cd: CopperData):
    """Kaplamasiz (NPTH) delikler: dielektrik duvari yalniz bunlar icin gerekir."""
    from shapely.geometry import Point
    out = []
    for p in cd.pads:
        if p.npth and p.drill_w > 0 and p.drill_h > 0:
            if abs(p.drill_w - p.drill_h) < 1e-6:
                out.append(Point(p.x, -p.y).buffer(p.drill_w / 2, quad_segs=hole_segs(p.drill_w)))
            else:
                out.append(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
    return out


def _all_holes(cd: CopperData):
    """Dielektrik (FR4/prepreg) levhalardan kesilecek TUM delikler: PTH/NPTH pad'ler ve via'lar (dusuk poligon)."""
    from shapely.geometry import Point
    holes = []
    for p in cd.pads:
        if p.drill_w > 0 and p.drill_h > 0:
            if abs(p.drill_w - p.drill_h) < 1e-6:
                holes.append(Point(p.x, -p.y).buffer(p.drill_w / 2, quad_segs=hole_segs(p.drill_w)))
            else:
                holes.append(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
    v = cd.vias
    for x, y, d, dr in v.xyd:
        if dr > 0:
            holes.append(Point(x, -y).buffer(dr / 2, quad_segs=hole_segs(dr)))
    return holes


TILES = 4                # gövde ve maske 4x4 karoya bolunur: via/pad degisince yalniz dokunulan karolar yeniden uretilir


def tile_boxes(bounds, n: int = TILES):
    """Kart sinir kutusu (sahne koord.) -> n*n dikdortgen (x0, y0, x1, y1). Komsu karolar ortak kenari paylasir (dikis yok)."""
    x0, y0, x1, y1 = bounds
    x0 -= 1.0; y0 -= 1.0; x1 += 1.0; y1 += 1.0
    xs = np.linspace(x0, x1, n + 1); ys = np.linspace(y0, y1, n + 1)
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1]) for j in range(n) for i in range(n)]


def tiles_for(bounds, pts, n: int = TILES) -> set:
    """pts: [(x, y, yaricap)] sahne koordinati -> dokunulan karo indeksleri."""
    out = set()
    for k, (a0, b0, a1, b1) in enumerate(tile_boxes(bounds, n)):
        for x, y, r in pts:
            if x + r >= a0 and x - r <= a1 and y + r >= b0 and y - r <= b1:
                out.add(k)
                break
    return out


def _pad_circle(p):
    """Pad'in sahne koordinatinda kapsayici cemberi (karo secimi icin)."""
    arr = p.front if p.front is not None and len(p.front) else p.back
    if arr is not None and len(arr):
        r = float(np.max(np.hypot(arr[:, 0] - p.x, arr[:, 1] - p.y)))
    else:
        r = max(p.drill_w, p.drill_h)
    return p.x, -p.y, r + 0.6


def build_body(outline_lines, stack: Stackup, cd: CopperData, mask_expansion: float, tent_vias=None, sd=None,
               only_mask: bool = False, cuts=None, tiles=None):
    """-> dict anahtar -> (P,N,T,G). Anahtarlar: diel:t<k>, diel:walls, mask:top:t<k>, mask:bottom:t<k>.

    tiles: None = hepsi (+ duvarlar); yoksa yalniz bu karolar (canli via/pad degisimi). only_mask: dielektrik uretilmez.
    cuts: {'top'|'bottom': shapely} onceden hesaplanmis maske-katmani grafik/yazi cutout'lari (sahne koordinatinda)."""
    from shapely.geometry import Point, box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    board = outline_to_polygon(outline_lines)
    if board is None:
        return {}
    boxes = tile_boxes(board.bounds)
    want = range(len(boxes)) if tiles is None else sorted(tiles)
    out = {}
    if tiles is not None:
        # Yalniz istenen karolara degen pad/via'lar islenir (shapely geometrisi uretmeden once, ucuz cember testiyle)
        import dataclasses
        wb = [boxes[k] for k in want]

        def near(x, y, r):
            return any(x + r >= a0 and x - r <= a1 and y + r >= b0 and y - r <= b1 for a0, b0, a1, b1 in wb)
        pads = [p for p in cd.pads if near(*_pad_circle(p))]
        v = cd.vias
        keep = [i for i in range(len(v.xyd)) if near(v.xyd[i][0], -v.xyd[i][1], v.xyd[i][2] / 2 + 0.6)]
        from .copper import ViaData
        vias = ViaData(np.asarray(v.xyd)[keep].reshape(-1, 4), np.asarray(v.nets)[keep], [v.layers[i] for i in keep],
                       np.asarray(v.cover)[keep].reshape(-1, 2), np.asarray(v.hide_drill)[keep] if len(v.hide_drill) else np.zeros(0, bool))
        cd = dataclasses.replace(cd, pads=pads, vias=vias, tracks={}, zones={})

    def by_tile(geoms):
        """Her karo icin o karoya degen geometriler (STRtree)."""
        if not geoms:
            return {k: [] for k in want}
        tree = STRtree(geoms)
        return {k: [geoms[i] for i in tree.query(box(*boxes[k]))] for k in want}

    tile_board = {k: board.intersection(box(*boxes[k])) for k in want}
    if not only_mask:
        diels = [l for l in stack.layers if l.kind == "dielectric"]
        if diels:
            z0 = min(l.z0 for l in diels); z1 = max(l.z1 for l in diels)
            holes = by_tile(_all_holes(cd))
            for k in want:
                tb = tile_board[k]
                if tb.is_empty:
                    out[f"diel:t{k}"] = polygon_prisms([], z0, z1)
                    continue
                cap = tb.difference(unary_union(holes[k])) if holes[k] else tb
                # Dielektrik levhalar opak ve ayni konturlu -> tek govde; karolarin yalniz ust/alt kapagi (dikis gorunmez)
                out[f"diel:t{k}"] = polygon_prisms([cap], z0, z1, bottom_cap=True, walls=False)
            if tiles is None:
                # Yan duvarlar: kart kenari + kaplamasiz (NPTH) delikler. Kaplamali deliklerde tup ayni yaricapta oldugu icin yok.
                npth = _npth_holes(cd)
                wall_body = board.difference(unary_union(npth)) if npth else board
                out["diel:walls"] = polygon_prisms([wall_body], z0, z1, top_cap=False, bottom_cap=False)

    def margin(p, side):
        m = p.mask_front if side == "top" else p.mask_back
        return mask_expansion if m is None else m

    big = by_tile(_big_holes(cd))
    for side in ("top", "bottom"):
        ml = next((l for l in stack.layers if l.kind == "mask" and l.side == side), None)
        if ml is None:
            continue
        lid_mask = 42 if side == "top" else 41
        openings = []
        for p in cd.pads:
            if lid_mask not in p.layers:
                continue
            g = pad_polygon(p, side)
            if g is None or g.is_empty:
                continue
            g = pad_polygon_solid(p, side) or g
            m = margin(p, side)
            if m:
                g = g.buffer(m, join_style=2, mitre_limit=2.0)
            if not g.is_empty:
                openings.append(g)
        v = cd.vias
        lid_cu = 3 if side == "top" else 34
        for i in range(len(v.xyd)):
            # via'nin KiCad kaplama modu (covered/uncovered/kurallardan); tent_vias ile hepsi gecersiz kilinabilir
            if lid_cu in v.layers[i] and via_mask_open(cd, i, side, tent_vias):
                x, y, d, dr = v.xyd[i]
                openings.append(Point(x, -y).buffer(max(d / 2 + mask_expansion, 0.01), quad_segs=5))
        if cuts is not None:
            cut = cuts.get(side)
            if cut is not None and not cut.is_empty:
                openings.append(cut)
        elif sd is not None:                # mask katmanindaki grafik/yazi = cutout (logo vb.)
            from .copper import _scene_geom
            from .silk import layer_geometry
            cut = _scene_geom(layer_geometry(sd, lid_mask))
            if cut is not None and not cut.is_empty:
                openings.append(cut)
        opn = by_tile(openings)
        z0, z1 = ml.z0, ml.z1
        for k in want:
            tb = tile_board[k]
            if tb.is_empty:
                out[f"{ml.key}:t{k}"] = polygon_prisms([], z0, z1)
                continue
            body = tb.difference(unary_union(big[k])) if big[k] else tb     # maske govdesi (tented via'lar kapali kalir)
            mask = body.difference(unary_union(opn[k])) if opn[k] else body
            # 10 um levhanin duvari gorunmez; maske 3 gecisle cizildigi icin duvarsiz
            if side == "top":
                out[f"{ml.key}:t{k}"] = polygon_prisms([mask], z0, z1, top_cap=True, bottom_cap=False, walls=False)
            else:
                out[f"{ml.key}:t{k}"] = polygon_prisms([mask], z0, z1, top_cap=False, bottom_cap=True, walls=False)
    return out


def pad_polygon_solid(p, side):
    """Pad outline'i (delik dusulmeden) - mask acikligi deligi de kapsamali."""
    from shapely.geometry import Polygon
    from .copper import _flip
    arr = p.front if side == "top" else p.back
    if arr is None or len(arr) < 3:
        return None
    g = Polygon(_flip(arr))
    return g if g.is_valid else g.buffer(0)
