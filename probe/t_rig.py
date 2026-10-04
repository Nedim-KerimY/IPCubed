import time
from ipcubed import compat
import pygfx as gfx
from ipcubed.camera_rig import CameraRig
from ipcubed.settings import Settings

cam = gfx.PerspectiveCamera(35, 1.6)
rig = CameraRig(cam)
rig.set_aspect(1.6)
rig.frame((107, -136, 260, -46), 1.6, Settings())
rig.set_start_2d()
rig.go("3d", 700)
t0 = time.perf_counter()
n = 0
while rig.animating:
    rig.tick(); n += 1
    s = rig.s
    if n % 8 == 1:
        dist = s.view_h / (2 * __import__('math').tan(__import__('math').radians(s.fov) / 2))
        print(f"t={time.perf_counter()-t0:4.2f}s pitch={s.pitch:5.1f} fov={s.fov:5.1f} view_h={s.view_h:6.1f} dist={dist:7.1f}")
    time.sleep(0.016)
print("ticks", n, "final", rig.s)
