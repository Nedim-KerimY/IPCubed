# IPCubed (BETA VERSION, USE AT YOUR OWN RISK, MAY HARM BOARD PRODUCTION FILES)

**KiCad modern 3D viewer plugin using KiCad IPC API.**

IPCubed reads the open board over the KiCad IPC API (KiCad 10+) and shows a live, full-stackup 3D view
(copper, dielectric, solder mask, silkscreen, STEP/WRL models, ViewCube). Core logic is cross-platform;
only the "overlay on top of the KiCad window" part is OS specific (`embed.py` for Windows, `embed_x11.py` for Linux/X11).

Click to watch showcase in YouTube:

[![IPCubed — Altium-Style High Quality 3D Mode in KiCad](https://img.youtube.com/vi/FmNPxe1aHF4/hqdefault.jpg)](https://www.youtube.com/watch?v=FmNPxe1aHF4)

## Install

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

In KiCad: *Preferences → Plugins → Enable KiCad API*.

## Run

```bash
python -m ipcubed                # background daemon; press 3 in the PCB editor canvas (Windows, Linux/X11); exits when KiCad closes
python -m ipcubed --persist      # same, but keeps running after KiCad closes (used by autostart)
python -m ipcubed --standalone --show     # plain window (any OS, also Wayland)
python -m ipcubed.ctl toggle|show|hide|quit    # control a running daemon (bind to a desktop shortcut on Wayland)
python -m ipcubed.autostart [--off]      # start at login (Windows registry / XDG autostart / macOS LaunchAgent)
```

## SpaceMouse (Windows)

Click the 3D viewport to focus it, then use the SpaceMouse cap to pan, orbit,
and roll. Push to zoom in; pull to zoom out. Motion stops when the viewport
loses focus, is hidden, or a dialog is open.

**3D Settings → Adjust → SpaceMouse** provides enable, roll, reverse-motion,
and separate pan/zoom and rotation speed controls. Settings save automatically
and are shared across boards.

The Windows backend uses Raw Input without an additional Python dependency.
It reads motion directly rather than using 3DxWare application-specific motion
profiles. Dedicated buttons, display integration, and Linux/macOS SpaceMouse
backends are not implemented.

While the cap moves, and for 150 ms afterward, wheel zoom in the viewport
pauses to prevent duplicate zoom from 3DxWare wheel emulation. This also pauses
a physical mouse wheel during the gesture; wheel zoom returns at rest.
No global driver profiles or mouse settings are changed.

## Platform notes

| | Overlay on KiCad + `3` hotkey | Notes |
|---|---|---|
| Windows 10/11 | yes (tested) | |
| Linux, X11 (or KiCad forced to XWayland: `GDK_BACKEND=x11 kicad`) | yes (**untested**) | needs `python-xlib`; Qt uses the `xcb` platform automatically |
| Linux, native Wayland | no | A window cannot be placed over another client on Wayland: the viewer falls back to a standalone window; use `ipcubed.ctl toggle` from a shortcut |
| macOS | no | standalone window |

* `nvidia-smi` (if installed) feeds the GPU number of the *Performance stats* overlay; otherwise it shows `n/a`.
* Linux needs a Vulkan-capable driver for wgpu (Mesa `vulkan-*` or the NVIDIA driver).
* Settings and caches: `~/.config/ipcubed`, `~/.cache/ipcubed` (Windows: `%LOCALAPPDATA%\ipcubed`).
* Debug log: `IPCUBED_DEBUG=1` → `$TMPDIR/ipcubed.log`.

## License

MIT, see [LICENSE](LICENSE).
