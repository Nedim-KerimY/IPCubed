import re
from collections import Counter
from kipy import KiCad
s = KiCad(timeout_ms=120000).get_board().get_as_string()
# her (file ...) blogunu bul (veri blogu | | icerir, ic ice parantez yok)
blocks = re.findall(r'\(file\s*\(name\s+"([^"]+)"\)\s*\(type\s+(\w+)\)(.*?)\(checksum\s+"(\w+)"\)', s, flags=re.S)
print("file bloklari:", len(blocks))
has_data = [(n, len(re.sub(r'\s+', '', d)) if '(data' in d else 0, c) for n, t, d, c in blocks]
print("veri iceren:", sum(1 for x in has_data if x[1] > 0), "veri icermeyen:", sum(1 for x in has_data if x[1] == 0))
by_name = {}
for n, ln, c in has_data:
    by_name.setdefault(n, set()).add((c, ln > 0))
multi = {n: v for n, v in by_name.items() if len({c for c, _ in v}) > 1}
print("ayni ad farkli checksum:", len(multi), list(multi.items())[:3])
no_data_any = [n for n, v in by_name.items() if not any(h for _, h in v)]
print("hicbir blokta verisi olmayan ad:", no_data_any[:10])
# blok bicimi ornegi
n, t, d, c = next(b for b in blocks if '(data' in b[2])
print("ornek blok:", repr(f'(file (name "{n}") (type {t}){d[:60]}...{d[-40:]}(checksum "{c}")'))
# footprint -> embedded eslesmesi
fp = re.split(r'\n\t\(footprint ', s)
print("footprint sayisi:", len(fp) - 1)
f1 = fp[2]
print("fp uuid:", re.search(r'\(uuid "([^"]+)"\)', f1).group(1), "| embedded:", re.findall(r'\(name "([^"]+)"\)', f1)[:3])
print("model satiri:", re.findall(r'\(model "([^"]+)"', f1))
