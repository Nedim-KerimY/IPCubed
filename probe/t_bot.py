import faulthandler, sys, runpy
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
if __name__ == "__main__":
    faulthandler.dump_traceback_later(60, exit=True)
    sys.argv = ["ipcubed", "--screenshot", sys.argv[1], "--width", "1100", "--height", "700", "--view", "bottom"]
    runpy.run_module("ipcubed", run_name="__main__")
