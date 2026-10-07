# IPCubed — KiCad plugin (BETA, USE AT YOUR OWN RISK)

**Live, full-stackup 3D view on top of the KiCad PCB editor, using the KiCad IPC API.**

This `kicad-plugin` branch contains only what KiCad needs to install and run the plugin. Development happens on
[`main`](https://github.com/Nedim-KerimY/IPCubed/tree/main).

[![IPCubed — Altium-Style High Quality 3D Mode in KiCad](https://img.youtube.com/vi/FmNPxe1aHF4/hqdefault.jpg)](https://www.youtube.com/watch?v=FmNPxe1aHF4)

## Requirements

* **KiCad 10.0 or newer**
* Windows 10/11 or Linux (X11). On Wayland and macOS, the 3D view opens in its own window instead of on top of KiCad.
* A GPU driver with Vulkan / DirectX 12 support
* Linux only: a Python 3.10+ interpreter on `PATH`, with the `venv` module (e.g. `sudo apt install python3-venv`)

## Install

### Option A: Plugin and Content Manager (recommended)

1. Download `IPCubed-<version>-pcm.zip` from the [Releases](https://github.com/Nedim-KerimY/IPCubed/releases) page.
   Do **not** use GitHub's green *Code → Download ZIP* button for this option.
2. In KiCad: **Plugin and Content Manager → Install from File...** and pick the zip.
3. Go to step *First run* below.

### Option B: Manual copy

1. Download this branch: *Code → Download ZIP* (on the `kicad-plugin` branch) and extract it.
2. Copy the **contents** of the `plugins` folder into a new folder named `ipcubed` in your KiCad plugin directory:

   | OS | Plugin directory |
   |---|---|
   | Windows | `Documents\KiCad\10.0\plugins\ipcubed\` |
   | Linux | `~/.local/share/kicad/10.0/plugins/ipcubed/` |
   | macOS | `~/Documents/KiCad/10.0/plugins/ipcubed/` |

   After copying, `plugin.json` must be directly inside the `ipcubed` folder.
3. Restart KiCad.

### First run

1. **Preferences → Preferences → Plugins → Enable KiCad API** (tick it, then restart KiCad if asked).
2. Open a board in the PCB editor. A **3D Live** button (cube icon) appears in the top toolbar.
   If it doesn't, check *Preferences → Plugins* and make sure the IPCubed action is enabled.
3. Click **3D Live**. On the very first click KiCad creates a Python environment for the plugin and downloads its
   dependencies (PySide6, pygfx, OpenCascade, about 1 GB). **This can take several minutes.** Wait until it finishes, then
   click the button again.

## Use

| | |
|---|---|
| **3D Live** button | Start the viewer and open the 3D view |
| `3` in the PCB canvas | Toggle 3D on/off (after the viewer is started) |
| `2` / `Esc` | Back to 2D |
| Right-click in 3D | Menu: 3D settings, exploded view, net highlighter, open in a separate window, ... |

The viewer runs in the background while KiCad is open and **exits by itself when KiCad closes**.
Edits you make in KiCad (moving footprints, tracks, zones, silkscreen, ...) appear live in 3D.

## Update / uninstall

* Plugin and Content Manager: install the new zip over the old one, or use *Uninstall* there.
* Manual install: replace or delete the `ipcubed` folder in the plugin directory.

Settings and caches live in `%LOCALAPPDATA%\ipcubed` (Windows), `~/.config/ipcubed` and `~/.cache/ipcubed` (Linux).
You can delete them to reset the plugin.

## Troubleshooting

* **Nothing happens when I click the button:** the first click only installs dependencies. Wait a few minutes and click again.
  KiCad shows plugin environment errors in *Preferences → Plugins*.
* **Linux, native Wayland:** a window cannot be placed over another window there, so the 3D view opens in its own window.
  To get the overlay, start KiCad on XWayland: `GDK_BACKEND=x11 kicad`.
* **Debug log:** set the environment variable `IPCUBED_DEBUG=1` before starting KiCad. The log is written to
  `%TEMP%\ipcubed.log` (Windows) or `/tmp/ipcubed.log` (Linux).

## For maintainers

* `plugins/` is the plugin as KiCad loads it (`plugin.json`, `toggle.py`, `requirements.txt`, the `ipcubed` package).
* `metadata.json` + `resources/icon.png` make up the Plugin and Content Manager package.
* `python tools/build_pcm_zip.py` builds `dist/IPCubed-<version>-pcm.zip`. The *Package KiCad plugin* GitHub Actions
  workflow runs it on every push to this branch and publishes the zip as the `v<version>` pre-release.
  Bump `versions[0].version` in `metadata.json` for a new release.
* To bring in changes from `main`: `git merge main` (the `ipcubed/` → `plugins/ipcubed/` move is followed by git).

## License

MIT, see [LICENSE](LICENSE).
