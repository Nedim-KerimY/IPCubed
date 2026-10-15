"""Tum bakir katmanlari: kipy'den veri cek (ag kimlikleriyle) -> gercek kalinlikli 3D prizma mesh'leri.

Veri birimleri mm, KiCad koordinati (Y asagi). Mesh uretimi sahne koordinatinda (Y negatif, Z yukari).
Her bakir mesh'in vertex'leri bir `tag` (ag id'si) tasir: ileride ag/iz vurgulama icin.
"""
from __future__ import annotations

import math
import dataclasses
from dataclasses import dataclass, field

import numpy as np

NM = 1e-6
F_CU, B_CU = 3, 34
F_MASK, B_MASK = 42, 41
PSS_CIRCLE, PSS_RECT, PSS_OVAL, PSS_TRAP, PSS_ROUNDRECT, PSS_CHAMFER, PSS_CUSTOM = 1, 2, 3, 4, 5, 6, 7


@dataclass
class PadRec:
    x: float
    y: float
    angle: float
    layers: frozenset
    front: np.ndarray | None        # F.Cu pad outline (N,2)
    back: np.ndarray | None
    inner: np.ndarray | None        # ic katmanlar icin outline
    drill_w: float
    drill_h: float
    npth: bool
    net: int
    mask_front: float | None        # pad'e ozel mask marji (mm) ya da None
    mask_back: float | None
    kiid: str = ""                   # pad KIID (bayat poligon tespiti icin onceki anlik goruntuyle eslestirme)
    fp: str = ""                     # ust footprint KIID (canli tasima: pad'ler footprint ile birlikte hareket eder)


COVER_COVERED, COVER_UNCOVERED = 1, 2        # SolderMaskMode: MASKED(tented)=1, UNMASKED(acik)=2; 0/3 = kart kurali


@dataclass
class ViaData:
    xyd: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))     # x,y,dia,drill
    nets: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int32))
    layers: list = field(default_factory=list)                           # her via icin frozenset(layer id)
    cover: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.int8))   # (on, arka) ViaCoveringMode
    hide_drill: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))      # tikali/dolu/kapakli: delik gorunmez


@dataclass
class CopperData:
    tracks: dict = field(default_factory=dict)       # layer_id -> (N,6) x1,y1,x2,y2,w,net
    zones: dict = field(default_factory=dict)        # layer_id -> [(outline, holes, net)]
    vias: ViaData = field(default_factory=ViaData)
    pads: list = field(default_factory=list)
    net_names: list = field(default_factory=list)
    tent_rules: tuple = (True, True)                 # kartin tenting kurali (on, arka): FROM_DESIGN_RULES icin
    fp_index: dict = field(default_factory=dict)     # footprint KIID -> sira (mesh vertex etiketinde sahip kodu)


def via_mask_open(cd: "CopperData", i: int, side: str, override=None) -> bool:
    """Via'nin o yuzde lehim maskesi acikligi var mi?  override: None=via basina KiCad ayari, True=hepsi kapali(tented), False=hepsi acik."""
    if override is not None:
        return not override
    mode = int(cd.vias.cover[i][0 if side == "top" else 1])
    if mode == COVER_COVERED:
        return False
    if mode == COVER_UNCOVERED:
        return True
    return not cd.tent_rules[0 if side == "top" else 1]          # tasarim kurallarindan


# -------------------------------------------------------------------------------- veri cekme
def _arc_from_three(s, m, e, w, net=0, step=0.12):
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return np.array([[x1, y1, x3, y3, w, net]])
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (s, m, e))
    tau = 2 * math.pi
    ccw = ((a2 - a1) % tau) < ((a3 - a1) % tau)
    sweep = ((a3 - a1) % tau) if ccw else -((a1 - a3) % tau)
    n = max(3, int(abs(sweep) * r / step) + 1)
    ang = a1 + sweep * np.arange(n + 1) / n
    xs, ys = ux + r * np.cos(ang), uy + r * np.sin(ang)
    return np.c_[xs[:-1], ys[:-1], xs[1:], ys[1:], np.full(n, w), np.full(n, net)]


def _poly_pts(pl) -> np.ndarray:
    """PolyLine -> (N,2) mm. kipy sarmalayicilari yerine dogrudan protobuf dugumleri (zone dolgusunda yuz binlerce nokta)."""
    pts = []
    for n in pl._proto.nodes:
        if n.HasField("point"):
            p = n.point
            pts.append((p.x_nm * NM, p.y_nm * NM))
        elif n.HasField("arc"):
            a = n.arc
            seg = _arc_from_three((a.start.x_nm * NM, a.start.y_nm * NM), (a.mid.x_nm * NM, a.mid.y_nm * NM),
                                  (a.end.x_nm * NM, a.end.y_nm * NM), 0)
            pts.extend((s[0], s[1]) for s in seg)
            pts.append((seg[-1][2], seg[-1][3]))
    return np.array(pts, dtype=np.float64).reshape(-1, 2)


def _pw_outline(pw):
    return _poly_pts(pw.outline) if pw is not None else None


def _center(arr):
    return (arr.min(0) + arr.max(0)) / 2


def _rigid(arr, q, x, y, ang):
    """Onceki konumdaki poligonu (q: onceki PadRec) yeni pad konumuna/acisina tasir: pad kendi konumu etrafinda donup yeni konuma gider.
    KiCad koordinati (Y asagi): aci pozitif = saat yonunun tersi, x' = x c + y s, y' = -x s + y c."""
    import math
    d = math.radians(ang - q.angle)
    c, s = math.cos(d), math.sin(d)
    rel = arr - np.array([q.x, q.y])
    return np.c_[rel[:, 0] * c + rel[:, 1] * s, -rel[:, 0] * s + rel[:, 1] * c] + np.array([x, y])


