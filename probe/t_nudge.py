import time
from kipy import KiCad
from kipy.geometry import Vector2

k = KiCad(timeout_ms=60000)
b = k.get_board()
fp = next(f for f in b.get_footprints() if f.reference_field.text.value == "U10")
old = Vector2.from_xy(fp.position.x, fp.position.y)
print("U10 at", old)
commit = b.begin_commit()
fp.position = Vector2.from_xy(old.x + 5_000_000, old.y)
b.update_items(fp)
b.push_commit(commit, "nudge test")
print("moved +5mm; bekleniyor")
time.sleep(4)
commit = b.begin_commit()
fp.position = old
b.update_items(fp)
b.push_commit(commit, "nudge back")
print("geri alindi")
