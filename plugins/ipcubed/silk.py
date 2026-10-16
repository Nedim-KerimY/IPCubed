"""Silkscreen: cizgi/yay/daire/poligon + yazi (vektor kontur). Dunya koordinati KiCad (Y asagi), mm.

Kenar durumlari:
- IPC footprint ic ogelerini MUTLAK koordinatta verir (ek donusum yok).
- keep_upright: 180 derece donuslerde acisi duzeltilir, hizalama DEGISMEZ (SVG ile olculdu).
- yazi tipi: '' = KiCad stroke fontu (DejaVu ile olcekli taklit); adli TrueType bulunursa o, yoksa DejaVu (KiCad da yedege duser).
- ~{overbar}, ^{ust}, _{alt} isaretleri sade metne indirgenir; cozulmemis ${VAR}'lar kart baglaminda genisletilir.
- Referans resimleri (non-plotting) KiCad'in 3D'sinde de yok: atlanir. Bozuk/sira disi ogeler tek tek atlanir (hepsi cokmez).
"""
from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field

import numpy as np

NM = 1e-6
SILK = {40: "top", 39: "bottom"}

UPRIGHT_SWAP = False         # SVG ile olculdu: KiCad keep_upright'ta hizalamayi cevirmiyor
EM_FACTOR = 1.42             # DejaVu buyuk harf yuksekligi 0.73 em -> KiCad stroke fontunda buyuk harf ~1.04 x yazi yuksekligi
WIDTH_FACTOR = 0.98          # SVG ile kalibre (FID1: KiCad 2.025 mm / DejaVu 1.659 mm @0.8)
CAP_H = 1.04                 # buyuk harf yuksekligi / yazi yuksekligi
BOTTOM_LIFT = 0.10           # alt hizalamada metin ~0.1 x boyut yukari oturur
TTF_EM = 1.0                 # TrueType: KiCad yazi yuksekligi ~ em
TTF_CAP = 0.72


EDGE_CUTS = 47
BOTTOM_LAYERS = {34, 41, 39, 37}       # alt yuz katmanlari (yazi aynalama icin)


@dataclass
class SilkData:
    shapes: dict = field(default_factory=lambda: {"top": [], "bottom": []})   # tuples
    texts: dict = field(default_factory=lambda: {"top": [], "bottom": []})    # dict'ler
    # bakir ve mask katmanlarindaki grafikler (logo, cutout, bakir yazi/sekil): layer_id -> liste
    extra_shapes: dict = field(default_factory=dict)
    extra_texts: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)       # footprint'lerin Edge.Cuts sekilleri (konnektor kesikleri): kart konturuna eklenir
    skipped: int = 0


def _rot(a_deg):
    a = math.radians(a_deg)
    return math.cos(a), math.sin(a)


def _xf(x, y, px, py, c, s):
    return px + x * c + y * s, py - x * s + y * c


