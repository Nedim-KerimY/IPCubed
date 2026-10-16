"""wgpu adaptor secimi: desteklenen GPU surucusu yoksa yazilim cizicisine dus, hic yoksa nedenini soyle.

wgpu Windows'ta DirectX 12 / Vulkan ister. Eski GPU'larda (or. Intel HD 4000: DX12 ve Vulkan surucusu yok) yalniz OpenGL
kalir ve wgpu'nun OpenGL yolu cogu zaman calismaz: 3D sessizce gelmezdi. Sira:
  1) donanim GPU, DX12 / Vulkan / Metal (harici once)
  2) yazilim cizici: Windows WARP (DX12, "Microsoft Basic Render Driver"), Linux llvmpipe: yavas ama calisir
  3) OpenGL (son care)
"""
from __future__ import annotations

from .log import _log

_HW = ("discretegpu", "integratedgpu", "virtualgpu")


def _rank(info: dict) -> tuple:
    backend = str(info.get("backend_type", "")).lower()
    kind = str(info.get("adapter_type", "")).lower()
    gl = "gl" in backend
    hw = kind in _HW
    tier = 0 if hw and not gl else 1 if not gl else 2
    return tier, 0 if kind == "discretegpu" else 1


def _desc(info: dict) -> str:
    return f"{info.get('device', '?')} ({info.get('backend_type', '?')}, {info.get('adapter_type', '?')})"


class Choice:
    def __init__(self, adapter=None, info=None, software=False, error="", tried=()):
        self.adapter, self.info, self.software, self.error, self.tried = adapter, info or {}, software, error, list(tried)

    @property
    def description(self) -> str:
        return _desc(self.info) if self.info else "none"


def choose() -> Choice:
    """Adaptoru sec ve pygfx'e bildir (renderer olusturulmadan ONCE cagrilmali)."""
    import wgpu
    try:
        adapters = list(wgpu.gpu.enumerate_adapters_sync())
    except Exception as e:  # noqa: BLE001
        _log(f"gpu: adaptorler listelenemedi: {type(e).__name__}: {e}")
        adapters = []
    infos = []
    for a in adapters:
        try:
            infos.append((a, dict(a.info)))
        except Exception:  # noqa: BLE001
            continue
    tried = [_desc(i) for _, i in infos]
    _log("gpu: adaptorler: " + ("; ".join(tried) or "yok"))
    if not infos:                                   # listeleme desteklenmiyorsa wgpu'nun kendi secimi, sonra yazilim cizici
        for kw in ({"power_preference": "high-performance"}, {"force_fallback_adapter": True}):
            try:
                a = wgpu.gpu.request_adapter_sync(**kw)
            except Exception as e:  # noqa: BLE001
                _log(f"gpu: request_adapter({kw}) basarisiz: {e}")
                a = None
            if a is not None:
                infos = [(a, dict(a.info))]
                break
    if not infos:
        return Choice(error="No graphics adapter usable by wgpu was found (DirectX 12, Vulkan or OpenGL).", tried=tried)
    infos.sort(key=lambda ai: _rank(ai[1]))
    adapter, info = infos[0]
    try:
        import pygfx as gfx
        gfx.renderers.wgpu.select_adapter(adapter)
    except Exception as e:  # noqa: BLE001
        _log(f"gpu: select_adapter basarisiz: {e}")
    software = str(info.get("adapter_type", "")).lower() == "cpu"
    _log(f"gpu: secilen {_desc(info)}{' (yazilim cizici)' if software else ''}")
    return Choice(adapter, info, software, tried=tried)


UNSUPPORTED_TEXT = (
    "IPCubed's 3D view needs a graphics driver with DirectX 12 or Vulkan (on Linux: Vulkan or OpenGL 3.3+), "
    "and none could be used on this computer.\n\n"
    "Older graphics chips (for example Intel HD 4000 and earlier) have no DirectX 12 / Vulkan driver. "
    "Updating the graphics driver can help on newer chips.")

SOFTWARE_NOTE = "Software rendering: no supported GPU driver (slow)"
