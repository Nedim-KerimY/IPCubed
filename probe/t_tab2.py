from PIL import Image
from collections import Counter
img = Image.open(r"C:\Users\erdem\AppData\Local\Temp\strip.png").convert("RGB")
img = img.resize((img.width // 4, img.height // 4), Image.NEAREST)
w, h = img.size
print(w, h)
bg = Counter(img.crop((w // 2, 3, w - 16, h - 3)).getdata()).most_common(1)[0][0]
print("bg", bg)
for x in range(168, 215, 3):
    col = [img.getpixel((x, y)) for y in range(2, h - 2)]
    print(x, sorted(set(col))[:4], max(sum(abs(p[i] - bg[i]) for i in range(3)) for p in col))
