"""Synthetic frame helpers (Pillow-drawn placards, no real photos) shared by the
inspection demo and tests. Mirrors the generators used for the capture-gate tests."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 640, 480
LINES = ["HPD-5A", "35KV 600A", "SER 884213"]


def make_frame(font_size: int = 40, blur: float = 0.0) -> Image.Image:
    im = Image.new("L", (W, H), 120)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, W - 40, H - 40], fill=215)
    font, step = ImageFont.load_default(font_size), int(font_size * 1.4)
    y = H // 2 - int(step * 1.5)
    for line in LINES:
        d.text(((W - d.textlength(line, font=font)) / 2, y), line, font=font, fill=20)
        y += step
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def approach_sequence(n_good: int = 6) -> list[Image.Image]:
    """Inspector walks up: far, far, blurred, then n_good steady frames."""
    return [make_frame(12), make_frame(16), make_frame(40, blur=3)] + [make_frame(40)] * n_good


def bad_sequence(n: int = 8) -> list[Image.Image]:
    """Never gets a usable frame: alternating far and blurred."""
    return [make_frame(12) if i % 2 == 0 else make_frame(40, blur=3) for i in range(n)]
