import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ipcubed.model_loader import load_model, convert_step

d = Path(r"C:\Users\erdem\Desktop\antmicro-kintex7-ddr4-tester\lib\3d-models")
files = sorted(d.glob("*.step")) + sorted(d.glob("*.stp"))
print(len(files), "dosya;", sum(f.stat().st_size for f in files) / 1e6, "MB")
tot = 0; fails = []
rows = []
for f in files:
    t0 = time.perf_counter()
    try:
        m = convert_step(f, "normal")
    except Exception as e:
        fails.append((f.name, repr(e))); continue
    dt = time.perf_counter() - t0
    tot += dt
    if m is None:
        fails.append((f.name, "None")); continue
    lo, hi = m.bounds
    rows.append((dt, f.name, f.stat().st_size // 1024, len(m.positions), len(m.indices), (hi - lo).round(2).tolist(), len({tuple(c) for c in m.colors[:: max(1,len(m.colors)//200)]})))
rows.sort(reverse=True)
for r in rows[:10]:
    print(f"{r[0]*1000:8.0f} ms  {r[1]:38s} {r[2]:6d} KB  v={r[3]:7d} t={r[4]:7d} size={r[5]} ncol~{r[6]}")
print(f"toplam donusum: {tot:.1f} s, basarisiz: {len(fails)}")
for f in fails[:10]: print("FAIL", f)
# cache testi
t0 = time.perf_counter()
for f in files: load_model(f)
print(f"1. load_model (cache yaz): {time.perf_counter()-t0:.1f} s")
t0 = time.perf_counter()
for f in files: load_model(f)
print(f"2. load_model (cache oku): {(time.perf_counter()-t0)*1000:.0f} ms")
