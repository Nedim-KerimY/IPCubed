import re, sys, time, pickle
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import numpy as np
from PIL import Image, ImageDraw

PPM = 24                    # piksel / mm
ORG = (107.0, 46.0)         # SVG (0,0) = kart sol-ust (KiCad koord.)
W, H = 152.88, 89.99


def parse_svg(path):
    s = open(path, encoding="utf-8", errors="ignore").read()
    # stroke genislikleri grup bazli; basitce her path'i kendi stili ile al
    out = []
    for m in re.finditer(r'<path d="([^"]+)"', s):
        if " A" in m.group(1) or "A" in m.group(1): continue
        pts = [tuple(map(float, p)) for p in re.findall(r"([-0-9.]+)\s+([-0-9.]+)", m.group(1))]
        if len(pts) >= 2:
            out.append(pts)
    circles = [(float(a), float(b), float(r)) for a, b, r in re.findall(r'<circle cx="([-0-9.]+)" cy="([-0-9.]+)" r="([-0-9.]+)"', s)]
    return out, circles


def main(side="top"):
    paths, circles = parse_svg(rf"{__import__('os').environ['TEMP']}\silk_ref\{'top' if side == 'top' else 'bot'}.svg")
    img_ref = Image.new("L", (int(W * PPM) + 8, int(H * PPM) + 8), 0)
    d = ImageDraw.Draw(img_ref)
    for pts in paths:
        d.line([(x * PPM, y * PPM) for x, y in pts], fill=255, width=max(1, int(0.12 * PPM)))

    # benim silk geometrim
    from ipcubed.kicad_source import KiCadSource
    from ipcubed.silk import fetch_silk, shape_geometry, text_geometry
    from shapely.ops import unary_union
    b = KiCadSource().board
    sd = fetch_silk(b, b.get_footprints())
    shp = shape_geometry(sd.shapes[side])
    txt = []
    for t in sd.texts[side]:
        g = text_geometry(t)
        if g is not None and not g.is_empty:
            txt.append(g)
    print("sekiller", len(shp), "yazilar", len(txt), "yazi ornegi:", sd.texts[side][0])
    img_me = Image.new("L", img_ref.size, 0)
    dm = ImageDraw.Draw(img_me)
    def draw(g, col=255):
        for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            ext = [((x - ORG[0]) * PPM, (y - ORG[1]) * PPM) for x, y in poly.exterior.coords]
            dm.polygon(ext, fill=col)
            for r in poly.interiors:
                dm.polygon([((x - ORG[0]) * PPM, (y - ORG[1]) * PPM) for x, y in r.coords], fill=0)
    for g in shp:
        draw(g)
    for g in txt:
        draw(g)
    # fark gorseli
    a, m = np.asarray(img_ref) > 0, np.asarray(img_me) > 0
    rgb = np.zeros(a.shape + (3,), np.uint8)
    rgb[a & ~m] = (255, 40, 40)       # yalniz KiCad
    rgb[m & ~a] = (40, 255, 40)       # yalniz benim
    rgb[a & m] = (255, 255, 0)
    Image.fromarray(rgb).save(rf"{__import__('os').environ['TEMP']}\silkdiff_{side}.png")
    print("ortak", (a & m).sum(), "yalniz KiCad", (a & ~m).sum(), "yalniz ben", (m & ~a).sum())
    # yakin plan: yazi bolgesi
    for name, box in {"zoomA": (20, 20, 75, 50), "zoomB": (95, 25, 150, 55)}.items():
        x0, y0, x1, y1 = [int(v * PPM) for v in box]
        Image.fromarray(rgb[y0:y1, x0:x1]).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.NEAREST).save(rf"{__import__('os').environ['TEMP']}\silkdiff_{side}_{name}.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "top")

