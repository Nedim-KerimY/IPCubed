"""Orbit kamera donanimi: CAD tarzi kontrol + 2D<->3D yumusak gecis.

Durum: hedef nokta, gorunur yukseklik (hedef duzleminde, dunya mm), yaw/pitch (derece), fov.
fov degisirken gorunur yukseklik sabit tutulur (dolly-zoom): kucuk fov ~ ortografik "2D" bakis.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace

import numpy as np


@dataclass
class RigState:
    target: tuple[float, float, float] = (0.0, 0.0, 0.8)
    view_h: float = 100.0      # hedef duzleminde gorunen yukseklik (mm)
    yaw: float = 0.0           # derece
    pitch: float = 48.0        # derece, 90 = tam ustten
    fov: float = 35.0          # derece (dikey)


def _ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, t)))      # smoothstep-cos


def basis(yaw: float, pitch: float):
    """-> (konum yonu d, ileri f, sag r, yukari u). Z-yukari dunya."""
    y, p = math.radians(yaw), math.radians(pitch)
    d = np.array([math.cos(p) * math.sin(y), -math.cos(p) * math.cos(y), math.sin(p)])
    f = -d
    r = np.array([math.cos(y), math.sin(y), 0.0])
    u = np.cross(r, f)
    return d, f, r, u


class CameraRig:
    FOV_2D = 3.0
    FOV_ORTHO = 3.0            # ortografik mod: cok kucuk gorus acisi + ayni gorunur yukseklik (dolly-zoom) = pratikte ortografik

    def __init__(self, camera):
        self.camera = camera
        self.s = RigState()
        self.s2d = RigState(pitch=90.0, fov=self.FOV_2D)
        self.s3d = RigState()
        self.mode = "3d"
        self._anim = None          # (t0, dur, a, b, lift)
        self.on_change = lambda: None
        self.plane_z = 0.8
        self.aspect = 1.6

    # --- poz uygulama --------------------------------------------------------------
    def apply(self):
        s = self.s
        d, f, r, u = basis(s.yaw, min(s.pitch, 90.0))
        dist = s.view_h / (2 * math.tan(math.radians(s.fov) / 2))
        pos = np.array(s.target) + d * dist
        cam = self.camera
        cam.fov = s.fov
        # Derinlik tamponu cozunurlugu: yakin duzlemi hedef mesafesiyle olceklersek mikron mertebesindeki katmanlar
        # (maske/silk/yuzey kaplama) uzaklasinca z-fighting yapmaz. Cozunurluk ~ d^2 / (near * 2^24).
        try:
            cam.depth_range = (max(0.05, dist * 0.08), dist * 6.0 + 600.0)
        except Exception:
            pass
        cam.local.position = tuple(pos)
        cam.world.reference_up = tuple(u)
        cam.look_at(tuple(s.target))

    def set_aspect(self, aspect: float):
        self.aspect = aspect
        try:
            self.camera.aspect = aspect
        except Exception:
            pass

    # --- cerceveleme ---------------------------------------------------------------
    def frame(self, bounds, thickness: float, settings=None):
        """bounds: (minx,miny,maxx,maxy) sahne koordinati."""
        cx, cy = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        self.plane_z = thickness
        tgt = (cx, cy, thickness / 2)
        # 2D: kart ekrana sigsin
        vh2d = max(h, w / self.aspect) * 1.12
        self.s2d = RigState(tgt, vh2d, 0.0, 90.0, self.FOV_2D)
        fov = settings.fov_3d if settings else 35.0
        if settings is not None and getattr(settings, "projection", "perspective") == "orthographic":
            fov = self.FOV_ORTHO
        pitch = settings.pitch_3d if settings else 48.0
        yaw = settings.yaw_3d if settings else 0.0
        self.s3d = RigState(tgt, max(h * 1.25, w / self.aspect * 1.05) * 1.3, yaw, pitch, fov)
        self.s = replace(self.s2d if self.mode == "2d" else self.s3d)
        self.apply()

    # --- animasyon -----------------------------------------------------------------
    def go(self, mode: str, ms: int = 700, immediate: bool = False):
        goal = self.s2d if mode == "2d" else self.s3d
        self.mode = mode
        if immediate or ms <= 0:
            self.s = replace(goal)
            self._anim = None
            self.apply()
            return
        self._anim = (time.perf_counter(), ms / 1000.0, replace(self.s), replace(goal))

    def goto(self, yaw, pitch: float, ms: int = 450):
        """ViewCube: verilen yaw/pitch'e yumusak don (yaw None: mevcut korunur; en kisa yoldan)."""
        cur = self.s
        if yaw is None:
            yaw = cur.yaw
        yaw_t = cur.yaw + ((yaw - cur.yaw + 180.0) % 360.0 - 180.0)
        goal = replace(cur, yaw=yaw_t, pitch=pitch, fov=self.s3d.fov if cur.fov < 10 else cur.fov)
        self.mode = "3d"
        if ms <= 0:
            self.s = goal
            self._anim = None
            self.apply(); self.on_change()
            return
        self._anim = (time.perf_counter(), ms / 1000.0, replace(cur), goal)

    def set_projection(self, orthographic: bool, fov_persp: float, ms: int = 400):
        """Perspektif <-> ortografik: gorus acisini yumusakca degistirir (gorunur yukseklik sabit, kart ayni boyda kalir)."""
        target = self.FOV_ORTHO if orthographic else fov_persp
        self.s3d = replace(self.s3d, fov=target)
        if self.mode == "2d" or self._anim:
            return
        if ms <= 0:
            self.s = replace(self.s, fov=target)
            self.apply(); self.on_change()
            return
        self._anim = (time.perf_counter(), ms / 1000.0, replace(self.s), replace(self.s, fov=target))

    def set_start_2d(self):
        """Animasyonu 2D'den baslatmak icin."""
        self.s = replace(self.s2d)
        self.apply()

    @property
    def animating(self) -> bool:
        return self._anim is not None

    def tick(self) -> bool:
        """Animasyonu ilerlet. Degisti ise True."""
        if self._anim is None:
            return False
        t0, dur, a, b = self._anim
        k = (time.perf_counter() - t0) / dur
        e = _ease(k)
        lerp = lambda x, y: x + (y - x) * e
        # fov ve gorunur yukseklik log uzayinda, boylece his dogal olur
        llerp = lambda x, y: math.exp(math.log(x) + (math.log(y) - math.log(x)) * e)
        lift = 1.0 + 0.10 * math.sin(math.pi * min(1.0, k))               # ortada hafif geri cekil ("elime al")
        self.s = RigState(
            tuple(lerp(p, q) for p, q in zip(a.target, b.target)),
            llerp(a.view_h, b.view_h) * lift,
            lerp(a.yaw, b.yaw), lerp(a.pitch, b.pitch),
            llerp(a.fov, b.fov),
        )
        if k >= 1.0:
            self.s = replace(b)
            self._anim = None
        self.apply()
        return True

    # --- CAD tarzi girdi ----------------------------------------------------------
    def _pix_to_plane(self, nx: float, ny: float):
        """Ekran (-1..1) -> z=plane_z duzleminde dunya noktasi."""
        s = self.s
        d, f, r, u = basis(s.yaw, min(s.pitch, 90.0))
        th = math.tan(math.radians(s.fov) / 2)
        dist = s.view_h / (2 * th)
        pos = np.array(s.target) + d * dist
        ray = f + r * (nx * th * self.aspect) + u * (ny * th)
        if abs(ray[2]) < 1e-9:
            return None
        k = (self.plane_z - pos[2]) / ray[2]
        return pos + ray * k if k > 0 else None

    def rotate(self, dx_px: float, dy_px: float):
        if self._anim:
            return
        self.mode = "3d"
        self.s.yaw -= dx_px * 0.35
        self.s.pitch = max(-90.0, min(90.0, self.s.pitch + dy_px * 0.35))      # -90: kartin altindan (arka yuz) bakis
        if self.s.fov < 10:               # 2D'den cikis: perspektife don
            self.s.fov = self.s3d.fov
        self.apply(); self.on_change()

    def pan(self, dx_px: float, dy_px: float, viewport_h: float):
        if self._anim:
            return
        s = self.s
        _, _, r, u = basis(s.yaw, min(s.pitch, 90.0))
        scale = s.view_h / viewport_h
        t = np.array(s.target) - r * dx_px * scale + u * dy_px * scale
        # zemin duzleminde kal: yatay duzlem hareketi
        s.target = (t[0], t[1], s.target[2])
        self.apply(); self.on_change()

    def zoom(self, factor: float, nx: float = 0.0, ny: float = 0.0):
        """factor<1 yakinlastirir. Imlec altindaki nokta sabit kalir."""
        if self._anim:
            return
        before = self._pix_to_plane(nx, ny)
        self.s.view_h = max(2.0, min(2000.0, self.s.view_h * factor))
        after = self._pix_to_plane(nx, ny)
        if before is not None and after is not None:
            d = before - after
            t = np.array(self.s.target) + np.array([d[0], d[1], 0.0])
            self.s.target = tuple(t)
        self.apply(); self.on_change()
