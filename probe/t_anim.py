import sys, time
sys.path.insert(0, r"C:\Users\erdem\AppData\Roaming\kicad\viewer3d")
from PIL import ImageGrab, Image
from ipcubed.ctl import send

def burst(n=7, gap=0.07):
    frames = []
    for _ in range(n):
        frames.append(ImageGrab.grab(bbox=(43, 120, 1654, 970), all_screens=True).resize((400, 212)))
        time.sleep(gap)
    return frames

send("show"); time.sleep(2.5)
send("hide")
frames = burst()
sheet = Image.new("RGB", (400 * 4, 212 * 2))
for i, f in enumerate(frames):
    sheet.paste(f, ((i % 4) * 400, (i // 4) * 212))
sheet.save(r"C:\Users\erdem\AppData\Local\Temp\anim_hide.png")
time.sleep(1.5)
send("show")
frames = burst()
sheet = Image.new("RGB", (400 * 4, 212 * 2))
for i, f in enumerate(frames):
    sheet.paste(f, ((i % 4) * 400, (i // 4) * 212))
sheet.save(r"C:\Users\erdem\AppData\Local\Temp\anim_show.png")
print("ok")