# ------------------------------------------------------------------------------ sekiller
def _shape_items(proto_shape, px=0, py=0, c=1, s=0, rot=False):
    """protobuf shape -> [('seg',...),('poly',outline,holes,filled,w),...] dunya koord."""
    out = []
    attrs = proto_shape.attributes
    w = attrs.stroke.width.value_nm * NM
    filled = int(attrs.fill.fill_type) == 2          # GFT_FILLED
    kind = proto_shape.WhichOneof("geometry")
    T = (lambda p: _xf(p.x_nm * NM, p.y_nm * NM, px, py, c, s)) if rot else (lambda p: (p.x_nm * NM, p.y_nm * NM))
    if kind == "segment":
        a, b = T(proto_shape.segment.start), T(proto_shape.segment.end)
        out.append(("seg", a[0], a[1], b[0], b[1], w))
    elif kind == "rectangle":
        r = proto_shape.rectangle
        tl, br = r.top_left, r.bottom_right
        pts = [T(tl), T(type(tl)(x_nm=br.x_nm, y_nm=tl.y_nm)), T(br), T(type(tl)(x_nm=tl.x_nm, y_nm=br.y_nm))]
        out.append(("poly", np.array(pts), [], filled, w))
    elif kind == "circle":
        ce, rp = T(proto_shape.circle.center), T(proto_shape.circle.radius_point)
        out.append(("circle", ce[0], ce[1], math.hypot(rp[0] - ce[0], rp[1] - ce[1]), w, filled))
    elif kind == "arc":
        a = proto_shape.arc
        out.append(("arc", T(a.start), T(a.mid), T(a.end), w))
    elif kind == "polygon":
        for pw in proto_shape.polygon.polygons:
            def ring(r):
                return np.array([T(n.point) for n in r.nodes if n.HasField("point")])
            outline = ring(pw.outline)
            holes = [ring(h) for h in pw.holes]
            if len(outline) >= 3:
                out.append(("poly", outline, [h for h in holes if len(h) >= 3], filled, w))
    elif kind == "bezier":
        b = proto_shape.bezier
        p = [T(b.start), T(b.control1), T(b.control2), T(b.end)]
        t = np.linspace(0, 1, 16)[:, None]
        pts = ((1 - t) ** 3) * p[0] + 3 * ((1 - t) ** 2) * t * p[1] + 3 * (1 - t) * t * t * p[2] + t**3 * p[3]
        for a, b2 in zip(pts[:-1], pts[1:]):
            out.append(("seg", a[0], a[1], b2[0], b2[1], w))
    return out


def edge_polylines(items) -> list[list[tuple[float, float]]]:
    """Footprint Edge.Cuts sekil tuple'lari -> kart konturu polyline'lari (kicad_source._outline_from_shapes ile ayni bicim)."""
    from .copper import _arc_from_three
    out = []
    for it in items:
        try:
            kind = it[0]
            if kind == "seg":
                out.append([(it[1], it[2]), (it[3], it[4])])
            elif kind == "arc":
                seg = _arc_from_three(it[1], it[2], it[3], 0.0, 0, step=0.15)
                out.append([(float(seg[0][0]), float(seg[0][1]))] + [(float(r[2]), float(r[3])) for r in seg])
            elif kind == "circle":
                cx, cy, r = it[1], it[2], it[3]
                out.append([(cx + r * math.cos(2 * math.pi * i / 64), cy + r * math.sin(2 * math.pi * i / 64)) for i in range(65)])
            elif kind == "poly":
                for ring in [it[1]] + list(it[2]):
                    pts = [(float(x), float(y)) for x, y in ring]
                    if len(pts) >= 3:
                        out.append(pts + [pts[0]])
        except Exception:
            continue
    return out


# ------------------------------------------------------------------------------ yazilar
_MARKUP = re.compile(r"[~^_]\{([^{}]*)\}")


def clean_markup(s: str) -> str:
    """KiCad metin isaretlerini (~{overbar}, ^{ust}, _{alt}) sade metne indirge."""
    prev = None
    while prev != s:
        prev, s = s, _MARKUP.sub(r"\1", s)
    return s


def _knockout(t) -> bool:
    """BoardText.knockout (alan: Field.text icinde de BoardText)."""
    try:
        return bool(t.proto.knockout)
    except Exception:  # noqa: BLE001
        return False


def _text_dict(t, value, side):
    at = t.attributes
    angle = float(getattr(at.angle, "degrees", at.angle)) % 360.0
    h, v = int(at.horizontal_alignment), int(at.vertical_alignment)
    if getattr(at, "keep_upright", False) and 90.0 < angle <= 270.0:
        angle -= 180.0
        if UPRIGHT_SWAP:
            h = {1: 3, 3: 1}.get(h, h)
            v = {1: 3, 3: 1}.get(v, v)
    return dict(
        value=clean_markup(value), x=t.position.x * NM, y=t.position.y * NM, angle=angle,
        sx=at.size.x * NM, sy=at.size.y * NM,
        stroke=(at.stroke_width * NM) if hasattr(at, "stroke_width") else 0.15,
        halign=h, valign=v, font=(at.font_name or ""),
        bold=bool(at.bold), italic=bool(at.italic), mirrored=bool(at.mirrored) or side == "bottom",
        line_spacing=at.line_spacing or 1.0,
        knockout=_knockout(t),
    )


