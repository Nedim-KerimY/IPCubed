"""Kalici kullanici ayarlari (JSON). Pencere ve sahne bu nesneyi paylasir."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from .paths import config_dir


# Genel gorunum stilleri: maske + isik + parlaklik + arka plan birlikte (canli karsilastirma icin)
STYLES = {
    # Stiller yalnizca isik / parlaklik / maske etkisi / arka plani degistirir; KART RENKLERINE
    # (maske rengi, bakir, dielektrik, silk) DOKUNMAZ - onlari kullanici secer ve korunur.
    "Vivid": dict(mask_density=0.88, mask_haze=0.34, mask_gloss=1.5, light_intensity=1.0,
                                   bg_top="#46566f", bg_bottom="#0d1119"),
    "Bright studio":          dict(mask_density=0.80, mask_haze=0.46, mask_gloss=1.1, light_intensity=1.25,
                                   bg_top="#6d7e98", bg_bottom="#1a2230"),
    "Realistic dark":          dict(mask_density=0.93, mask_haze=0.26, mask_gloss=1.9, light_intensity=0.92,
                                   bg_top="#2c333f", bg_bottom="#090b10"),
}
# Lehim maskesi hazir renkleri: renk (ton), yogunluk (altindaki bakiri boyayan filtre), pus (mat ton), silk
MASK_PRESETS = {
    "Green":       dict(mask_color="#14a152", mask_density=0.88, mask_haze=0.34, silk_color="#fbfbf6"),
    "Dark green":  dict(mask_color="#0d7a3a", mask_density=0.90, mask_haze=0.30, silk_color="#fbfbf6"),
    "Blue":        dict(mask_color="#1c66e0", mask_density=0.88, mask_haze=0.36, silk_color="#fbfbf6"),
    "Red":     dict(mask_color="#b3171d", mask_density=0.92, mask_haze=0.32, silk_color="#f5f5f0"),
    "Black":       dict(mask_color="#17181c", mask_density=0.97, mask_haze=0.48, silk_color="#f5f5f0"),
    "White":       dict(mask_color="#ecece7", mask_density=0.15, mask_haze=0.60, silk_color="#16171a"),
    "Yellow":        dict(mask_color="#d6b50f", mask_density=0.80, mask_haze=0.38, silk_color="#16171a"),
    "Purple":         dict(mask_color="#5a2a99", mask_density=0.92, mask_haze=0.32, silk_color="#f5f5f0"),
}


@dataclass
class Settings:
    # gorunurluk (anahtar -> bool). Anahtarlar: cu:<id>, diel:<n>, mask:top/bottom, silk:top/bottom, finish:*, barrel
    layer_visible: dict = field(default_factory=dict)
    show_comp_top: bool = True
    show_comp_bottom: bool = True
    show_pads: bool = True
    show_inner_copper: bool = False          # ic bakir katmanlari varsayilan gizli (hizli)
    # renkler
    mask_color: str = "#14a152"
    copper_color: str = "#e08d4a"
    pad_color: str | None = None             # yuzey kaplama (acikta kalan bakir); None: kartin kaplama turunden otomatik
    substrate_color: str = "#95965c"         # dielektrik (FR4/prepreg) rengi
    edge_color: str = "#95965c"              # kart kesiti (dielektrikle ayni)
    silk_color: str = "#fbfbf6"
    bg_top: str = "#46566f"                  # mavimsi stüdyo gradyani
    bg_bottom: str = "#0d1119"
    mask_gloss: float = 1.5                  # lake yansimasi siddeti
    # lehim maskesi gorunumu: yogunluk = renk filtresi (altindaki bakiri yesile boyar), pus = parlak yesil katki
    mask_density: float = 0.90
    mask_haze: float = 0.30
    substrate_opacity: float = 1.0
    pth_opacity: float = 1.0                 # exploded view: PTH / via tup (varil) opakligi
    polygon_opacity: float = 1.0             # exploded view: zone/pour opakligi (sag tik kaydirici)
    highlight_polygons: bool = True          # Net Highlighter: pour'lar da vurgulansin / secilebilsin
    settings_rev: int = 2                    # kayitli ayar gocleri (load)
    # maske
    mask_expansion: float | None = None      # None: kartin ayari
    tent_vias: bool | None = None            # None: via basina KiCad ayari; True: hepsi maskeyle kapali; False: hepsi acik
    # kamera
    fov_3d: float = 35.0
    pitch_3d: float = 48.0
    yaw_3d: float = 0.0
    anim_ms: int = 700
    projection: str = "perspective"           # "perspective" | "orthographic"
    show_stats: bool = False                 # sag altta FPS/CPU/RAM/GPU yazisi
    show_view_cube: bool = True              # sag ustte ViewCube (gizlenebilir)
    custom_presets: dict = field(default_factory=dict)   # ice aktarilan renk ayarlari: ad -> degerler
    # isik
    light_intensity: float = 1.0             # ana carpan
    ambient_level: float = 0.50
    key_level: float = 1.75
    fill_level: float = 0.60
    env_intensity: float = 1.0               # ortam yansimasi carpani (metal, lake, bilesen)
    # maske renk ince ayari (renk secici ustune carpanlar)
    mask_value: float = 1.0                  # parlaklik
    mask_saturation: float = 1.0             # doygunluk
    # bilesen modelleri
    model_saturation: float = 1.35
    model_contrast: float = 3.0

    TUNING_KEYS = ("light_intensity", "ambient_level", "key_level", "fill_level", "env_intensity", "mask_gloss",
                   "mask_density", "mask_haze", "mask_value", "mask_saturation", "model_saturation", "model_contrast")

    def reset_tuning(self):
        d = Settings()
        for k in self.TUNING_KEYS:
            setattr(self, k, getattr(d, k))

    def effective_mask_color(self) -> str:
        """mask_color + parlaklik/doygunluk carpanlari (HSV)."""
        import colorsys
        c = self.mask_color.lstrip("#")
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        s = min(1.0, s * self.mask_saturation)
        v = min(1.0, v * self.mask_value)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

    def visible(self, key: str) -> bool:
        if key in self.layer_visible:
            return bool(self.layer_visible[key])
        if key.startswith("cu:") and key not in ("cu:3", "cu:34"):
            return self.show_inner_copper
        return True

    def save(self):
        try:
            (config_dir() / "settings.json").write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            d = json.loads((config_dir() / "settings.json").read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            for k, v in d.items():
                if k in names:
                    setattr(s, k, v)
            if any(abs(s.model_contrast - old) < 1e-9 for old in (1.12, 1.8)):       # eski varsayilan kontrast -> yeni varsayilan
                s.model_contrast = 3.0
            # onceki surumlerin VARSAYILAN dielektrik/kesit renkleri kaydedilmis olabilir: yeni varsayilana tasi
            for k, old in (("substrate_color", {"#1d4a2c", "#1a2a1f", "#2a6b40", "#14301f"}), ("edge_color", {"#b09a55", "#9c8b4f"})):
                if getattr(s, k) in old:
                    setattr(s, k, getattr(cls(), k))
            if s.settings_rev < 2:                     # rev 2: varsayilan dielektrik opakligi yine %100 (rev 1'in 0.9'u geri alinir)
                if abs(s.substrate_opacity - 0.9) < 1e-9:
                    s.substrate_opacity = 1.0
                s.settings_rev = 2
        except Exception:
            pass
        return s
