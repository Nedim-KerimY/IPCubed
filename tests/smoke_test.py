"""IPCubed smoke test: does a fresh install work on this machine?

Run it with the Python of a FRESH virtual environment (CI does this on Windows and Linux for every push; a release is
only published when it passes):

    python -m venv fresh && fresh/bin/python tests/smoke_test.py          (Windows: fresh\\Scripts\\python.exe)

1. installs plugins/ipcubed/deps.txt with the installer's own code path (setup_deps.install: the same pip command, flags
   and progress parsing a user gets after clicking "Download"), then in that environment checks:
2. every pinned version is what deps.txt says,
3. every IPCubed module imports,
4. a STEP model (written with OpenCascade) converts to a coloured mesh,
5. silkscreen text (matplotlib font) and copper/body prisms (shapely + earcut) build,
6. Qt draws the overlay labels (offscreen),
7. wgpu finds an adapter (GPU or software) and pygfx renders a non-empty frame offscreen,
8. the longest installed file path fits the budget the installer checks against Windows' 260-character limit.

--skip-install: only the checks (environment already has the components).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULTS: list[tuple[str, bool, str]] = []


def check(name):
    def deco(fn):
        t = time.perf_counter()
        try:
            detail = fn() or ""
            RESULTS.append((name, True, f"{detail} ({time.perf_counter() - t:.1f}s)"))
        except Exception as e:  # noqa: BLE001
            RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
        return fn
    return deco


def install_components():
    """Kullanicinin "Download" sonrasi calisan kod yolu (diyaloglar ve kullanici klasorleri devre disi)."""
    from ipcubed import setup_deps as sd
    tmp = Path(tempfile.mkdtemp(prefix="ipcubed-test-"))
    sd._marker = lambda: tmp / "marker.json"
    sd.log_path = lambda: tmp / "install.log"
    sd._set_lock = lambda *a: None
    sd._drop_lock = lambda: None
    sd._kicad_running = lambda: False
    sd.info = lambda text, error=False: print(("ERROR: " if error else "") + text)
    rc = sd.install(False)
    log = (tmp / "install.log").read_text(encoding="utf-8", errors="replace")
    print(log[-3000:])
    assert rc == 0 and (tmp / "marker.json").exists(), f"installer failed (rc={rc})"
    return "installer ok"


# ---------------------------------------------------------------------------------------------------------------- checks
def run_checks():
    @check("pinned versions")
    def _():
        from importlib.metadata import version
        from packaging.requirements import Requirement
        bad, n = [], 0
        for line in (PLUGINS / "ipcubed" / "deps.txt").read_text().splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            r = Requirement(line)
            if r.marker is not None and not r.marker.evaluate():
                continue
            n += 1
            v = version(r.name)
            if not r.specifier.contains(v, prereleases=True):
                bad.append(f"{r.name} {v} (wants {r.specifier})")
        assert not bad, "; ".join(bad)
        return f"{n} packages match deps.txt"

    @check("all modules import")
    def _():
        import importlib
        skip = {"embed_x11"} if sys.platform != "linux" else set()
        if sys.platform != "win32":
            skip.add("embed")
        mods = sorted(p.stem for p in (PLUGINS / "ipcubed").glob("*.py") if p.stem not in skip | {"__main__"})
        for m in mods:
            importlib.import_module(f"ipcubed.{m}")
        return f"{len(mods)} modules"

    @check("STEP model -> mesh (OpenCascade)")
    def _():
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        from ipcubed.model_loader import convert_step
        f = Path(tempfile.mkdtemp()) / "box.step"
        w = STEPControl_Writer()
        w.Transfer(BRepPrimAPI_MakeBox(10.0, 5.0, 2.0).Shape(), STEPControl_AsIs)
        assert w.Write(str(f)) == IFSelect_RetDone
        m = convert_step(f)
        assert m is not None and len(m.indices) >= 12, "no triangles"
        lo, hi = m.bounds
        assert abs((hi - lo)[0] - 10.0) < 1e-3, f"bad size {hi - lo}"
        return f"{len(m.indices)} triangles"

    @check("silkscreen text + copper prisms")
    def _():
        from shapely.geometry import Polygon
        from ipcubed.prism import polygon_prisms
        from ipcubed.silk import text_geometry
        g = text_geometry(dict(value="R11 IPCubed", x=0.0, y=0.0, angle=0.0, sx=1.0, sy=1.0, stroke=0.15, halign=0,
                               valign=0, font="", bold=False, italic=False, mirrored=False, line_spacing=1.0))
        assert g is not None and not g.is_empty and g.area > 0.5, "empty text"
        P = polygon_prisms([Polygon([(0, 0), (2, 0), (2, 1), (0, 1)], [[(0.5, 0.25), (1, 0.25), (1, 0.75)]])], 0.0, 0.035)
        assert P is not None and len(P[0]) > 0, "empty prism"
        return f"text area {g.area:.1f} mm2"

    @check("Qt offscreen (overlay labels)")
    def _():
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
        from ipcubed.exploder import label_image
        a = label_image("Loading silkscreen, copper …", 1.0)
        assert a.shape[0] > 10 and a.shape[1] > 100 and a[..., 3].max() > 0
        return f"label {a.shape[1]}x{a.shape[0]}"

    @check("wgpu + pygfx offscreen render")
    def _():
        import numpy as np
        import pygfx as gfx
        import wgpu
        from rendercanvas.offscreen import RenderCanvas
        ad = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        info = f"{ad.info['device']} ({ad.info['backend_type']}, {ad.info['adapter_type']})"
        canvas = RenderCanvas(size=(160, 120), pixel_ratio=1)
        renderer = gfx.WgpuRenderer(canvas)
        scene = gfx.Scene()
        scene.add(gfx.Background.from_color("#000"))
        scene.add(gfx.Mesh(gfx.box_geometry(1, 1, 1), gfx.MeshBasicMaterial(color="#3c3")))
        cam = gfx.PerspectiveCamera(50)
        cam.show_object(scene)
        canvas.request_draw(lambda: renderer.render(scene, cam))
        img = np.asarray(canvas.draw())
        assert img.ndim == 3 and img[..., 1].max() > 100, "frame is empty"
        return info

    @check("installed file paths fit Windows' limit")
    def _():
        import sysconfig
        from ipcubed.setup_deps import MAX_REL_PATH
        sp = Path(sysconfig.get_paths()["purelib"])
        longest = max((len(str(p.relative_to(sp))) for p in sp.rglob("*")), default=0)
        if sys.platform != "win32":            # sinir yalniz Windows'ta; Linux/macOS tekerleklerinde yollar farkli
            return f"longest {longest} (limit only checked on Windows)"
        # tam esitlik: buyukse kurulum yarim kalir, kucukse kontrol uzun kullanici adlarini gereksiz engeller
        assert longest == MAX_REL_PATH, f"longest relative path {longest} != MAX_REL_PATH {MAX_REL_PATH}: update setup_deps"
        return f"longest {longest} == {MAX_REL_PATH}"

    @check("installer helpers")
    def _():
        from ipcubed import setup_deps as sd
        p = sd._Progress(100)
        for line in ("Downloading pyside6_essentials-6.11.2-cp310-abi3-win_amd64.whl (76.9 MB)", "Progress 38450000 of 76900000"):
            p.feed(line)
        assert 0.3 < p.fraction() < 0.5 and "Qt" in p.message()
        s = sd.smart_app_control_state()
        if sys.platform != "win32":
            assert s is None
        else:                              # Windows Server / eski Windows 10: anahtar yok -> None (kapali sayilir)
            assert s is None or s in (0, 1, 2), s
        return f"smart app control state: {s}"


def main() -> int:
    if "--skip-install" not in sys.argv:
        print("== installing components (setup_deps.install) ==", flush=True)
        try:
            install_components()
        except Exception as e:  # noqa: BLE001
            print(f"FAIL install: {e}")
            return 1
    run_checks()
    print("\n== IPCubed smoke test ==")
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed on {sys.platform}, Python {sys.version.split()[0]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
