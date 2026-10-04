import sys
from pathlib import Path
import numpy as np
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Iterator
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.XCAFPrs import XCAFPrs, XCAFPrs_DocumentExplorer, XCAFPrs_DocumentExplorerFlags_OnlyLeafNodes
from OCP.collections import IndexedDataMap_TopoDS_Shape_XCAFPrs_Style_TopTools_ShapeMapHasher as StyleMap
from OCP.Quantity import Quantity_TypeOfColor

d = Path(r"C:\Users\erdem\Desktop\antmicro-kintex7-ddr4-tester\lib\3d-models")
for fn in ("BarrelJack_3167288_Horizontal.step", "1-1825027-1.step", "LED_0603_1608Metric.step"):
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader(); rd.SetColorMode(True); rd.SetNameMode(False)
    assert rd.ReadFile(str(d / fn)) == IFSelect_RetDone and rd.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ex = XCAFPrs_DocumentExplorer(doc, XCAFPrs_DocumentExplorerFlags_OnlyLeafNodes)
    found, nfaces, colored = set(), 0, 0
    while ex.More():
        node = ex.Current(); ex.Next()
        base = st.GetShape_s(node.RefLabel)
        settings = StyleMap()
        XCAFPrs.CollectStyleSettings_s(node.RefLabel, TopLoc_Location(), settings)

        def style_color(shape):
            if settings.Contains(shape):
                s = settings.FindFromKey(shape)
                if s.IsSetColorSurf():
                    return s.GetColorSurf().Values(Quantity_TypeOfColor.Quantity_TOC_sRGB)
            return None

        def walk(shape, inherited):
            global nfaces, colored
            c = style_color(shape) or inherited
            if shape.ShapeType() == TopAbs_FACE:
                nfaces += 1
                if c is not None:
                    colored += 1
                    found.add(tuple(round(v * 255) for v in c))
                return
            it = TopoDS_Iterator(shape)
            while it.More():
                walk(it.Value(), c)
                it.Next()

        walk(base, None)
    print(fn, "yuz:", nfaces, "renkli yuz:", colored, "renkler:", sorted(found))

