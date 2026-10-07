"""KiCad IPC (kipy) uzerinden kart verisini cek. Sahne birimleri: mm, Y yukari (KiCad Y'si negatiflenir)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

NM = 1e-6  # nm -> mm


@dataclass
class ModelRef:
    raw_path: str
    offset: tuple[float, float, float]      # mm
    rotation: tuple[float, float, float]    # derece
    scale: tuple[float, float, float]
    opacity: float = 1.0


@dataclass
class FootprintData:
    kiid: str
    reference: str
    x: float            # mm, KiCad koordinati (Y asagi)
    y: float
    angle: float        # derece
    bottom: bool
    models: list[ModelRef] = field(default_factory=list)


@dataclass
class BoardSnapshot:
    name: str
    project_dir: Path | None
    thickness: float                       # mm
    outline_lines: list[list[tuple[float, float]]]   # mm, KiCad koordinati; her biri polyline
    footprints: list[FootprintData]
    copper: object | None = None           # copper.CopperData
    stack: object | None = None            # stackup.Stackup
    silk: object | None = None             # silk.SilkData
    mask_expansion: float = 0.0            # mm (kart ayari pad_to_mask_clearance)
    embedded: dict = field(default_factory=dict)    # gomulu model adi -> dosya yolu (kicad-embed://)
    poses: dict = field(default_factory=dict)       # footprint kiid -> (x, y, aci, alt_yuz) VERININ cekildigi andaki konumlar
    data_path: str | None = None                    # tam bakir+silk verisinin dosyasi (isciler okur; ana surece hafif kopya gelir)


def _read_mask_rules(proj, name: str) -> tuple[float, bool, bool]:
    """IPC bu kart ayarlarini vermez: .kicad_pcb basligindan pad_to_mask_clearance ve (tenting (front..)(back..)) oku."""
    import re
    try:
        p = Path(proj) / name if proj else None
        if p and p.is_file():
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(600_000)
            m = re.search(r"\(pad_to_mask_clearance\s+(-?[0-9.]+)\)", head)
            t = re.search(r"\(tenting\s*\(front\s+(yes|no)\)\s*\(back\s+(yes|no)\)", head)
            return (float(m.group(1)) if m else 0.0,
                    (t.group(1) == "yes") if t else True, (t.group(2) == "yes") if t else True)
    except OSError:
        pass
    return 0.0, True, True


def _arc_points(s, m, e, n_per_rad=12):
    """3 nokta -> yay polyline (mm)."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [s, e]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (s, m, e))
    # s -> m -> e yonunu koruyan sweep
    def norm(a):
        while a < 0:
            a += 2 * math.pi
        return a % (2 * math.pi)
    ccw = norm(a2 - a1) < norm(a3 - a1)
    sweep = norm(a3 - a1) if ccw else -norm(a1 - a3)
    n = max(4, int(abs(sweep) * n_per_rad))
    return [(ux + r * math.cos(a1 + sweep * i / n), uy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]


def _v(p):
    return (p.x * NM, p.y * NM)


def _outline_from_shapes(shapes, edge_layer) -> list[list[tuple[float, float]]]:
    lines: list[list[tuple[float, float]]] = []
    for s in shapes:
        if s.layer != edge_layer:
            continue
        t = type(s).__name__
        if t == "BoardSegment":
            lines.append([_v(s.start), _v(s.end)])
        elif t == "BoardArc":
            lines.append(_arc_points(_v(s.start), _v(s.mid), _v(s.end)))
        elif t == "BoardCircle":
            c = _v(s.center)
            r = math.hypot(s.radius_point.x * NM - c[0], s.radius_point.y * NM - c[1]) if hasattr(s, "radius_point") else 0
            n = 64
            lines.append([(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)])
        elif t == "BoardRectangle":
            a, b = _v(s.top_left), _v(s.bottom_right)
            lines.append([(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1]), (a[0], a[1])])
        elif t == "BoardPolygon":
            for pwh in s.polygons:
                pts = [(n.point.x * NM, n.point.y * NM) for n in pwh.outline.nodes if n.has_point]
                if pts:
                    lines.append(pts + [pts[0]])
                for h in pwh.holes:
                    pts = [(n.point.x * NM, n.point.y * NM) for n in h.nodes if n.has_point]
                    if pts:
                        lines.append(pts + [pts[0]])
    return lines


