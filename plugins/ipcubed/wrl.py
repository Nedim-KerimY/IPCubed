"""VRML 2.0 (.wrl / .wrz) -> MeshData. KiCad modelleri: Transform/Group/Shape + IndexedFaceSet, DEF/USE, Material.

Birim: VRML'de 1 birim = 0.1 inc (KiCad kurali) -> mm icin 2.54 ile carpilir. Eksenler STEP ile ayni (KiCad ayni donusumu uygular).
Desteklenen: Transform (translation/rotation/scale/center/scaleOrientation), Group/Collision/Anchor/Billboard/Switch/LOD,
Shape(appearance.material: diffuse/emissive/transparency), IndexedFaceSet(coord, coordIndex, ccw, creaseAngle, color/colorIndex), Box.
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np

from .model_loader import MeshData

UNIT_MM = 2.54
_TOKEN = re.compile(r'#[^\n]*|"(?:[^"\\]|\\.)*"|[\[\]{}]|[^\s\[\]{},"#]+')
_NUM = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")


class _Node:
    __slots__ = ("type", "f", "_geo")

    def __init__(self, type_, f):
        self.type, self.f, self._geo = type_, f, None


class _Parser:
    def __init__(self, text: str):
        self.t = [m for m in _TOKEN.findall(text) if not m.startswith("#")]
        self.i = 0
        self.defs: dict[str, _Node] = {}

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        v = self.t[self.i]
        self.i += 1
        return v

    def parse_root(self) -> list:
        out = []
        while self.peek() is not None:
            t = self.peek()
            if t in ("PROTO", "EXTERNPROTO"):
                self._skip_proto()
                continue
            if t == "ROUTE":
                self.i += 4
                continue
            n = self.node()
            if n is not None:
                out.append(n)
        return out

    def _skip_proto(self):
        self.next()
        self.next()
        depth = 0
        while self.peek() is not None:
            t = self.next()
            if t in ("[", "{"):
                depth += 1
            elif t in ("]", "}"):
                depth -= 1
                if depth == 0 and t == "}":
                    break

    def node(self):
        t = self.next()
        if t == "DEF":
            name = self.next()
            n = self.node()
            self.defs[name] = n
            return n
        if t == "USE":
            return self.defs.get(self.next())
        if t == "NULL":
            return None
        if self.peek() != "{":
            return None
        self.next()
        fields = {}
        while self.peek() not in ("}", None):
            name = self.next()
            if name == "ROUTE":
                self.i += 3
                continue
            fields[name] = self.value()
        if self.peek() == "}":
            self.next()
        return _Node(t, fields)

    def value(self):
        if self.peek() == "[":
            self.next()
            vals: list = []
            while self.peek() not in ("]", None):
                p = self.peek()
                if _NUM.match(p):
                    vals.append(float(self.next()))
                elif p.startswith('"'):
                    vals.append(self.next()[1:-1])
                elif p in ("TRUE", "FALSE"):
                    vals.append(self.next() == "TRUE")
                else:
                    vals.append(self.node())
            if self.peek() == "]":
                self.next()
            return vals
        p = self.peek()
        if p is None:
            return None
        if _NUM.match(p):
            nums = []
            while self.peek() is not None and _NUM.match(self.peek()):
                nums.append(float(self.next()))
            return nums
        if p.startswith('"'):
            return self.next()[1:-1]
        if p in ("TRUE", "FALSE"):
            return self.next() == "TRUE"
        return self.node()


# ------------------------------------------------------------------ matrisler
def _rot(axis_angle) -> np.ndarray:
    x, y, z, a = (list(axis_angle) + [0, 0, 1, 0])[:4]
    n = (x * x + y * y + z * z) ** 0.5
    m = np.eye(4)
    if n == 0 or a == 0:
        return m
    x, y, z = x / n, y / n, z / n
    c, s = np.cos(a), np.sin(a)
    t = 1 - c
    m[:3, :3] = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                 [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                 [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    return m


def _trans(v) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (list(v) + [0, 0, 0])[:3]
    return m


def _scale(v) -> np.ndarray:
    m = np.eye(4)
    s = (list(v) + [1, 1, 1])[:3]
    m[0, 0], m[1, 1], m[2, 2] = s
    return m


def _transform_matrix(f: dict) -> np.ndarray:
    t = f.get("translation", [0, 0, 0])
    r = f.get("rotation", [0, 0, 1, 0])
    s = f.get("scale", [1, 1, 1])
    so = f.get("scaleOrientation", [0, 0, 1, 0])
    c = f.get("center", [0, 0, 0])
    # T * C * R * SR * S * SR^-1 * C^-1
    sr = _rot(so)
    return _trans(t) @ _trans(c) @ _rot(r) @ sr @ _scale(s) @ np.linalg.inv(sr) @ _trans(-np.array((list(c) + [0, 0, 0])[:3]))


# ------------------------------------------------------------------ geometri
def _material(app: _Node | None):
    """-> (r, g, b, a) 0..1"""
    diffuse, emissive, transp = (0.8, 0.8, 0.8), (0.0, 0.0, 0.0), 0.0
    if app is not None and app.type == "Appearance":
        m = app.f.get("material")
        if isinstance(m, _Node) and m.type == "Material":
            diffuse = tuple((list(m.f.get("diffuseColor", diffuse)) + [0, 0, 0])[:3])
            emissive = tuple((list(m.f.get("emissiveColor", emissive)) + [0, 0, 0])[:3])
            tr = m.f.get("transparency", [0.0])
            transp = float(tr[0] if isinstance(tr, list) and tr else tr or 0.0)
    rgb = np.clip(np.array(diffuse) + np.array(emissive), 0, 1)
    return (*rgb.tolist(), float(np.clip(1.0 - transp, 0.0, 1.0)))


def _faces(coord_index: list[float]) -> list[list[int]]:
    faces, cur = [], []
    for v in coord_index:
        if v < 0:
            if len(cur) >= 3:
                faces.append(cur)
            cur = []
        else:
            cur.append(int(v))
    if len(cur) >= 3:
        faces.append(cur)
    return faces


def _triangulate(faces, pts: np.ndarray):
    """-> (T,3) tepe indeksleri + her ucgenin kaynak yuzu"""
    tris, owner = [], []
    for fi, f in enumerate(faces):
        n = len(f)
        if n == 3:
            tris.append(f)
            owner.append(fi)
        elif n == 4:
            tris.append([f[0], f[1], f[2]])
            tris.append([f[0], f[2], f[3]])
            owner += [fi, fi]
        else:
            tri = _earcut_face(f, pts)
            tris.extend(tri)
            owner += [fi] * len(tri)
    return np.array(tris, np.int64).reshape(-1, 3), np.array(owner, np.int64)


def _earcut_face(f, pts):
    p = pts[f]
    nrm = np.cross(p[1] - p[0], p[2] - p[1])
    for k in range(1, len(f) - 1):                      # ilk dejenere olmayan kose cifti
        nrm = np.cross(p[k] - p[0], p[k + 1] - p[k])
        if np.linalg.norm(nrm) > 1e-12:
            break
    if np.linalg.norm(nrm) < 1e-12:
        return [[f[0], f[k], f[k + 1]] for k in range(1, len(f) - 1)]
    a = np.argmax(np.abs(nrm))                           # baskin eksene dik duzleme izdusum
    q = np.delete(p, a, axis=1)
    try:
        import mapbox_earcut as ec
        idx = ec.triangulate_float64(q.astype(np.float64), np.array([len(q)], np.uint32))
        tri = [[f[int(idx[i])], f[int(idx[i + 1])], f[int(idx[i + 2])]] for i in range(0, len(idx), 3)]
        # earcut sargisi izdusuma bagli: gercek duzlem normaline gore yonu duzelt
        out = []
        for t in tri:
            n2 = np.cross(pts[t[1]] - pts[t[0]], pts[t[2]] - pts[t[0]])
            out.append(t if float(n2 @ nrm) >= 0 else [t[0], t[2], t[1]])
        return out
    except Exception:
        return [[f[0], f[k], f[k + 1]] for k in range(1, len(f) - 1)]


def _ifs(node: _Node):
    """IndexedFaceSet -> (points (V,3), tris (T,3), vcolor (V,3)|None, ccw, crease) yerel koordinatlarda."""
    if node._geo is not None:
        return node._geo
    coord = node.f.get("coord")
    pts = np.array(coord.f.get("point", []), np.float64).reshape(-1, 3) if isinstance(coord, _Node) else np.zeros((0, 3))
    faces = _faces(node.f.get("coordIndex", []))
    res = None
    if len(pts) and faces:
        faces = [f for f in faces if max(f) < len(pts)]
        tris, owner = _triangulate(faces, pts) if faces else (np.zeros((0, 3), np.int64), None)
        vcol = None
        col = node.f.get("color")
        if isinstance(col, _Node):
            cc = np.array(col.f.get("color", []), np.float64).reshape(-1, 3)
            if len(cc) == len(pts):
                vcol = cc
        ccw = node.f.get("ccw", True)
        crease = node.f.get("creaseAngle", [0.0])
        crease = float(crease[0] if isinstance(crease, list) and crease else crease or 0.0)
        res = (pts, tris, vcol, bool(ccw), crease)
    node._geo = res if res is not None else ()
    return node._geo


def _box(f):
    s = (list(f.get("size", [2, 2, 2])) + [2, 2, 2])[:3]
    h = np.array(s) / 2
    pts = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], np.float64) * h
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = np.array([t for a, b, c, d in q for t in ((a, b, c), (a, c, d))], np.int64)
    return pts, tris, None, True, 0.0


def _shape_arrays(node: _Node, M: np.ndarray, color):
    g = node.f.get("geometry")
    if not isinstance(g, _Node):
        return None
    if g.type == "IndexedFaceSet":
        geo = _ifs(g)
    elif g.type == "Box":
        geo = _box(g.f)
    else:
        return None
    if not geo:
        return None
    pts, tris, vcol, ccw, crease = geo
    if len(tris) == 0:
        return None
    P = pts @ M[:3, :3].T + M[:3, 3]
    if np.linalg.det(M[:3, :3]) < 0:                     # ayna: yuz yonu tersine doner
        ccw = not ccw
    if not ccw:
        tris = tris[:, ::-1]
    p0, p1, p2 = P[tris[:, 0]], P[tris[:, 1]], P[tris[:, 2]]
    fn = np.cross(p1 - p0, p2 - p0)
    flen = np.linalg.norm(fn, axis=1, keepdims=True)
    keep = flen[:, 0] > 1e-18
    tris, fn, flen = tris[keep], fn[keep], flen[keep]
    if len(tris) == 0:
        return None
    flat = fn / flen
    if crease > 1e-6:
        vs = np.zeros_like(P)
        for k in range(3):
            np.add.at(vs, tris[:, k], fn)               # alan agirlikli tepe normali
        vl = np.linalg.norm(vs, axis=1, keepdims=True)
        vl[vl == 0] = 1
        vn = vs / vl
        cosc = np.cos(min(crease, np.pi))
        nrm = np.empty((len(tris), 3, 3))
        for k in range(3):
            sm = vn[tris[:, k]]
            use = (np.einsum("ij,ij->i", sm, flat) >= cosc)[:, None]
            nrm[:, k] = np.where(use, sm, flat)
    else:
        nrm = np.repeat(flat[:, None, :], 3, axis=1)
    pos = P[tris].reshape(-1, 3)
    if vcol is not None:
        rgb = vcol[tris].reshape(-1, 3)
        col = np.concatenate([rgb, np.full((len(rgb), 1), color[3])], axis=1)
    else:
        col = np.tile(np.array(color, np.float64), (len(pos), 1))
    return pos, nrm.reshape(-1, 3), col


def _collect(nodes, M, out, appearance_default=None, depth=0):
    if depth > 64:
        return
    for n in nodes:
        if not isinstance(n, _Node):
            continue
        t = n.type
        if t == "Transform":
            Mn = M @ _transform_matrix(n.f)
            _collect(_children(n), Mn, out, depth=depth + 1)
        elif t in ("Group", "Collision", "Anchor", "Billboard"):
            _collect(_children(n), M, out, depth=depth + 1)
        elif t == "Switch":
            ch = n.f.get("choice", [])
            w = n.f.get("whichChoice", [-1])
            w = int(w[0] if isinstance(w, list) and w else -1)
            if 0 <= w < len(ch):
                _collect([ch[w]], M, out, depth=depth + 1)
        elif t == "LOD":
            lv = n.f.get("level", [])
            if lv:
                _collect([lv[0]], M, out, depth=depth + 1)
        elif t == "Shape":
            r = _shape_arrays(n, M, _material(n.f.get("appearance")))
            if r is not None:
                out.append(r)


def _children(n: _Node):
    c = n.f.get("children", [])
    return c if isinstance(c, list) else [c]


def load_wrl(path: Path) -> MeshData | None:
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", errors="ignore")
    head = text[:64].lower()
    if text.startswith("#vrml v1") or "vrml v1" in head:
        return None                                      # VRML 1.0 desteklenmiyor
    roots = _Parser(text).parse_root()
    parts: list = []
    _collect(roots, np.eye(4), parts)
    if not parts:
        return None
    pos = np.concatenate([p[0] for p in parts]) * UNIT_MM
    nrm = np.concatenate([p[1] for p in parts])
    col = np.concatenate([p[2] for p in parts])
    idx = np.arange(len(pos), dtype=np.uint32).reshape(-1, 3)
    return MeshData(pos.astype(np.float32), nrm.astype(np.float32),
                    np.clip(col * 255 + 0.5, 0, 255).astype(np.uint8), idx)