_stale_fixed = 0           # son fetch_copper'da duzeltilen (KiCad'den bayat gelen) pad poligonu sayisi (teshis)


def _reconcile(arr_new, arr_prev, q, x, y, ang):
    """KiCad bir bileseni tasidiktan sonra pad poligonlarini BAYAT (eski konumda) dondurebilir: pad konumu yeni, sekil eski, ve bu
    bir sonraki degisiklige dek surer (tekrar istemek duzeltmez). Onceki (dogru) poligonu rijit donusumle ilerleterek beklenen sekli
    hesaplar; KiCad'in sekli beklenenden >0.02 mm saparsa (ve kose sayisi ayniysa = boyut degisimi degil) beklenen sekil kullanilir."""
    global _stale_fixed
    if arr_prev is None or len(arr_prev) < 3:
        return arr_new
    if arr_new is None or len(arr_new) < 3 or len(arr_new) != len(arr_prev):
        return arr_new                       # yeni/bos ya da sekil duzenlenmis: KiCad'e guven
    exp = _rigid(arr_prev, q, x, y, ang)
    if float(np.abs(_center(arr_new) - _center(exp)).max()) <= 0.02:
        return arr_new                       # taze
    _stale_fixed += 1
    return exp


def _recenter(arr, x, y, ang, size, offset):
    """Onceki kayit yokken (ilk yukleme) bayat poligonu yakala: poligon pad konumunu hic kapsamiyorsa KiCad eski konumdaki sekli
    dondurmustur (viewer yeniden acilinca/onbellek silinince de surer). Sekli pad konumuna tasir; pad boyutuna gore 90 derece
    donmusse cevirir. size/offset: bakir katmani boyutu ve ofseti (mm, pad yerel ekseninde)."""
    global _stale_fixed
    if arr is None or len(arr) < 3 or not size[0] or not size[1]:
        return arr
    import math
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)
    exp_c = np.array([x + offset[0] * c + offset[1] * s, y - offset[0] * s + offset[1] * c])
    cur_c = _center(arr)
    if float(np.abs(cur_c - exp_c).max()) <= max(size) / 2 + 0.05:
        return arr                           # pad konumunu kapsiyor: taze
    _stale_fixed += 1
    W, H = abs(size[0] * c) + abs(size[1] * s), abs(size[0] * s) + abs(size[1] * c)     # beklenen sinir kutusu
    w, h = arr.max(0) - arr.min(0)
    rel = arr - cur_c
    if abs(w - H) + abs(h - W) < abs(w - W) + abs(h - H) - 0.01:
        rel = np.c_[rel[:, 1], -rel[:, 0]]   # 90 derece (sinir kutusu dik)
    return rel + exp_c


def fetch_tracks(board, ids: set, nid) -> dict:
    """Tum izlar -> {katman: (N,6) x1,y1,x2,y2,kalinlik,ag}. Yaylar kisa dogru parcalarina bolunur."""
    tr: dict[int, list] = {}
    for t in board.get_tracks():
        L = int(t.layer)
        if L not in ids:
            continue
        w = t.width * NM
        n = nid(t.net)
        if type(t).__name__ == "ArcTrack":
            seg = _arc_from_three((t.start.x * NM, t.start.y * NM), (t.mid.x * NM, t.mid.y * NM),
                                  (t.end.x * NM, t.end.y * NM), w, n)
        else:
            seg = np.array([[t.start.x * NM, t.start.y * NM, t.end.x * NM, t.end.y * NM, w, n]])
        tr.setdefault(L, []).append(seg)
    return {L: np.concatenate(v) for L, v in tr.items()}


def make_nid(names: list | None = None):
    """Ag adi -> tamsayi (onceki eslemeyi koruyarak: kismi yenilemelerde etiketler tutarli kalir). -> (nid, adlar listesi)"""
    names = list(names) if names else [""]
    netid = {n: i for i, n in enumerate(names)}

    def nid(net) -> int:
        name = net.name if net is not None else ""
        v = netid.get(name)
        if v is None:
            v = netid[name] = len(names)
            names.append(name)
        return v
    return nid, names


def fetch_vias(board, ids: set, nid) -> ViaData:
    vias, vn, vl, vc, vh = [], [], [], [], []
    for v in board.get_vias():
        vias.append((v.position.x * NM, v.position.y * NM, v.diameter * NM, v.drill_diameter * NM))
        vn.append(nid(v.net))
        ps = v.padstack
        vl.append(frozenset(int(l) for l in ps.layers if int(l) in ids))
        try:
            fo, bo, dr = ps.front_outer_layers.proto, ps.back_outer_layers.proto, ps.proto.drill
            # Maske tenting'i `solder_mask_mode` (MASKED=kapali/tented, UNMASKED=acik, 0/3=kart kurali).
            # `covering_mode` IPC-4761 fab kapagi (copper cap), maske acikligiyla ilgisi yok.
            vc.append((int(fo.solder_mask_mode), int(bo.solder_mask_mode)))
            # tikali (plugged), dolu (filled) ya da kapakli (capped) via: delik gorunmez
            vh.append(int(fo.plugging_mode) == 1 or int(bo.plugging_mode) == 1
                      or int(dr.filled) == 1 or int(dr.capped) == 1)
        except Exception:
            vc.append((0, 0)); vh.append(False)
    return ViaData(np.array(vias, dtype=np.float64).reshape(-1, 4), np.array(vn, np.int32), vl,
                   np.array(vc, np.int8).reshape(-1, 2), np.array(vh, bool))


