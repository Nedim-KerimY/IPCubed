"""KiCad toolbar action: toggle the IPCubed 3D view (starts the viewer in the background on first use)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ipcubed.ctl import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "toggle"))