def _bucket(sd: SilkData, lay: int, extra: set):
    """katman -> (sekil listesi, yazi listesi) ya da None (ilgilenilmeyen katman)."""
    side = SILK.get(lay)
    if side is not None:
        return sd.shapes[side], sd.texts[side]
    if lay in extra:
        return sd.extra_shapes.setdefault(lay, []), sd.extra_texts.setdefault(lay, [])
    return None


def fp_silk_part(f, extra) -> SilkData:
    """Tek footprint'in silk/bakir/mask katmanlarindaki sekil ve yazilari (mutlak koordinat). Ham footprint nesnesi (agir) saklanmaz,
    yalnizca bu hafif ozet saklanir."""
    sd = SilkData()
    try:
        ref = f.reference_field.text.value
        val = f.value_field.text.value
        for it in f.definition.items:
            lay = int(it.layer) if hasattr(it, "layer") else None
            if lay == EDGE_CUTS and type(it).__name__ == "BoardShape":
                try:
                    sd.edges.extend(_shape_items(it.proto.shape))
                except Exception:
                    sd.skipped += 1
                continue
            b = _bucket(sd, lay, extra) if lay is not None else None
            if b is None or type(it).__name__ != "BoardShape":
                continue
            try:
                # IPC footprint ic ogelerini zaten MUTLAK (dunya) koordinatta verir
                b[0].extend(_shape_items(it.proto.shape))
            except Exception:
                sd.skipped += 1
        for t in f.texts_and_fields:
            try:
                lay = int(t.layer)
                b = _bucket(sd, lay, extra)
                if b is None:
                    continue
                txt = getattr(t, "text", t)
                if not txt.attributes.visible or (hasattr(t, "visible") and not t.visible):
                    continue
                v = (txt.value or "").replace("${REFERENCE}", ref).replace("${VALUE}", val)
                if v.strip():
                    b[1].append(_text_dict(txt, v, "bottom" if lay in BOTTOM_LAYERS else "top"))
            except Exception:
                sd.skipped += 1
    except Exception:
        sd.skipped += 1
    return sd


def _merge_part(sd: SilkData, p: SilkData):
    for side in ("top", "bottom"):
        sd.shapes[side].extend(p.shapes[side])
        sd.texts[side].extend(p.texts[side])
    for k, v in p.extra_shapes.items():
        sd.extra_shapes.setdefault(k, []).extend(v)
    for k, v in p.extra_texts.items():
        sd.extra_texts.setdefault(k, []).extend(v)
    sd.edges.extend(p.edges)
    sd.skipped += p.skipped


def fetch_silk(board, footprints, extra_layers=(), cache: dict | None = None) -> SilkData:
    """Silk + `extra_layers` (bakir ve mask katman id'leri) icin sekil ve yazilari topla.

    cache: footprint kiid -> ozet. `footprints` verilirse ozetler yeniden uretilip cache'e yazilir; bos verilirse cache kullanilir
    (ham footprint nesneleri ~400 MB tuttugundan saklanmaz)."""
    extra = set(extra_layers)
    sd = SilkData()
    if footprints:
        parts = []
        for f in footprints:
            p = fp_silk_part(f, extra)
            parts.append(p)
            if cache is not None:
                cache[f.id.value] = p
    else:
        parts = list((cache or {}).values())
    for p in parts:
        _merge_part(sd, p)
    try:
        for sh in board.get_shapes():
            b = _bucket(sd, int(sh.layer), extra)
            if b is not None:
                try:
                    b[0].extend(_shape_items(sh.proto.shape))
                except Exception:
                    sd.skipped += 1
    except Exception:
        pass
    _board_texts(board, sd, extra)
    _expand_variables(board, sd)
    return sd


