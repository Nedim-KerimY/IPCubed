"""Viewer'i oturum acilisinda arka planda baslat (istege bagli). python -m ipcubed.autostart [--off]

Oturumla baslayan daemon `--persist` ile calisir: KiCad kapaninca cikmaz, bir sonraki KiCad'i bekler.

Windows: HKCU Run; Linux: ~/.config/autostart/ipcubed.desktop; macOS: LaunchAgent.
"""
from __future__ import annotations

import sys
from pathlib import Path

NAME = "ipcubed"


def command() -> str:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe") if sys.platform == "win32" else exe
    py = pyw if pyw.exists() else exe
    root = Path(__file__).resolve().parents[1]
    code = f"import sys,runpy; sys.path.insert(0, r'{root}'); sys.argv[1:] = ['--persist']; runpy.run_module('ipcubed', run_name='__main__')"
    return f'"{py}" -c "{code}"'


def _desktop_path():
    from pathlib import Path
    import os
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "ipcubed.desktop"


def _plist_path():
    from pathlib import Path
    return Path.home() / "Library" / "LaunchAgents" / "com.ipcubed.plist"


def set_autostart(on: bool) -> str:
    root = Path(__file__).resolve().parents[1]
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
                return command()
            try:
                winreg.DeleteValue(k, NAME)
            except FileNotFoundError:
                pass
            return "removed"
    if sys.platform == "darwin":
        path = _plist_path()
        if not on:
            path.unlink(missing_ok=True)
            return "removed"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.ipcubed</string>
<key>ProgramArguments</key><array><string>{sys.executable}</string><string>-m</string><string>ipcubed</string><string>--persist</string></array>
<key>WorkingDirectory</key><string>{root}</string>
<key>RunAtLoad</key><true/>
</dict></plist>
""", encoding="utf-8")
        return str(path)
    path = _desktop_path()                        # Linux: XDG autostart
    if not on:
        path.unlink(missing_ok=True)
        return "removed"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""[Desktop Entry]
Type=Application
Name=IPCubed
Comment=Fast live 3D viewer for the KiCad PCB editor
Exec="{sys.executable}" -m ipcubed --persist
Path={root}
Terminal=false
X-GNOME-Autostart-enabled=true
""", encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    print(set_autostart("--off" not in sys.argv))
