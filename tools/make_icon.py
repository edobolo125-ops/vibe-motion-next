"""Buat assets/icon.ico (+ icon.png) tanpa berkas sumber.

Desain: kotak membulat gradasi hijau tua → teal, tiga klip putih di timeline, dan playhead kuning.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
C1, C2 = (6, 95, 70), (45, 212, 191)  # hijau tua → teal
YELLOW = (250, 204, 21, 255)


def _gradient(size: int) -> Image.Image:
    im = Image.new("RGB", (size, size))
    px = im.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3))
    return im


def draw(size: int = 512) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill=255)
    img.paste(_gradient(s), (0, 0), mask)
    d = ImageDraw.Draw(img)
    # tiga klip di timeline (y, x awal, x akhir)
    for y, x0, x1 in [(.26, .12, .62), (.44, .30, .80), (.62, .18, .70)]:
        d.rounded_rectangle((s * x0, s * y, s * x1, s * (y + .13)), radius=s * .031, fill=(255, 255, 255, 235))
    # playhead
    d.rounded_rectangle((s * .5 - s * .0137, s * .16, s * .5 + s * .0137, s * .84), radius=s * .0137, fill=YELLOW)
    d.polygon([(s * .5 - s * .059, s * .13), (s * .5 + s * .059, s * .13), (s * .5, s * .20)], fill=YELLOW)
    return img


def main(out_dir: Path | None = None) -> Path:
    out_dir = out_dir or Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = draw(512)
    base.save(out_dir / "icon.png")
    base.save(out_dir / "icon.ico", sizes=[(s, s) for s in SIZES])
    return out_dir / "icon.ico"


if __name__ == "__main__":
    print(main())
