import sys, time, queue
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
if __name__ == "__main__":
    from ipcubed.sync_proc import SyncProcess
    t = time.perf_counter()
    s = SyncProcess(); s.start(); s.visible = True; s.check_now.set(); s.request_full.set()
    msg = None
    while time.perf_counter() - t < 15:
        try:
            msg = s.out.get(timeout=0.5); break
        except queue.Empty:
            pass
    print("ilk mesaj", round(time.perf_counter() - t, 1), "s:", msg[0] if msg else None, (str(msg[1])[:60] if msg else ""))
    print("canli:", s.is_alive()); s.stop(); print("durdu:", not s.is_alive())
