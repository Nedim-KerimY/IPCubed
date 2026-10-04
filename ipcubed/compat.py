"""Ortam uyumlulugu. pygfx'ten ONCE import edilmeli.

Bazi Windows kurulumlarinda Uygulama Denetimi (Smart App Control/WDAC) imzasiz `uharfbuzz`
DLL'ini engeller. pygfx bunu yalnizca yazi sekillendirme icin kullanir; yuklenemezse stub'la.
"""
import sys
import types


def patch() -> None:
    try:
        import uharfbuzz  # noqa: F401
    except Exception:
        sys.modules["uharfbuzz"] = types.ModuleType("uharfbuzz")
        sys.modules["uharfbuzz"].__stub__ = True


patch()
