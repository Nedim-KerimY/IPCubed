import re, sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from OCP.STEPControl import STEPControl_Reader
import ipcubed.model_loader as ml

d = Path(r"C:\Users\erdem\Desktop\antmicro-kintex7-ddr4-tester\lib\3d-models")
files = ["LED_0603_1608Metric.step", "C_0402_1005Metric.step", "R_0402_1005Metric.step", "USB4105-GF-A.step", "1-1825027-1.step", "BarrelJack_3167288_Horizontal.step"]
for fn in files:
    p = d / fn
    if not p.exists():
        continue
    txt = p.read_text(errors="ignore")
    raw = re.findall(r"COLOUR_RGB\s*\(\s*'[^']*'\s*,\s*([-0-9.Ee+]+)\s*,\s*([-0-9.Ee+]+)\s*,\s*([-0-9.Ee+]+)\s*\)", txt)
    rawc = sorted({tuple(round(float(x), 3) for x in t) for t in raw})
    m = ml.convert_step(p, "draft")
    ours = {tuple(int(v) for v in c[:3]) for c in np.unique(m.colors, axis=0)}
    print("==", fn)
    print("  dosyadaki ham renkler (0-1) ilk 4:", rawc[:4], "| toplam benzersiz", len(rawc))
    print("  bizim cikardigimiz (0-255) ilk 4:", sorted(ours)[:4], "| toplam", len(ours))
    # ham -> 0-255 ve sRGB'ye (linear sanip) dönüşüm karsilastirmasi
    def to_srgb(v):
        return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    if rawc:
        a = rawc[0]
        print("  ham ilk renk 0-255:", tuple(round(x * 255) for x in a), "| linear->sRGB'ye cevrilirse:", tuple(round(to_srgb(x) * 255) for x in a))