def layer_geometry(sd: SilkData, lid: int):
    """Bir katmandaki (bakir/mask) grafik ve yazilarin birlesimi -> shapely (KiCad koord., Y asagi) ya da None."""
    from shapely.ops import unary_union
    geoms = shape_geometry(sd.extra_shapes.get(lid, []))
    for t in sd.extra_texts.get(lid, []):
        try:
            g = text_geometry(t)
            if g is not None and not g.is_empty:
                geoms.append(g.buffer(max(t["stroke"], 0.05) * 0.18, quad_segs=1) if t["stroke"] > 0 and not t.get("knockout") else g)
        except Exception:
            continue
    if not geoms:
        return None
    u = unary_union(geoms)
    return None if u.is_empty else u


def _board_texts(board, sd: SilkData, extra=()):
    extra = set(extra)
    try:
        from kipy.proto.common.types import KiCadObjectType as KOT
        for t in board.get_items([KOT.KOT_PCB_TEXT]):
            lay = int(t.layer)
            b = _bucket(sd, lay, extra)
            if b is not None and t.attributes.visible and (t.value or "").strip():
                b[1].append(_text_dict(t, t.value, "bottom" if lay in BOTTOM_LAYERS else "top"))
    except Exception:
        sd.skipped += 1
    try:                                    # metin kutulari: metni kutunun hizalama kosesine koy
        from kipy.proto.common.types import KiCadObjectType as KOT
        for tb in board.get_items([KOT.KOT_PCB_TEXTBOX]):
            lay = int(tb.layer)
            b = _bucket(sd, lay, extra)
            side = "bottom" if lay in BOTTOM_LAYERS else "top"
            if b is None:
                continue
            p = tb.proto.textbox
            at = p.attributes
            tl, br = p.top_left, p.bottom_right
            h = int(at.horizontal_alignment)
            v = int(at.vertical_alignment)
            x = {1: tl.x_nm, 2: (tl.x_nm + br.x_nm) / 2, 3: br.x_nm}.get(h, tl.x_nm) * NM
            y = {1: tl.y_nm, 2: (tl.y_nm + br.y_nm) / 2, 3: br.y_nm}.get(v, tl.y_nm) * NM

            class _T:                        # _text_dict'in bekledigi arayuz
                attributes = None
                position = None
            tt = _T()
            tt.attributes = _AttrsView(at)
            tt.position = type("P", (), {"x": x / NM, "y": y / NM})()
            if p.text.strip():
                b[1].append(_text_dict(tt, p.text, side))
    except Exception:
        sd.skipped += 1


class _AttrsView:
    """protobuf TextAttributes -> kipy benzeri ozellikler (metin kutulari icin)."""

    def __init__(self, a):
        self.angle = a.angle.value_degrees
        self.horizontal_alignment = int(a.horizontal_alignment)
        self.vertical_alignment = int(a.vertical_alignment)
        self.keep_upright = a.keep_upright
        self.size = type("S", (), {"x": a.size.x_nm, "y": a.size.y_nm})()
        self.stroke_width = a.stroke_width.value_nm
        self.font_name = a.font_name
        self.bold, self.italic, self.mirrored = a.bold, a.italic, a.mirrored
        self.line_spacing = a.line_spacing
        self.visible = True


def _expand_variables(board, sd: SilkData):
    """Cozulmemis ${VAR}'lari kart baglaminda genislet (REVISION, TITLE...)."""
    items = [t for side in list(sd.texts.values()) + list(sd.extra_texts.values()) for t in side if "${" in t["value"]]
    if not items:
        return
    try:
        vals = board.expand_text_variables([t["value"] for t in items])
        for t, v in zip(items, vals):
            t["value"] = clean_markup(v)
    except Exception:
        sd.skipped += 1