def _footprint_data(f) -> FootprintData:
    from kipy.board_types import BoardLayer
    models = []
    for m in f.definition.models:
        if not m.visible:
            continue
        models.append(ModelRef(
            m.filename,
            (m.offset.x, m.offset.y, m.offset.z),
            (m.rotation.x, m.rotation.y, m.rotation.z),
            (m.scale.x, m.scale.y, m.scale.z),
            getattr(m, "opacity", 1.0),
        ))
    return FootprintData(
        kiid=f.id.value,
        reference=f.reference_field.text.value,
        x=f.position.x * NM, y=f.position.y * NM,
        angle=f.orientation.degrees,
        bottom=f.layer == BoardLayer.BL_B_Cu,
        models=models,
    )


def _mask_cut_box(sd):
    """Maske katmanlarindaki (F/B.Mask) grafik/yazi cutout'larinin kapsayici kutusu (KiCad koord.) ya da None."""
    if sd is None:
        return None
    xs, ys = [], []
    for lay in (41, 42):
        for it in sd.extra_shapes.get(lay, []) or []:
            kind = it[0]
            if kind == "seg":
                xs += [it[1], it[3]]; ys += [it[2], it[4]]
            elif kind == "poly":
                arr = np.asarray(it[1]); xs += [arr[:, 0].min(), arr[:, 0].max()]; ys += [arr[:, 1].min(), arr[:, 1].max()]
            elif kind == "circle":
                xs += [it[1] - it[3], it[1] + it[3]]; ys += [it[2] - it[3], it[2] + it[3]]
            elif kind == "arc":
                for p in it[1:4]:
                    xs.append(p[0]); ys.append(p[1])
        for t in sd.extra_texts.get(lay, []) or []:
            r = max(t.get("sx", 1.0), t.get("sy", 1.0)) * (len(str(t.get("value", ""))) + 2)
            xs += [t["x"] - r, t["x"] + r]; ys += [t["y"] - r, t["y"] + r]
    if not xs:
        return None
    return (min(xs) - 1.0, min(ys) - 1.0, max(xs) + 1.0, max(ys) + 1.0)


def _tracks_touch(old, new, box) -> bool:
    """Eklenen/silinen iz parcalarindan biri kutuya degiyor mu?"""
    o = {tuple(np.round(r, 6)) for r in (old if old is not None else np.zeros((0, 6)))}
    n = {tuple(np.round(r, 6)) for r in (new if new is not None else np.zeros((0, 6)))}
    x0, y0, x1, y1 = box
    for r in o ^ n:
        w = r[4] / 2
        if max(r[0], r[2]) + w >= x0 and min(r[0], r[2]) - w <= x1 and max(r[1], r[3]) + w >= y0 and min(r[1], r[3]) - w <= y1:
            return True
    return False


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None or (a is not None and len(a) == 0) or (b is not None and len(b) == 0)
    return a.shape == b.shape and bool(np.array_equal(a, b))


def board_thickness(board) -> float:
    try:
        st = board.get_stackup()
        total = sum(l.thickness for l in st.layers if l.type in (1, 2)) * NM  # bakir + dielektrik
        if 0.2 < total < 10:
            return total
    except Exception:
        pass
    return 1.6