def fetch_pads(board, ids: set, nid, prev: "CopperData | None" = None, sigs: dict | None = None):
    """-> (PadRec listesi, footprint sira haritasi). sigs: pad KIID -> ham pad verisi hash'i (cagiran saklar). Verilirse ve onceki
    kayit varsa yalniz DEGISEN pad'lerin sekli KiCad'den istenir (3400 pad'lik kartta ~0.9 sn yerine birkac ms); digerleri onceki
    (zaten duzeltilmis) poligonlari kullanir."""
    global _stale_fixed
    import hashlib
    pads = board.get_pads()
    old = {q.kiid: q for q in prev.pads if q.kiid} if prev is not None else {}
    new_sigs = {p.id.value: hashlib.blake2b(p.proto.SerializeToString(), digest_size=8).digest() for p in pads}
    if sigs is not None and old:
        need = [i for i, p in enumerate(pads) if p.id.value not in old or sigs.get(p.id.value) != new_sigs[p.id.value]]
    else:
        need = list(range(len(pads)))
    if sigs is not None:
        sigs.clear()
        sigs.update(new_sigs)
    polys = {}
    shape_layers = (("front", F_CU), ("back", B_CU), ("inner", ids - {F_CU, B_CU} and min(ids - {F_CU, B_CU}) or F_CU))
    sub = [pads[i] for i in need]
    for key, L in shape_layers:
        got = [None] * len(sub)
        if sub:
            try:
                got = list(board.get_pad_shapes_as_polygons(sub, L))
            except Exception:
                pass
        polys[key] = dict(zip(need, got))
    _stale_fixed = 0
    fp_index = dict(prev.fp_index) if prev is not None else {}     # sira kalici: mesh etiketlerindeki sahip kodu degismesin
    out = []

    def margin(outer):
        try:
            s = outer.proto.solder_mask_settings
            return s.solder_mask_margin.value_nm * NM if s.HasField("solder_mask_margin") else None
        except Exception:
            return None

    for i, p in enumerate(pads):
        ps = p.padstack
        layers = frozenset(int(l) for l in ps.layers)
        dr = ps.drill.diameter
        px_, py_, pang = p.position.x * NM, p.position.y * NM, ps.angle.degrees
        fp_id = p.parent.value if hasattr(p.parent, "value") else str(p.parent)
        fp_index.setdefault(fp_id, len(fp_index))
        q = old.get(p.id.value)
        if i not in polys["front"] and q is not None:          # degismemis pad: onceki poligonlar aynen
            out.append(dataclasses.replace(q, net=nid(p.net)))
            continue
        shp = [_pw_outline(polys["front"].get(i)), _pw_outline(polys["back"].get(i)), _pw_outline(polys["inner"].get(i))]
        if q is not None and q.layers == layers:          # onceki kayitla karsilastir: bayat KiCad poligonlarini duzelt
            shp = [_reconcile(shp[0], q.front, q, px_, py_, pang), _reconcile(shp[1], q.back, q, px_, py_, pang),
                   _reconcile(shp[2], q.inner, q, px_, py_, pang)]
        # her durumda son kontrol: pad KONUMU KiCad'den hep taze gelir, bayat olan yalniz sekil. Sekil konumu kapsamiyorsa (onceki
        # kayit yok = ilk yukleme, ya da onceki kayit da bayat/yaris: tasima mesajindan once gelen kontrol) konuma tasinir.
        try:
            cl = ps.copper_layers[0]
            sz, off = (cl.size.x * NM, cl.size.y * NM), (cl.offset.x * NM, cl.offset.y * NM)
            shp = [_recenter(a, px_, py_, pang, sz, off) for a in shp]
        except Exception:  # noqa: BLE001
            pass
        out.append(PadRec(
            px_, py_, pang, layers,
            shp[0], shp[1], shp[2],
            dr.x * NM, dr.y * NM, int(p.pad_type) == 4, nid(p.net),
            margin(ps.front_outer_layers), margin(ps.back_outer_layers), p.id.value, fp_id,
        ))
    if _stale_fixed:
        try:
            from .log import _log
            _log(f"bayat pad poligonu duzeltildi: {_stale_fixed} poligon (KiCad eski konumu dondurdu)")
        except Exception:  # noqa: BLE001
            pass
    return out, fp_index


def fetch_zones(board, ids: set, nid) -> dict:
    zones: dict = {}
    for z in board.get_zones():
        if int(z.type) != 1 or not z.filled:           # ZT_COPPER
            continue
        zn = nid(z.net)
        for layer, polys_ in z.filled_polygons.items():
            L = int(layer)
            if L not in ids:
                continue
            for pw in polys_:
                out = _poly_pts(pw.outline)
                if len(out) < 3:
                    continue
                holes = [h for h in (_poly_pts(x) for x in pw.holes) if len(h) >= 3]
                zones.setdefault(L, []).append((out, holes, zn))
    return zones


def zones_equal(a, b) -> bool:
    if not a and not b:
        return True
    if not a or not b or len(a) != len(b):
        return False
    for (o1, h1, n1), (o2, h2, n2) in zip(a, b):
        if n1 != n2 or o1.shape != o2.shape or len(h1) != len(h2) or not np.array_equal(o1, o2):
            return False
        if any(x.shape != y.shape or not np.array_equal(x, y) for x, y in zip(h1, h2)):
            return False
    return True


def fetch_copper(board, copper_ids: list[int], prev: "CopperData | None" = None, pad_sigs: dict | None = None) -> CopperData:
    cd = CopperData()
    nid, names = make_nid(prev.net_names if prev is not None else None)
    ids = set(copper_ids)
    cd.tracks = fetch_tracks(board, ids, nid)
    cd.vias = fetch_vias(board, ids, nid)
    cd.pads, cd.fp_index = fetch_pads(board, ids, nid, prev, pad_sigs)
    cd.zones = fetch_zones(board, ids, nid)
    cd.net_names = names
    return cd


