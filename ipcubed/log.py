"""Hata ayiklama gunlugu (IPCUBED_DEBUG=1 -> %TEMP%/ipcubed.log). Hafif: her surecten iceri aktarilabilir."""
import time


def _log(msg: str):
    import os, tempfile
    if os.environ.get("IPCUBED_DEBUG") or os.environ.get("KICADVIEW_DEBUG"):
        with open(os.path.join(tempfile.gettempdir(), "ipcubed.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