class KiCadSource:
    def __init__(self, timeout_ms: int = 60000):
        from kipy import KiCad
        self.kicad = KiCad(timeout_ms=timeout_ms)
        self.board = self.kicad.get_board()
        self._fp_silk: dict = {}                # footprint kiid -> hafif silk ozeti (ham footprint nesneleri cok RAM tutar)
        self._silk_extra: set = set()
        self._fp_hash: dict = {}                # footprint kiid -> ham protobuf hash'i (silk ozeti hangi footprint'te bayat?)
        self._poses: dict = {}                  # footprint kiid -> (x, y, aci, alt_yuz): son bilinen konumlar (canli tasima)

    def refresh_board(self):
        self.board = self.kicad.get_board()

    def _silk(self, board, raw_fps, extra, fp_hash):
        from .silk import fetch_silk
        self._silk_extra = set(extra)
        self._fp_silk = {}
        self._fp_hash = fp_hash
        return fetch_silk(board, raw_fps, extra, cache=self._fp_silk)

    def snapshot(self, with_copper: bool = True) -> BoardSnapshot:
        from kipy.board_types import BoardLayer
        from .copper import fetch_copper
        from .silk import fetch_silk
        from .stackup import fetch_stackup
        b = self.board
        shapes = b.get_shapes()
        proj = None
        try:
            proj = Path(b.document.project.path)
        except Exception:
            pass
        fp_hash = self._fp_hashes()            # footprint'lerden ONCE: arada degisen footprint sonraki kontrolde yakalanir
        raw_fps = b.get_footprints()
        fps = [_footprint_data(f) for f in raw_fps]
        self._poses = {f.kiid: (f.x, f.y, f.angle, f.bottom) for f in fps}
        stack = fetch_stackup(b)
        mask_exp, tent_f, tent_b = _read_mask_rules(proj, b.name)
        embedded = {}
        from .embedded import extract_embedded, needed_names
        need = needed_names(m.raw_path for fp in fps for m in fp.models)
        if need:                               # gomulu modeller: kart metnini KiCad'den (bellekten) al
            try:
                embedded = extract_embedded(b.get_as_string(), need)
            except Exception as e:  # noqa: BLE001
                print("gomulu model okunamadi:", e)
        cd = fetch_copper(b, [l.layer_id for l in stack.copper()]) if with_copper else None
        if cd is not None:
            cd.tent_rules = (tent_f, tent_b)
        return BoardSnapshot(
            name=b.name,
            project_dir=proj,
            thickness=stack.thickness,
            outline_lines=_outline_from_shapes(shapes, BoardLayer.BL_Edge_Cuts),
            footprints=fps,
            copper=cd,
            stack=stack,
            silk=self._silk(b, raw_fps, [l.layer_id for l in stack.copper()] + [41, 42], fp_hash) if with_copper else None,
            mask_expansion=mask_exp,
            embedded=embedded,
            poses=dict(self._poses),
        )

    # --- canli degisim tespiti ---------------------------------------------
    def _raw_items(self, types):
        from kipy.proto.common.commands.editor_commands_pb2 import GetItems, GetItemsResponse
        cmd = GetItems()
        cmd.header.document.CopyFrom(self.board._doc)
        cmd.types.extend(types)
        return self.board._kicad.send(cmd, GetItemsResponse)

    def _raw_hash(self, types) -> str:
        """Ogeleri protobuf olarak al ve baytlarini hash'le: python nesnesine cevirmeden (cok hizli) degisim tespiti."""
        import hashlib
        return hashlib.blake2b(self._raw_items(types).SerializeToString(), digest_size=8).hexdigest()

    def pads_raw_hash(self) -> str:
        from kipy.proto.common.types import KiCadObjectType as K
        return self._raw_hash([K.KOT_PCB_PAD])

    def geom_signature(self, fresh_fp: bool = False) -> tuple:
        """Bakir/maske/silk geometrisini etkileyen her seyin hash'i: iz, via, zone, pad, sekil, yazi (~150 ms, buyuk kart)."""
        from kipy.proto.common.types import KiCadObjectType as K
        self._fp_resp = None
        groups = ([K.KOT_PCB_TRACE, K.KOT_PCB_ARC], [K.KOT_PCB_VIA], [K.KOT_PCB_ZONE], [K.KOT_PCB_PAD],
                  [K.KOT_PCB_SHAPE], [K.KOT_PCB_TEXT, K.KOT_PCB_TEXTBOX])
        # 7: footprint'ler (alanlar/yazilar ve footprint ici silk sekilleri dahil). Ust duzey KOT_PCB_SHAPE/TEXT footprint
        # cocuklarini KAPSAMAZ: referans yazisini tasimak/degistirmek ya da footprint'i tasimak yalniz burada gorunur.
        return tuple(self._raw_hash(g) for g in groups) + (self._stackup_hash(), self._fp_raw_hash(fresh_fp))

    _fp_sig = None
    _fp_resp = None                              # son kontrolde cekilen ham footprint yaniti (yalniz o kontrolun yenilemesi icin)
    _fp_sig_t = 0.0
    _fp_hot_until = 0.0                          # bu ana dek footprint'ler her kontrolde cekilir (duzenleme sonrasi)
    _fp_sig_cost = 0.0

    def _fp_raw_hash(self, fresh: bool = False) -> str:
        """Footprint hash'i, maliyetiyle orantili aralikla (en az 20x maliyeti). Buyuk kartta tum footprint'leri cekmek KiCad'in
        UI thread'ini ~0.8 sn kilitler (57 MB); her 1.5 sn'de yapilinca hem KiCad hem 3D (pencere mesajlari) takiliyordu.
        Arada son deger kullanilir. fresh: KiCad'de bir duzenleme/tasima az once bitti -> hemen cek ve 5 sn boyunca her kontrolde
        cek: KiCad tasimadan hemen sonra bazen ESKI konumu dondurur, bir sonraki kontrol duzeltir (seyrek aralik beklenmez)."""
        import time
        from kipy.proto.common.types import KiCadObjectType as K
        now = time.monotonic()
        if fresh:
            self._fp_hot_until = now + 5.0
        if now < self._fp_hot_until or self._fp_sig is None or now - self._fp_sig_t > max(1.5, 20 * self._fp_sig_cost):
            import hashlib
            t0 = time.perf_counter()
            resp = self._raw_items([K.KOT_PCB_FOOTPRINT])
            self._fp_resp = resp                 # ayni kontroldeki refresh_partial tekrar cekmesin (buyuk kartta ~0.8 sn)
            self._fp_sig = hashlib.blake2b(resp.SerializeToString(), digest_size=8).hexdigest()
            self._fp_sig_cost = time.perf_counter() - t0
            self._fp_sig_t = time.monotonic()
        return self._fp_sig

    def _stackup_hash(self) -> str:
        """Kart stackup'i (kalinliklar, yuzey kaplama turu, renkler) ham hash'i: Board Setup degisince yakalanir."""
        import hashlib
        from kipy.proto.board import board_commands_pb2
        cmd = board_commands_pb2.GetBoardStackup()
        cmd.board.CopyFrom(self.board._doc)
        resp = self.board._kicad.send(cmd, board_commands_pb2.BoardStackupResponse)
        return hashlib.blake2b(resp.SerializeToString(), digest_size=8).hexdigest()

    def refresh_tracks(self, prev: BoardSnapshot):
        """Yalniz izler degisti: izleri yeniden cek, katman katman karsilastir. -> (yeni snapshot, degisen bakir katman idleri)."""
        import dataclasses
        from .copper import fetch_tracks
        cd = prev.copper
        netid = {n: i for i, n in enumerate(cd.net_names)}
        names = list(cd.net_names)

        def nid(net) -> int:
            name = net.name if net is not None else ""
            v = netid.get(name)
            if v is None:
                v = netid[name] = len(names)
                names.append(name)
            return v
        ids = {l.layer_id for l in prev.stack.copper()}
        new = fetch_tracks(self.board, ids, nid)
        changed = [L for L in ids if not _same(cd.tracks.get(L), new.get(L))]
        cd2 = dataclasses.replace(cd, tracks=new, net_names=names)
        return dataclasses.replace(prev, copper=cd2), changed

    def refresh_geometry(self, prev: BoardSnapshot) -> BoardSnapshot:
        """Yalniz geometri (kontur, bakir, silk) yeniden cekilir; footprint/model/stackup oncekinden kalir."""
        import dataclasses
        from .copper import fetch_copper
        from .silk import fetch_silk
        b = self.board
        poses = dict(self._poses)                # bu verinin konum zamani (canli tasima icin pad taban konumu)
        ids = [l.layer_id for l in prev.stack.copper()]
        cd = fetch_copper(b, ids, prev=prev.copper)
        if prev.copper is not None:
            cd.tent_rules = prev.copper.tent_rules
        sd = fetch_silk(b, [], ids + [41, 42], cache=self._fp_silk)
        from kipy.board_types import BoardLayer
        return dataclasses.replace(prev, copper=cd, silk=sd, outline_lines=_outline_from_shapes(b.get_shapes(), BoardLayer.BL_Edge_Cuts), poses=poses)

    def refresh_partial(self, prev: BoardSnapshot, diff: list):
        """Yalniz DEGISEN kategoriyi cek (diff: geom_signature indeksleri 0 iz, 1 via, 2 zone, 3 pad, 4 sekil, 5 yazi) ve hangi
        katmanlarin yeniden uretilecegini soyle. -> (snapshot, plan). plan: cu (tam katman), tracks (yalniz iz), body (dielektrik +
        maske), barrel, silk, pads (pad taban konumu yenilendi), full (kart konturu degisti)."""
        import dataclasses
        from kipy.board_types import BoardLayer
        from .copper import fetch_pads, fetch_tracks, fetch_vias, fetch_zones, make_nid, zones_equal
        b = self.board
        stack_ids = [l.layer_id for l in prev.stack.copper()]
        ids = set(stack_ids)
        cd = prev.copper
        nid, names = make_nid(cd.net_names)
        plan = {"cu": set(), "tracks": set(), "zones": set(), "body": False, "body_tiles": set(), "vias": False,
                "barrel": False, "silk": False, "pads": False, "full": False}
        from .body import _pad_circle, tiles_for
        from .geometry import outline_to_polygon
        bk = getattr(self, "_bounds_key", None)
        if bk is None or bk[0] is not prev.outline_lines:
            poly = outline_to_polygon(prev.outline_lines)
            self._bounds_key = (prev.outline_lines, poly.bounds if poly is not None else (0, 0, 1, 1))
        bounds = self._bounds_key[1]
        new: dict = {}
        poses = prev.poses
        if 0 in diff:
            tr = fetch_tracks(b, ids, nid)
            new["tracks"] = tr
            plan["tracks"] |= {L for L in ids if not _same(cd.tracks.get(L), tr.get(L))}
            s = prev.silk                            # maske cutout'u altindaki iz acikta kalan bakirdir (kaplama): yalniz cutout'a
            cut_box = _mask_cut_box(s)                   # degen iz degisiminde tam katman gerekir; digerleri yalniz iz mesh'i
            if cut_box is not None:
                for L in plan["tracks"] & {3, 34}:
                    if _tracks_touch(cd.tracks.get(L), tr.get(L), cut_box):
                        plan["cu"].add(L)
        if 1 in diff:
            nv = fetch_vias(b, ids, nid)
            new["vias"] = nv
            plan["vias"] = True                                  # via mesh'leri (numpy, ~0.15 sn) + dokunulan govde/maske karolari
            o = {tuple(np.round(r, 6)) for r in np.asarray(cd.vias.xyd).reshape(-1, 4)}
            n = {tuple(np.round(r, 6)) for r in np.asarray(nv.xyd).reshape(-1, 4)}
            pts = [(x, -y, d / 2 + 0.6) for x, y, d, dr in (o ^ n)]
            if len(nv.xyd) == len(cd.vias.xyd) and not pts:     # yalniz ozellik (maske/kaplama) degisti: tum karolar
                plan["body"] = True
            plan["body_tiles"] |= tiles_for(bounds, pts)
        if 3 in diff:
            poses = dict(self._poses)
            new["pads"], new["fp_index"] = fetch_pads(b, ids, nid, cd)
            plan["cu"] |= ids
            plan["barrel"] = plan["pads"] = True
            old = {p.kiid: p for p in cd.pads}
            pts = []
            for p in new["pads"]:                                 # degisen pad'lerin eski ve yeni yerleri -> govde/maske karolari
                q = old.pop(p.kiid, None)
                if q is None or (q.x, q.y, q.angle, q.layers, q.drill_w, q.drill_h) != (p.x, p.y, p.angle, p.layers, p.drill_w, p.drill_h) \
                        or (p.front is None) != (q.front is None) or (p.front is not None and (p.front.shape != q.front.shape or not np.allclose(p.front, q.front))):
                    pts.append(_pad_circle(p))
                    if q is not None:
                        pts.append(_pad_circle(q))
            pts += [_pad_circle(q) for q in old.values()]            # silinen pad'ler
            plan["body_tiles"] |= tiles_for(bounds, pts)
        if 2 in diff:
            z = fetch_zones(b, ids, nid)
            new["zones"] = z
            plan["zones"] |= {L for L in ids if not zones_equal(cd.zones.get(L), z.get(L))}
            s = prev.silk                            # maske cutout'u (logo) altindaki zone acikta kalan bakir = kaplama: tam katman gerekir
            if s is not None and any(s.extra_shapes.get(m) or s.extra_texts.get(m) for m in (41, 42)):
                plan["cu"] |= plan["zones"] & {3, 34}
        stack = prev.stack
        if 6 in diff:                                    # Board Setup: stackup / yuzey kaplama turu degisti
            from .stackup import fetch_stackup
            stack = fetch_stackup(b)
            zs = lambda s: [(l.key, round(l.z0, 6), round(l.z1, 6)) for l in s.layers]
            if zs(stack) != zs(prev.stack):
                plan["refull"] = True                    # kalinlik / katman degisti: modeller dahil tam yukleme
            else:
                plan["stack"] = True                     # yalniz kaplama turu / renk: yeniden uretim yok, renk aninda
        sd, outline = prev.silk, prev.outline_lines
        fp_silk = 7 in diff and self._refresh_fp_silk()
        if 4 in diff or 5 in diff or fp_silk:
            from .silk import fetch_silk
            sd = fetch_silk(b, [], stack_ids + [41, 42], cache=self._fp_silk)
            outline = _outline_from_shapes(b.get_shapes(), BoardLayer.BL_Edge_Cuts)
            plan["full"] = outline != prev.outline_lines
            plan["silk"] = True
            lay = set()
            for s in (sd, prev.silk):                 # bakir / maske katmanlarinda grafik (logo, cutout) olan katmanlar
                if s is not None:
                    lay |= {L for L, v in s.extra_shapes.items() if v} | {L for L, v in s.extra_texts.items() if v}
            plan["cu"] |= lay & ids
            if lay & {41, 42}:
                plan["body"] = True
        cd2 = dataclasses.replace(cd, net_names=names, **new)
        return dataclasses.replace(prev, copper=cd2, silk=sd, outline_lines=outline, poses=poses, stack=stack), plan

    def _raw_footprints(self, resp=None):
        """-> [(kiid, hash, protobuf)] Python nesnesine cevirmeden (hash ham baytlardan). resp: onceden cekilmis yanit."""
        import hashlib
        from kipy.proto.board.board_types_pb2 import FootprintInstance as FpProto
        from kipy.proto.common.types import KiCadObjectType as K
        out = []
        if resp is None:
            resp = self._raw_items([K.KOT_PCB_FOOTPRINT])
        for it in resp.items:
            p = FpProto()
            if it.Unpack(p):
                out.append((p.id.value, hashlib.blake2b(it.value, digest_size=8).hexdigest(), p))
        return out

    def _fp_hashes(self) -> dict:
        try:
            return {k: h for k, h, _ in self._raw_footprints()}
        except Exception:  # noqa: BLE001
            return {}

    def _refresh_fp_silk(self) -> bool:
        """Degisen footprint'lerin silk/bakir/maske ozetini yenile (yalniz onlar Python nesnesine cevrilir). -> degisen var mi."""
        from kipy.board_types import FootprintInstance
        from .silk import fp_silk_part
        seen, changed = set(), False
        resp, self._fp_resp = self._fp_resp, None    # geometri kontrolunun az once cektigi yanit (varsa)
        for k, h, p in self._raw_footprints(resp):
            seen.add(k)
            if self._fp_hash.get(k) == h and k in self._fp_silk:
                continue
            self._fp_hash[k] = h
            self._fp_silk[k] = fp_silk_part(FootprintInstance(proto=p), self._silk_extra)
            changed = True
        for k in set(self._fp_silk) - seen:              # silinen footprint'ler
            self._fp_silk.pop(k, None)
            self._fp_hash.pop(k, None)
            changed = True
        return changed

    def pad_signature(self) -> dict[str, int]:
        """footprint KIID -> pad konum hash'i. ~45 ms, tum kart icin."""
        sig: dict[str, int] = {}
        for p in self.board.get_pads():
            k = p.parent.value if hasattr(p.parent, "value") else str(p.parent)
            sig[k] = sig.get(k, 0) ^ hash((p.position.x, p.position.y, p.id.value))
        return sig

    def footprints_by_id(self, ids: list[str]) -> list[FootprintData]:
        from kipy.proto.common.types import KIID
        out = []
        for i in range(0, len(ids), 50):
            kids = []
            for s in ids[i:i + 50]:
                k = KIID(); k.value = s
                kids.append(k)
            for f in self.board.get_items_by_id(kids):
                from .silk import fp_silk_part
                self._fp_silk[f.id.value] = fp_silk_part(f, self._silk_extra)
                self._fp_hash.pop(f.id.value, None)      # silk mesh'i henuz eski konumda: geometri kontrolu yeniden uretsin
                fd = _footprint_data(f)
                self._poses[fd.kiid] = (fd.x, fd.y, fd.angle, fd.bottom)
                out.append(fd)
        return out