# -------------------------------------------------------------------------------- geometri
def _flip(a):
    a = np.array(a, dtype=np.float64, copy=True)
    if a.ndim == 2 and a.shape[1] >= 2:
        a[:, 1] *= -1
    return a


def hole_segs(diameter: float) -> int:
    """Delik cevresi cozunurlugu (ceyrek daire parcasi): yuvarlak gorunmesi icin bu fonksiyon HER YERDE ortak kullanilir
    (pad deligi, dielektrik deligi, varil, via halkasi) - farkli cozunurluk kose/aralik gosterir."""
    return 3 if diameter < 0.35 else 5 if diameter < 0.7 else 8


def _drill_shape(p_x, p_y, w, h, angle, sx=1.0):
    from shapely import affinity
    from shapely.geometry import LineString, Point
    r = min(w, h) / 2
    if abs(w - h) < 1e-6:
        return Point(p_x, -p_y).buffer(r, quad_segs=hole_segs(2 * r))
    if w > h:
        ln = LineString([(-(w / 2 - r), 0), (w / 2 - r, 0)])
    else:
        ln = LineString([(0, -(h / 2 - r)), (0, h / 2 - r)])
    g = ln.buffer(r, quad_segs=hole_segs(2 * r))
    g = affinity.rotate(g, angle, origin=(0, 0))        # sahne Y'si ters: aci isareti duzelir
    return affinity.translate(g, p_x, -p_y)


def _via_annulus(x, y, dia, drill, detail: int = 3):
    from shapely.geometry import Point
    outer = Point(x, -y).buffer(dia / 2, quad_segs=detail)
    if drill > 0:                                   # delik her katmanda acik: dielektrik de kesildigi icin icinden gorunur
        outer = outer.difference(Point(x, -y).buffer(drill / 2, quad_segs=hole_segs(drill)))
    return outer


def _simplify(g, tol=0.004):
    return g.simplify(tol, preserve_topology=True) if g is not None and not g.is_empty else g


