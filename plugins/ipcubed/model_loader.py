"""STEP -> renkli ucgen mesh (OpenCascade/XCAF) + disk cache.

Cikti `MeshData`: tek mesh, vertex basina renk. Birim: mm (KiCad model koordinatlari).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .paths import cache_dir

CACHE_VERSION = 5
DEFAULT_COLOR = (0.62, 0.62, 0.65, 1.0)


@dataclass
class MeshData:
    positions: np.ndarray  # (N,3) float32
    normals: np.ndarray    # (N,3) float32
    colors: np.ndarray     # (N,4) uint8
    indices: np.ndarray    # (M,3) uint32

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(0), self.positions.max(0)


def _key(path: Path, quality: str) -> str:
    st = path.stat()
    h = hashlib.blake2b(digest_size=12)
    h.update(f"{CACHE_VERSION}|{quality}|{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()


def load_model(path: Path, quality: str = "normal") -> MeshData | None:
    """Cache'ten oku, yoksa donustur ve cache'le."""
    path = Path(path)
    cf = cache_dir() / f"{_key(path, quality)}.npz"
    if cf.exists():
        try:
            z = np.load(cf)
            return MeshData(z["p"], z["n"], z["c"], z["i"])
        except Exception:
            cf.unlink(missing_ok=True)
    ext = path.suffix.lower()
    if ext in (".step", ".stp"):
        mesh = convert_step(path, quality)
    elif ext in (".wrl", ".wrz", ".vrml"):
        from .wrl import load_wrl
        mesh = load_wrl(path)
    else:
        return None
    if mesh is not None:
        tmp = cf.with_suffix(".tmp.npz")
        np.savez(tmp, p=mesh.positions, n=mesh.normals, c=mesh.colors, i=mesh.indices)
        tmp.replace(cf)
    return mesh


_QUALITY = {  # (linear deflection mm, angular rad)
    "draft": (0.15, 0.8),
    "normal": (0.05, 0.5),
    "fine": (0.015, 0.3),
}


def convert_step(path: Path, quality: str = "normal") -> MeshData | None:
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_ColorRGBA, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
    from OCP.XCAFPrs import XCAFPrs_DocumentExplorer, XCAFPrs_DocumentExplorerFlags_OnlyLeafNodes

    lin, ang = _QUALITY[quality]

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True)
    rd.SetNameMode(False)
    if rd.ReadFile(str(path)) != IFSelect_RetDone or not rd.Transfer(doc):
        return None

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    srgb = Quantity_TypeOfColor.Quantity_TOC_sRGB

    def rgba(c):
        r, g, b = c.GetRGB().Values(srgb)
        return (r, g, b, float(c.Alpha()))

    def label_color(label):
        if label.IsNull():
            return None
        c = Quantity_ColorRGBA()
        for ct in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
            if color_tool.GetColor_s(label, ct, c):
                return rgba(c)
        return None

    pos_chunks, col_chunks, idx_chunks = [], [], []
    offset = 0

    from OCP.TopoDS import TopoDS_Iterator
    from OCP.XCAFPrs import XCAFPrs
    from OCP.collections import IndexedDataMap_TopoDS_Shape_XCAFPrs_Style_TopTools_ShapeMapHasher as StyleMap

    def emit_face(face, col, node_trsf):
        nonlocal offset
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            return
        trsf = node_trsf.Multiplied(loc.Transformation())
        n = tri.NbNodes()
        pts = np.empty((n, 3), np.float32)
        for i in range(1, n + 1):
            p = tri.Node(i).Transformed(trsf)
            pts[i - 1] = (p.X(), p.Y(), p.Z())
        m = tri.NbTriangles()
        idx = np.empty((m, 3), np.uint32)
        rev = face.Orientation() == TopAbs_REVERSED
        for i in range(1, m + 1):
            a, b, c = tri.Triangle(i).Get()
            idx[i - 1] = (a - 1, c - 1, b - 1) if rev else (a - 1, b - 1, c - 1)
        pos_chunks.append(pts)
        idx_chunks.append(idx + offset)
        col_chunks.append(np.tile(np.array(col, np.float32) * 255, (n, 1)).astype(np.uint8))
        offset += n

    ex = XCAFPrs_DocumentExplorer(doc, XCAFPrs_DocumentExplorerFlags_OnlyLeafNodes)
    while ex.More():
        node = ex.Current()
        ex.Next()
        base = shape_tool.GetShape_s(node.RefLabel)
        node_trsf = node.Location.Transformation()
        node_col = DEFAULT_COLOR
        if node.Style.IsSetColorSurf():
            node_col = rgba(node.Style.GetColorSurfRGBA())
        else:
            node_col = label_color(node.RefLabel) or node_col
        BRepMesh_IncrementalMesh(base, lin, False, ang, True)

        # OpenCascade'in gorsellestirme koduyla ayni yol: etiket + alt sekil stil haritasi, hiyerarsik renk mirasi
        # (compound -> solid -> shell -> face). FindSubShape yalniz dogrudan etiketlenmis yuzleri bulur; STEP'te renkler
        # cogu zaman solid/shell seviyesinde tanimli oldugundan bircok modelde renk kayboluyordu.
        styles = StyleMap()
        XCAFPrs.CollectStyleSettings_s(node.RefLabel, TopLoc_Location(), styles)

        def walk(shape, inherited, node_trsf=node_trsf, node_col=node_col, styles=styles):
            col = inherited
            if styles.Contains(shape):
                st = styles.FindFromKey(shape)
                if st.IsSetColorSurf():
                    col = rgba(st.GetColorSurfRGBA())
            if shape.ShapeType() == TopAbs_FACE:
                emit_face(TopoDS.Face(shape), col or node_col, node_trsf)
                return
            it = TopoDS_Iterator(shape)
            while it.More():
                walk(it.Value(), col)
                it.Next()

        walk(base, None)
    if not pos_chunks:
        return None
    pos = np.concatenate(pos_chunks)
    idx = np.concatenate(idx_chunks)
    return MeshData(pos, _vertex_normals(pos, idx), np.concatenate(col_chunks), idx)


def _vertex_normals(pos: np.ndarray, idx: np.ndarray) -> np.ndarray:
    v0, v1, v2 = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    out = np.zeros_like(pos)
    for k in range(3):
        np.add.at(out, idx[:, k], fn)
    ln = np.linalg.norm(out, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return (out / ln).astype(np.float32)