# ------------------------------------------------------------------------------ geometri
def _halign_factor(h: int) -> float:
    return {1: 0.0, 2: -0.5, 3: -1.0}.get(h, 0.0)       # LEFT, CENTER, RIGHT


def _valign_factor(v: int) -> float:
    return {1: -1.0, 2: -0.5, 3: 0.0}.get(v, -0.5)      # TOP, CENTER, BOTTOM


_font_cache: dict = {}


def _font_props(name: str, bold: bool, italic: bool):
    """(FontProperties, ttf_mi). Adli font bulunamazsa DejaVu'ya duser (KiCad da yedek font kullanir)."""
    key = (name, bold, italic)
    hit = _font_cache.get(key)
    if hit is not None:
        return hit
    from matplotlib import font_manager as fm
    weight, style = ("bold" if bold else "normal"), ("italic" if italic else "normal")
    prop, ttf = None, False
    if name and name.lower() not in ("kicad font", "newstroke"):
        try:
            cand = fm.FontProperties(family=name, weight=weight, style=style)
            fm.findfont(cand, fallback_to_default=False)
            prop, ttf = cand, True
        except Exception:
            prop, ttf = None, bool(name)         # bulunamadi: DejaVu, TrueType olceginde
    if prop is None:
        prop = fm.FontProperties(family="DejaVu Sans", weight=weight, style=style)
    _font_cache[key] = (prop, ttf)
    return prop, ttf


def _glyph_geom(line: str, em: float, prop):
    from matplotlib.textpath import TextPath
    from shapely.geometry import Polygon
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")            # eksik glif uyarilari
        path = TextPath((0, 0), line, size=em, prop=prop)
    geom = None
    for pts in path.to_polygons(closed_only=True):
        if len(pts) < 3:
            continue
        g = Polygon(pts)
        if not g.is_valid:
            g = g.buffer(0)
        geom = g if geom is None else geom.symmetric_difference(g)
    return geom


def text_geometry(t: dict):
    """Yazi -> shapely geometri (KiCad dunya koord., Y asagi)."""
    from shapely import affinity
    from shapely.ops import unary_union
    prop, ttf = _font_props(t.get("font", ""), t["bold"], t["italic"])
    lines = t["value"].replace("\\n", "\n").split("\n")
    if ttf:
        em, cap, wf = t["sy"] * TTF_EM, TTF_CAP, 1.0
    else:
        em, cap, wf = t["sy"] * EM_FACTOR, CAP_H, WIDTH_FACTOR
    lh = t["sy"] * 1.62 * t["line_spacing"]
    geoms = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        g = _glyph_geom(line, em, prop)
        if g is None or g.is_empty:
            continue
        g = affinity.scale(g, wf, 1.0, origin=(0, 0))
        x0, y0, x1, y1 = g.bounds
        g = affinity.translate(g, -x0 + _halign_factor(t["halign"]) * (x1 - x0), -i * lh)
        geoms.append(g)
    if not geoms:
        return None
    g = unary_union(geoms)
    # metin kutusu: ilk satirin ustu (cap) ile son satirin taban cizgisi (-(n-1)*lh) arasi
    top_y, bot_y = t["sy"] * cap, -(len(lines) - 1) * lh
    f = {1: 0.0, 2: 0.5, 3: 1.0}.get(t["valign"], 0.5)
    dy = -(top_y + f * (bot_y - top_y)) + (t["sy"] * BOTTOM_LIFT if t["valign"] == 3 else 0.0)
    g = affinity.translate(g, 0, dy)
    if t.get("knockout"):
        # KiCad "knockout": yazi kutusu dolu basilir, harfler bosluk kalir. Kenar payi KiCad'deki gibi
        # max(kalinlik, yukseklik/9). Harfler kalem kalinligiyla kalinlastirilir (build_silk bu geometriyi bir daha kalinlastirmaz).
        from shapely.geometry import box
        pen = max(t["stroke"], 0.0)
        glyphs = g.buffer(max(pen, 0.05) * 0.18, quad_segs=1) if pen > 0 else g
        m = max(pen, t["sy"] / 9.0)
        x0, y0, x1, y1 = glyphs.bounds
        g = box(x0 - m, y0 - m, x1 + m, y1 + m).difference(glyphs)
    g = affinity.scale(g, 1, -1, origin=(0, 0))          # font Y yukari -> KiCad Y asagi
    if t["mirrored"]:
        g = affinity.scale(g, -1, 1, origin=(0, 0))
    c, s = _rot(t["angle"])
    return affinity.affine_transform(g, [c, s, -s, c, t["x"], t["y"]])


