"""Compose the three companion-page screenshots into one figure labelled (a), (b), (c)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

src, out = Path(sys.argv[1]), Path(sys.argv[2])
a = Image.open(src / "4.webp").convert("RGB")   # (a) Part 0: wrong energy can look right
b = Image.open(src / "5.webp").convert("RGB")   # (b) logical explorer, mutant M5
c = Image.open(src / "6.webp").convert("RGB")   # (c) energy updates with runtime properties

BG = (252, 250, 248)
INK = (29, 31, 35)
LAB, GAP, GUT, PAD = 72, 48, 64, 24          # label band, vertical gap, column gutter, outer padding
font = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 54)

# Right column: (b) at native size. Left column: (a) over (c), scaled to the same total height.
right_h = LAB + b.height
ratio_sum = a.height / a.width + c.height / c.width
left_w = round((right_h - 2 * LAB - GAP) / ratio_sum)
a2 = a.resize((left_w, round(left_w * a.height / a.width)), Image.LANCZOS)
c2 = c.resize((left_w, round(left_w * c.height / c.width)), Image.LANCZOS)

W = PAD + left_w + GUT + b.width + PAD
H = PAD + max(right_h, 2 * LAB + GAP + a2.height + c2.height) + PAD
fig = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(fig)

def place(img, x, y, label):
    draw.text((x + 6, y + 6), label, font=font, fill=INK)
    fig.paste(img, (x, y + LAB))
    return y + LAB + img.height

y = place(a2, PAD, PAD, "(a)")
place(c2, PAD, y + GAP, "(c)")
place(b, PAD + left_w + GUT, PAD, "(b)")

out.parent.mkdir(parents=True, exist_ok=True)
fig.save(out.with_suffix(".png"), optimize=True)
fig.save(out.with_suffix(".pdf"), resolution=300)
print(fig.size, "left column width", left_w)
