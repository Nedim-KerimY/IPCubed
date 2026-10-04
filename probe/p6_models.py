from collections import Counter
from kipy import KiCad
from ipcubed.paths import resolve_model_path
from ipcubed.kicad_source import _footprint_data
from pathlib import Path

b = KiCad(timeout_ms=60000).get_board()
print("board:", b.name, "| project:", b.document.project.path)
proj = Path(b.document.project.path)
fps = b.get_footprints()
print("footprint:", len(fps))
c = Counter()
miss = Counter()
nomodel = 0
for f in fps:
    ms = list(f.definition.models)
    if not ms:
        nomodel += 1
    for m in ms:
        raw = m.filename
        scheme = raw.split("://")[0] + "://" if "://" in raw else ("${...}" if raw.startswith("${") else "yol")
        ok = resolve_model_path(raw, proj) is not None
        c[(scheme, ok)] += 1
        if not ok:
            miss[raw] += 1
print("modelsiz footprint:", nomodel)
print("(sema, cozuldu) sayilari:", dict(c))
print("cozulemeyen ornekler:")
for k, v in miss.most_common(8):
    print("  ", v, repr(k))
# gomulu dosya var mi?
f0 = next((f for f in fps if list(f.definition.models)), None)
if f0:
    d = f0.definition
    print("definition attrs:", [a for a in dir(d) if not a.startswith("_")])
    print("proto fields:", [x.name for x in d.proto.DESCRIPTOR.fields] if hasattr(d, "proto") else None)
    m = list(d.models)[0]
    print("model proto:", str(m.proto)[:300].replace("\n", " "))