def pad_polygon(p: PadRec, side: str):
    """Pad outline -> shapely (sahne koord.), delik dusulmus. side: top|bottom|inner."""
    from shapely.geometry import Polygon
    arr = {"top": p.front, "bottom": p.back, "inner": p.inner}[side]
    if arr is None or len(arr) < 3:
        return None
    g = Polygon(_flip(arr))
    if not g.is_valid:
        g = g.buffer(0)
    g = _simplify(g, 0.003)
    if p.drill_w > 0 and p.drill_h > 0:
        g = g.difference(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
    return g


def _scene_geom(g):
    from shapely import affinity
    return None if g is None else affinity.scale(g, 1, -1, origin=(0, 0))


def _polys(g):
    if g is None or g.is_empty:
        return []
    return [p for p in (g.geoms if g.geom_type in ("MultiPolygon", "GeometryCollection") else [g]) if p.geom_type == "Polygon"]


def _exposed_copper(cd: CopperData, lid: int, gfx_scene, cut_scene):
    """Mask acikliklarinda (cutout) acikta kalan bakir: grafik + zone + iz  ∩  cutout (sahne koord.)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    if cut_scene is None or cut_scene.is_empty:
        return None
    x0, y0, x1, y1 = cut_scene.bounds
    parts = []
    if gfx_scene is not None:
        parts.append(gfx_scene)
    for out, holes, net in cd.zones.get(lid, []):
        a = _flip(out)
        if a[:, 0].max() < x0 or a[:, 0].min() > x1 or a[:, 1].max() < y0 or a[:, 1].min() > y1:
            continue
        try:
            g = Polygon(a, [_flip(h) for h in holes])
            parts.append(g if g.is_valid else g.buffer(0))
        except Exception:
            pass
    segs = cd.tracks.get(lid)
    if segs is not None and len(segs):
        s = segs.copy()
        s[:, [1, 3]] *= -1
        w = s[:, 4] / 2
        keep = ((np.maximum(s[:, 0], s[:, 2]) + w >= x0) & (np.minimum(s[:, 0], s[:, 2]) - w <= x1)
                & (np.maximum(s[:, 1], s[:, 3]) + w >= y0) & (np.minimum(s[:, 1], s[:, 3]) - w <= y1))
        for r in s[keep]:
            parts.append(LineString([(r[0], r[1]), (r[2], r[3])]).buffer(r[4] / 2, quad_segs=2))
    if not parts:
        return None
    try:
        return unary_union(parts).intersection(cut_scene)
    except Exception:
        return None


def build_copper_layer(cd: CopperData, lid: int, z0: float, z1: float, side: str | None, sd=None, tent=None, outline=None,
                       mode: str = "all"):
    """Bir bakir katmaninin 3D mesh'leri: {'cu': zone/pad/via/grafik, 'tr': izler, 'finish': ... (yalniz dis katmanlar)}.
    mode="tracks": yalniz izler; mode="zones": yalniz zone dolgulari (zone degisiminde hizli yol). Ciktida "zn" = zone mesh'i.

    sd (SilkData): bakir katmanindaki grafikler (logo vb.) ve mask cutout'lari icin."""
    from shapely.geometry import Polygon
    from .prism import capsule_prisms, merge, polygon_prisms
    from .silk import layer_geometry

    from .geometry import board_clip

    bot = side == "bottom"                       # alt yuz: disaridan gorunen yuz z0 tarafi (kapaklar ona konur; yoksa dielektrikle z-fighting)
    pk = dict(top_cap=not bot, bottom_cap=bot)
    okey = _outline_key(outline)
    bc = _BOARD_CACHE.get(okey)
    if bc is None:
        bc = board_clip(outline)
        if len(_BOARD_CACHE) > 4:
            _BOARD_CACHE.clear()
        _BOARD_CACHE[okey] = bc
    board, outside = bc                          # kart poligonu ve DISARISI (cutout/yuva/kart disi): bakir buraya giremez

    hkey = _holes_key(cd)
    H = _HOLES_CACHE.get(hkey)
    if H is None:
        H = _Holes(cd)                            # delikler + uzamsal indeks (dev birlesim yerine yerel kirpma)
        if len(_HOLES_CACHE) > 4:
            _HOLES_CACHE.clear()
        _HOLES_CACHE[hkey] = H

    def clip(g, holes=True):
        """Kart disina tasan bakiri kart poligonuna kirp (cutout ile cakisan bakir kesilir); delik uzerini ac.
        holes=False: yalniz kart kirpmasi (pad/via halkasi kendi deligini zaten icermez, devasa birlesimle fark almak pahali)."""
        if g is None or g.is_empty:
            return g
        if outside is not None and g.intersects(outside):
            g = g.intersection(board)
        if holes and not g.is_empty:
            g = H.cut(g)
        return g

    gfx_scene = clip(_scene_geom(layer_geometry(sd, lid))) if sd is not None and mode == "all" else None
    parts, tparts = [], []
    if gfx_scene is not None:
        parts.append(polygon_prisms(_polys(gfx_scene), z0, z1, **pk))
    segs = cd.tracks.get(lid) if mode != "zones" else None
    if segs is not None and len(segs):
        s = segs.copy()
        s[:, [1, 3]] *= -1
        if True:
            hit = track_hits(cd, s, board, H)
            if hit.any():
                # Kirpilmasi gereken izler (via deligine giren uclar vb.) pahali (shapely); sonuc iz basina onbellekte:
                # bir iz duzenlemesinde yalniz yeni/degisen izler yeniden kirpilir (isci sureci boyunca gecerli).
                from shapely.geometry import LineString
                ctx = (okey, hkey, round(z0, 6), round(z1, 6), bot)
                if len(_CLIP_CACHE) > 300_000:
                    _CLIP_CACHE.clear()
                meshes = []
                for r in s[hit]:
                    k = (ctx, r.tobytes())
                    m = _CLIP_CACHE.get(k, _MISS)
                    if m is _MISS:
                        g = clip(LineString([(r[0], r[1]), (r[2], r[3])]).buffer(r[4] / 2, quad_segs=2))   # kart + delik kirpmasi
                        m = polygon_prisms([g], z0, z1, [int(r[5])], **pk) if g is not None and not g.is_empty else None
                        _CLIP_CACHE[k] = m
                    if m is not None:
                        meshes.append(m)
                if meshes:
                    tparts.append(merge(meshes))
                s = s[~hit]
        if len(s):
            tparts.append(capsule_prisms(s[:, :5], z0, z1, s[:, 5].astype(np.int32), bottom=bot))
    if mode == "tracks":
        return {"tr": merge(tparts)}
    zp, zt = [], []
    zparts = []
    for out, holes, net in cd.zones.get(lid, []):
        try:
            g = Polygon(_flip(out), [_flip(h) for h in holes])
            if not g.is_valid:
                g = g.buffer(0)
            g = clip(_simplify(g, 0.006))
            if g is not None and not g.is_empty:
                zp.append(g); zt.append(net)
        except Exception:
            pass
    if zp:
        zparts.append(polygon_prisms(zp, z0, z1, zt, **pk))      # ayri mesh: zone degisince yalniz bu yeniden uretilir
    if mode == "zones":
        return {"zn": merge(zparts)}

    outer = side in ("top", "bottom")
    mask_id = 42 if side == "top" else 41
    # Dis katmanda: lehim maskesi acikligi olan pad/via'lar 'finish' (yuzey kaplama); maskeyle KAPALI olanlar
    # (tented via, F.Mask'te olmayan pad) maskenin altindaki bakirdir. Ic katmanlarda hepsi bakir.
    ring_polys, ring_tags = [], []          # acik -> finish
    cu_polys, cu_tags = [], []              # kapali / ic katman -> bakir
    pad_parts(cd, cd.pads, lid, side, outer, mask_id, clip, ring_polys, ring_tags, cu_polys, cu_tags)
    # via halkalari burada degil: build_via_meshes (ayri mesh, numpy ile ~ms; via degisince yalniz o yeniden uretilir)
    if cu_polys:
        parts.append(polygon_prisms(cu_polys, z0, z1, cu_tags, **pk))
    out = {}
    if outer:
        zt_ = z1 + 0.004 if side == "top" else z1
        zb_ = z0 if side == "top" else z0 - 0.004
        if sd is not None:                     # mask cutout'larinda acikta kalan bakir da yuzey kaplamasi olur
            cut = _scene_geom(layer_geometry(sd, mask_id))
            exp = _exposed_copper(cd, lid, gfx_scene, cut)
            for p in _polys(exp):
                ring_polys.append(p); ring_tags.append(0)
        out["finish"] = polygon_prisms(ring_polys, zb_, zt_, ring_tags, **pk) if ring_polys else None
    out["cu"] = merge(parts)
    out["tr"] = merge(tparts)
    out["zn"] = merge(zparts)
    return out


OWNER_SHIFT = 16

# Isci sureci icinde kalici onbellekler (kismi yenilemelerde ayni hesap tekrarlanmasin)
_BOARD_CACHE: dict = {}
_HOLES_CACHE: dict = {}
_CLIP_CACHE: dict = {}
_MISS = object()


def _outline_key(outline) -> str:
    import hashlib
    return hashlib.blake2b(repr(outline).encode(), digest_size=12).hexdigest()


def _holes_key(cd: "CopperData") -> str:
    import hashlib
    h = hashlib.blake2b(digest_size=12)
    h.update(np.ascontiguousarray(cd.vias.xyd, dtype=np.float64).tobytes())
    arr = np.array([(p.x, p.y, p.drill_w, p.drill_h, p.angle) for p in cd.pads if p.drill_w > 0 and p.drill_h > 0], np.float64)
    h.update(arr.tobytes())
    return h.hexdigest()



def owner_tag(cd: "CopperData", p: "PadRec") -> int:
    """Vertex etiketi: dusuk 16 bit = ag, yuksek bitler = (footprint sirasi + 1). Canli tasimada o footprint'in ucgenleri ayiklanir."""
    return ((cd.fp_index.get(p.fp, -1) + 1) << OWNER_SHIFT) | (int(p.net) & 0xFFFF)


def pad_parts(cd, pads, lid, side, outer, mask_id, clip, ring_polys, ring_tags, cu_polys, cu_tags):
    """Pad halkalari: dis katmanda maske acikligi olanlar 'finish', digerleri bakir; her biri footprint sahip koduyla etiketlenir."""
    for p in pads:
        if lid not in p.layers or p.npth:
            continue
        g = clip(pad_polygon(p, side if outer else "inner"), holes=False)
        if g is None or g.is_empty:
            continue
        tag = owner_tag(cd, p)
        if outer and mask_id in p.layers:
            ring_polys.append(g); ring_tags.append(tag)
        else:
            cu_polys.append(g); cu_tags.append(tag)


def make_board_clip(outline):
    """Yalniz kart kirpmasi yapan clip(g, holes=False) (canli pad tasimada her seferinde yeniden hesaplanmasin diye onbellege alinir)."""
    from .geometry import board_clip
    board, outside = board_clip(outline)

    def clip(g, holes=False):
        if g is None or g.is_empty:
            return g
        if outside is not None and g.intersects(outside):
            g = g.intersection(board)
        return g
    return clip


def build_pad_dynamic(cd: "CopperData", pads, layers, zmap, clip):
    """Tasinan footprint'lerin pad'lerinin mesh'leri (kucuk, ana surecte ms'ler icinde). layers: [(lid, z0, z1, side|None)].
    -> {'cu:<lid>': mesh, 'finish:<side>': mesh, 'barrel': mesh}"""
    from .prism import merge, polygon_prisms
    out = {}
    for lid, z0, z1, side in layers:
        outer = side in ("top", "bottom")
        bot = side == "bottom"
        pk = dict(top_cap=not bot, bottom_cap=bot)
        mask_id = 42 if side == "top" else 41
        ring_polys, ring_tags, cu_polys, cu_tags = [], [], [], []
        pad_parts(cd, pads, lid, side, outer, mask_id, clip, ring_polys, ring_tags, cu_polys, cu_tags)
        if cu_polys:
            out[f"cu:{lid}"] = merge([polygon_prisms(cu_polys, z0, z1, cu_tags, **pk)])
        if outer and ring_polys:
            zt_ = z1 + 0.004 if side == "top" else z1
            zb_ = z0 if side == "top" else z0 - 0.004
            out[f"finish:{side}"] = polygon_prisms(ring_polys, zb_, zt_, ring_tags, **pk)
    sub = CopperData(pads=list(pads), vias=ViaData(), fp_index=cd.fp_index)
    out["barrel"] = build_barrels(sub, zmap)
    return out


class _Holes:
    """Tum delikler (pad + via drill) ve STRtree: sorgu basina yalniz yakin delikler birlestirilir."""

    def __init__(self, cd: CopperData):
        from shapely.geometry import Point
        from shapely.strtree import STRtree
        # Kirpma deligi 5 um genis: iz/zone'un kesik kenar duvari kaplama tupunun ICINDE (ayni yaricapta) kalirsa ayni yuzeyi
        # paylasip z-fighting yapar (delik kenarinda cizgilenme). Aradaki 5 um'yi zaten via/pad halkasi kapatir.
        hs = [_drill_shape(p.x, p.y, p.drill_w + 0.01, p.drill_h + 0.01, p.angle) for p in cd.pads if p.drill_w > 0 and p.drill_h > 0]
        hs += [Point(x, -y).buffer(dr / 2 + 0.005, quad_segs=hole_segs(dr)) for x, y, d, dr in cd.vias.xyd if dr > 0]
        self.hs = hs
        self.tree = STRtree(hs) if hs else None

    def cut(self, g):
        if self.tree is None:
            return g
        idx = self.tree.query(g, predicate="intersects")
        if len(idx) == 0:
            return g
        from shapely.ops import unary_union
        return g.difference(unary_union([self.hs[i] for i in idx]))


def track_hits(cd: CopperData, s: np.ndarray, board, H: "_Holes") -> np.ndarray:
    """Hangi izler kirpilmali: kart kenarina degen/disina tasan, ya da delige (pad/via) degen. (N,) bool.

    Tek buyuk birlesime karsi dwithin yerine STRtree (delikler + kart kenar parcalari): 36 bin iz ~0.1 sn."""
    import shapely
    from shapely.strtree import STRtree
    lines = shapely.linestrings(np.stack([s[:, 0:2], s[:, 2:4]], 1))
    w = s[:, 4] / 2
    hit = np.zeros(len(s), bool)
    if H.tree is not None:
        hit[H.tree.query(lines, predicate="dwithin", distance=w)[0]] = True
    if board is not None:
        edges = list(shapely.get_parts(shapely.get_parts(shapely.boundary(board))))
        if edges:
            hit[STRtree(edges).query(lines, predicate="dwithin", distance=w)[0]] = True
        hit |= ~shapely.contains_xy(board, s[:, 0], s[:, 1])          # izin baslangici kart disinda
    return hit


def _hole_union(cd: CopperData):
    """Tum delikler (pad + via drill) -> hazirlanmis birlesim. Bakir (grafik/zone) delik uzerini ortmemeli."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    import shapely
    hs = []
    for p in cd.pads:
        if p.drill_w > 0 and p.drill_h > 0:
            hs.append(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
    for x, y, d, dr in cd.vias.xyd:
        if dr > 0:
            hs.append(Point(x, -y).buffer(dr / 2, quad_segs=hole_segs(dr)))
    if not hs:
        return None
    u = unary_union(hs)
    shapely.prepare(u)
    return u


def _ring_mesh(cx, cy, R, r, n, z0, z1, net, bottom=False, cap=True, outer_wall=True, inner_wall=False):
    """Ayni kose sayili (n) halkalari tek seferde: kapak (R..r) + dis duvar (+ ic duvar). Vektorel, shapely yok.
    cx, cy, R, r, net: (M,) diziler, sahne koordinati. -> (P, N, T, G)"""
    M = len(cx)
    if M == 0:
        return None
    a = 2 * np.pi * np.arange(n) / n
    ca, sa = np.cos(a), np.sin(a)
    Ps, Ns, Ts, Gs, base = [], [], [], [], 0
    k = np.arange(n); k1 = (k + 1) % n
    if cap:
        zc = z0 if bottom else z1
        ox = cx[:, None] + R[:, None] * ca; oy = cy[:, None] + R[:, None] * sa
        ix = cx[:, None] + r[:, None] * ca; iy = cy[:, None] + r[:, None] * sa
        P = np.zeros((M, 2 * n, 3)); P[:, :n, 0] = ox; P[:, :n, 1] = oy; P[:, n:, 0] = ix; P[:, n:, 1] = iy; P[..., 2] = zc
        Nn = np.zeros((M, 2 * n, 3)); Nn[..., 2] = -1.0 if bottom else 1.0
        tri = np.concatenate([np.stack([k, k1, n + k1], 1), np.stack([k, n + k1, n + k], 1)])
        if bottom:
            tri = tri[:, ::-1]
        T = (tri[None] + (np.arange(M) * 2 * n)[:, None, None]).reshape(-1, 3) + base
        Ps.append(P.reshape(-1, 3)); Ns.append(Nn.reshape(-1, 3)); Ts.append(T); Gs.append(np.repeat(net, 2 * n)); base += M * 2 * n
    for rad, sign, on in ((R, 1.0, outer_wall), (r, -1.0, inner_wall)):
        if not on:
            continue
        wx = cx[:, None] + rad[:, None] * ca; wy = cy[:, None] + rad[:, None] * sa
        P = np.zeros((M, 2 * n, 3)); P[:, :n, 0] = wx; P[:, :n, 1] = wy; P[:, :n, 2] = z0
        P[:, n:, 0] = wx; P[:, n:, 1] = wy; P[:, n:, 2] = z1
        Nn = np.zeros((M, 2 * n, 3)); Nn[..., 0] = np.tile(ca, 2) * sign; Nn[..., 1] = np.tile(sa, 2) * sign
        tri = np.concatenate([np.stack([k, k1, n + k1], 1), np.stack([k, n + k1, n + k], 1)])
        if sign < 0:
            tri = tri[:, ::-1]
        T = (tri[None] + (np.arange(M) * 2 * n)[:, None, None]).reshape(-1, 3) + base
        Ps.append(P.reshape(-1, 3)); Ns.append(Nn.reshape(-1, 3)); Ts.append(T); Gs.append(np.repeat(net, 2 * n)); base += M * 2 * n
    return (np.concatenate(Ps).astype(np.float32), np.concatenate(Ns).astype(np.float32),
            np.concatenate(Ts).astype(np.uint32), np.concatenate(Gs).astype(np.int32))


def build_via_meshes(cd: CopperData, layers, zmap: dict, tent=None) -> dict:
    """Tum via'lar: her bakir katmaninda halka ('via:<L>' bakir; dis katmanda maske acik olanlar 'viaf:<side>' kaplama) ve
    tup ('viab'). Kose sayisi delik cozunurluguyle ayni (hole_segs) -> dielektrik deligi ve tup ile birebir oturur.
    layers: [(lid, z0, z1, side|None)]. Saf numpy: tum kart ~10-30 ms."""
    from .prism import merge
    v = cd.vias
    xyd = np.asarray(v.xyd, np.float64).reshape(-1, 4)
    out = {}
    if not len(xyd):
        return out
    nets = np.asarray(v.nets, np.int32)
    nseg = np.array([4 * hole_segs(dr) if dr > 0 else 12 for dr in xyd[:, 3]])
    cx, cy, R, r = xyd[:, 0], -xyd[:, 1], xyd[:, 2] / 2, np.maximum(xyd[:, 3] / 2, 0.0)
    ri = r                               # KiCad'deki delik capi bitmis (kaplamali) delik: gorunen aciklik = drill; kaplama duvari burada
    onl = {lid: np.array([lid in s for s in v.layers], bool) for lid, *_ in layers}
    for lid, z0, z1, side in layers:
        outer = side in ("top", "bottom")
        bot = side == "bottom"
        sel = onl[lid]
        if outer:
            op = np.array([via_mask_open(cd, i, side, tent) for i in range(len(xyd))], bool)
        else:
            op = np.zeros(len(xyd), bool)
        for key, mask, za, zb in ((f"via:{lid}", sel & ~op, z0, z1),
                                  (f"viaf:{side}", sel & op, z0 if side == "top" else z0 - 0.004, z1 + 0.004 if side == "top" else z1)):
            if not mask.any():
                continue
            parts = []
            for n in np.unique(nseg[mask]):
                m = mask & (nseg == n)
                parts.append(_ring_mesh(cx[m], cy[m], R[m], ri[m], int(n), za, zb, nets[m], bottom=bot))
            out[key] = merge([p for p in parts if p is not None])
    # tupler: ayni (acik/kapali, kose sayisi, z araligi) gruplar. Maskeyle kapali (tented) via'nin deligi bakir rengindedir:
    # yuzey kaplamasi (ENIG/HASL) yalniz acikta kalan bakira uygulanir; acik via'nin tupu kaplama renginde.
    opened = np.array([via_mask_open(cd, i, "top", tent) or via_mask_open(cd, i, "bottom", tent) for i in range(len(xyd))], bool)
    spans = {}
    for i, s in enumerate(v.layers):
        if xyd[i, 3] <= 0:
            continue
        zs = [zmap[l] for l in s if l in zmap]
        if not zs:
            continue
        spans.setdefault((bool(opened[i]), int(nseg[i]), round(min(z[0] for z in zs), 5), round(max(z[1] for z in zs), 5)), []).append(i)
    bparts, cparts = [], []
    for (op_, n, z0, z1), idx in spans.items():
        idx = np.array(idx)
        # kaplama tupu: tek silindir, delik yaricapinda (dielektrik deligi ile ayni); ust/alt kapagi via halkasi kapatir
        (bparts if op_ else cparts).append(_ring_mesh(cx[idx], cy[idx], ri[idx], ri[idx], n, z0, z1, nets[idx], cap=False,
                                                      outer_wall=True, inner_wall=False))
    if bparts:
        out["viab"] = merge([p for p in bparts if p is not None])
    if cparts:
        out["viabc"] = merge([p for p in cparts if p is not None])
    return out


def build_barrels(cd: CopperData, zmap: dict):
    """PTH pad tup (silindir) duvarlari: katman araligi boyunca, ici bos tup. (Via tupleri: build_via_meshes.)"""
    from shapely.geometry import Point
    from .prism import polygon_prisms
    rings, tags = [], []

    def add(x, y, drill_w, drill_h, angle, layers, net, round_):
        zs = [zmap[l] for l in layers if l in zmap]
        if not zs:
            return
        z0, z1 = min(z[0] for z in zs), max(z[1] for z in zs)
        r = max(drill_w, drill_h) / 2
        if round_:
            # Kaplama delik duvarina yaslanir ve IC tarafa kalinlasir: dis yaricap = delik (dielektrik duvariyla ayni),
            # ic yaricap = delik - kaplama. (Dis tarafa kalinlastirmak dielektrik duvariyla cakisip z-fighting yapiyordu.)
            sg = hole_segs(2 * r)
            plate = min(0.025, r * 0.4)
            inner = Point(x, -y).buffer(r, quad_segs=sg)
            g = Point(x, -y).buffer(r, quad_segs=sg).difference(inner)
        else:
            shape = _drill_shape(x, y, drill_w, drill_h, angle)
            plate = min(0.025, min(drill_w, drill_h) * 0.2)
            inner = shape
            g = shape.difference(inner)
        rings.append((g, inner, z0, z1, net))

    # via tupleri build_via_meshes'te (ayri mesh)
    for p in cd.pads:
        if p.drill_w > 0 and not p.npth:
            add(p.x, p.y, p.drill_w, p.drill_h, p.angle, p.layers, owner_tag(cd, p), abs(p.drill_w - p.drill_h) < 1e-6)
    parts = []
    # ayni z araligini paylasanlari tek cagrida topla
    groups: dict = {}
    for g, inner, z0, z1, net in rings:
        e = groups.setdefault((round(z0, 4), round(z1, 4)), ([], [], []))
        e[0].append(g); e[1].append(inner); e[2].append(net)
    for (z0, z1), (gs, ins, ns) in groups.items():
        # Kaplama: delik duvarinda TEK silindir, tam KiCad delik olcusunde (KiCad'deki delik capi bitmis delik capidir:
        # gorunen aciklik = drill). Dielektrik deliginin duvari cizilmedigi icin cakisma yok; pad halkasi tam delik kenarinda biter.
        parts.append(polygon_prisms(ins, z0, z1, ns, top_cap=False, bottom_cap=False))
    from .prism import merge
    return merge(parts)


def build_drills(cd: CopperData, z_top: float, z_bottom: float):
    """Koyu delik diskleri (ust/alt yuz)."""
    from .prism import merge, polygon_prisms
    holes = []
    for p in cd.pads:
        if p.drill_w > 0 and p.drill_h > 0:
            holes.append(_drill_shape(p.x, p.y, p.drill_w, p.drill_h, p.angle))
    v = cd.vias
    from shapely.geometry import Point
    for i, (x, y, d, dr) in enumerate(v.xyd):
        if dr > 0 and not (len(v.hide_drill) > i and v.hide_drill[i]):       # tikali/dolu via'nin deligi gorunmez
            holes.append(Point(x, -y).buffer(dr / 2, quad_segs=hole_segs(dr)))
    top = polygon_prisms(holes, z_top + 0.005, z_top + 0.005)
    bot = polygon_prisms(holes, z_bottom - 0.005, z_bottom - 0.005)
    # alt yuz: normal asagi bakmali
    bot = (bot[0], -bot[1], bot[2][:, ::-1], bot[3])
    return {"top": top, "bottom": bot}
