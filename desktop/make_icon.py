"""Draw the app icon (desktop/icon.png, 1024 px): a five-petal bloom on parchment."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024
OUT = Path(__file__).with_name("icon.png")


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 72
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=200, fill=(250, 248, 244, 255))
    petals = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    p = ImageDraw.Draw(petals)
    cx, cy, r, w, h = S / 2, S / 2 + 10, 150, 150, 230
    for k in range(5):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        petal = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(petal).ellipse([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=(224, 120, 47, 215))
        petal = petal.rotate(-math.degrees(a) - 90, center=(x, y), resample=Image.BICUBIC)
        petals = Image.alpha_composite(petals, petal)
    img = Image.alpha_composite(img, petals)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - 92, cy - 92, cx + 92, cy + 92], fill=(185, 81, 22, 255))
    d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(250, 248, 244, 235))
    img.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
