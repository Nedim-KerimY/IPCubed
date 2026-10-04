"""Silk kenar durumlari: adli font, eksik font, markup, cok satir, aynali, bos metin, CJK/ozel karakter."""
import sys
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
import ipcubed.silk as s

base = dict(x=0, y=0, angle=0, sx=1.0, sy=1.0, stroke=0.15, halign=1, valign=3, font="", bold=False, italic=False, mirrored=False, line_spacing=1.0)
cases = {
    "stroke fontu": dict(value="R123"),
    "Lato kalin (yok)": dict(value="Hello", font="Lato", bold=True),
    "Arial (var olabilir)": dict(value="Hello", font="Arial"),
    "uydurma font": dict(value="Test", font="NoSuchFont123"),
    "italik": dict(value="Ab", italic=True),
    "overbar": dict(value=s.clean_markup("~{RESET} x^{2} H_{2}O")),
    "cok satir": dict(value="Line1\nLine2\nLine3", valign=1),
    "aynali": dict(value="AB", mirrored=True),
    "ozel karakter": dict(value="3.3V ±5% 10µF 100Ω 25°C"),
    "CJK (eksik glif)": dict(value="温度 センサ"),
    "bos": dict(value="   "),
    "sadece bosluk+satir": dict(value="\n\n"),
    "cok uzun": dict(value="A" * 200),
    "sifir boyut": dict(value="X", sx=0.0, sy=0.0),
    "90 derece": dict(value="UP", angle=90),
    "ortali": dict(value="MID", halign=2, valign=2),
}
for name, kw in cases.items():
    t = dict(base); t.update(kw)
    try:
        g = s.text_geometry(t)
        r = "None" if g is None else (f"bounds={tuple(round(v, 2) for v in g.bounds)}" if not g.is_empty else "bos geometri")
    except Exception as e:
        r = f"HATA {type(e).__name__}: {e}"
    print(f"{name:22s} -> {r}")
print("markup:", repr(s.clean_markup("~{RESET} x^{2} H_{2}O ~{a~{b}}")))
