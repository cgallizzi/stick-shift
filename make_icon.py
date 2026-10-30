"""Draws icon.ico: a gear-shift knob over an H shift pattern."""
from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=96, fill=(16, 124, 16, 255))  # Xbox-ish green
gate = (120, 200, 120, 255)
for x in (150, 256, 362):                                   # H-pattern gate
    d.line((x, 120, x, 392), fill=gate, width=22)
d.line((150, 256, 362, 256), fill=gate, width=22)
d.rectangle((240, 256, 272, 420), fill=(30, 30, 30, 255))   # shaft
d.ellipse((150, 110, 362, 322), fill=(20, 20, 20, 255))     # knob
d.ellipse((196, 146, 250, 180), fill=(70, 70, 70, 255))     # shine
img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save("logo.png")