def shape_geometry(items):
    """Silk sekil tuple'lari -> shapely geometri listesi (KiCad dunya koord.)."""
    from shapely.geometry import LineString, Point, Polygon
    out = []
    for it in items:
        kind = it[0]
        try:
            if kind == "seg":
                _, x1, y1, x2, y2, w = it
                out.append(LineString([(x1, y1), (x2, y2)]).buffer(max(w, 0.02) / 2, quad_segs=3))
            elif kind == "circle":
                _, cx, cy, r, w, filled = it
                ww = max(w, 0.02)
                if filled:
                    out.append(Point(cx, cy).buffer(r + ww / 2, quad_segs=8))
                else:
                    out.append(Point(cx, cy).buffer(r + ww / 2, quad_segs=8).difference(Point(cx, cy).buffer(max(r - ww / 2, 0.001), quad_segs=8)))
            elif kind == "arc":
                _, s_, m_, e_, w = it
                from .copper import _arc_from_three
                seg = _arc_from_three(s_, m_, e_, max(w, 0.02), 0, step=0.15)
                pts = [(seg[0][0], seg[0][1])] + [(r[2], r[3]) for r in seg]
                out.append(LineString(pts).buffer(max(w, 0.02) / 2, quad_segs=3))
            elif kind == "poly":
                _, outline, holes, filled, w = it
                pg = Polygon(outline, holes)
                if not pg.is_valid:
                    pg = pg.buffer(0)
                if filled:
                    out.append(pg.buffer(max(w, 0.0) / 2))
                else:
                    out.append(pg.exterior.buffer(max(w, 0.02) / 2, quad_segs=2))
        except Exception:
            continue
    return out


def build_silk(sd: SilkData, side: str, z: float, outline=None):
    """-> (P,N,T,G): yassi mesh (ust: +Z, alt: -Z)."""
    from shapely import affinity
    from shapely.ops import unary_union
    from .prism import polygon_prisms
    geoms = shape_geometry(sd.shapes[side])
    for t in sd.texts[side]:
        try:
            g = text_geometry(t)
            if g is not None and not g.is_empty:
                geoms.append(g.buffer(max(t["stroke"], 0.05) * 0.18, quad_segs=1) if t["stroke"] > 0 and not t.get("knockout") else g)
        except Exception:
            continue
    if not geoms:
        return None
    u = unary_union(geoms)
    u = affinity.scale(u, 1, -1, origin=(0, 0))          # sahne: Y yukari
    from .geometry import board_clip
    board, outside = board_clip(outline)
    if board is not None and u.intersects(outside):       # kart disina / cutout icine tasan silk kirpilir (KiCad 3D gibi)
        u = u.intersection(board)
        if u.is_empty:
            return None
    polys = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
    if side == "top":
        return polygon_prisms(polys, z, z, top_cap=True, bottom_cap=False)
    return polygon_prisms(polys, z, z, top_cap=False, bottom_cap=True)
