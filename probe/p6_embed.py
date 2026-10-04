import re, time, base64
from kipy import KiCad

b = KiCad(timeout_ms=120000).get_board()
t = time.perf_counter()
s = b.get_as_string()
print(f"get_as_string: {time.perf_counter()-t:.2f}s, {len(s)/1e6:.1f} MB")
i = s.find("(embedded_files")
print("embedded_files at", i, "| count:", s.count("(embedded_files"))
print(s[i:i + 600].replace("\n", "\\n")[:600])
# yapi: (file (name "x") (type model) (data |...|) (checksum "..."))
files = re.findall(r'\(file\s*\(name\s+"([^"]+)"\)\s*\(type\s+(\w+)\)', s)
print("gomulu dosya:", len(files), files[:5])
m = re.search(r'\(data\s*\|([^|]*)\|', s)
if m:
    raw = re.sub(r"\s+", "", m.group(1))
    print("ilk data uzunlugu", len(raw), "bas:", raw[:12])
    try:
        import zstandard
        blob = base64.b64decode(raw)
        out = zstandard.ZstdDecompressor().decompressobj().decompress(blob)
        print("zstd ok:", len(out), "byte; bas:", out[:60])
    except Exception as e:
        print("coz hata", repr(e))
