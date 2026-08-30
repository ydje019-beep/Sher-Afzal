#!/usr/bin/env python3
"""
prepare_image.py — Normalize a real archival image for the documentary renderer.
Resizes/pads to target canvas (default 1920x1080 with blurred fill), applies the
style-bible treatment: bw | sepia | color (color = legacy/today scenes only), soft vignette.

Usage:
  python3 prepare_image.py input.jpg output.jpg [--treat sepia|bw|color] [--w 1920] [--h 1080]
"""
import argparse
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def treat(img, mode):
    if mode == "bw":
        img = ImageOps.grayscale(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.12)
    elif mode == "sepia":
        g = ImageOps.grayscale(img)
        g = ImageEnhance.Contrast(g).enhance(1.08)
        sep = Image.merge("RGB", (
            g.point(lambda p: min(255, int(p * 1.07 + 14))),
            g.point(lambda p: min(255, int(p * 0.93 + 8))),
            g.point(lambda p: int(p * 0.74)),
        ))
        img = sep
    else:  # color
        img = ImageEnhance.Color(img).enhance(1.08)
        img = ImageEnhance.Contrast(img).enhance(1.05)
    return img


def vignette(img, strength=0.35):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) // 6))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, black, mask.point(lambda p: int(255 - (255 - p) * strength)))


def fit_canvas(img, W, H):
    """Fit image inside WxH; fill background with blurred, darkened version (no bars)."""
    bg = ImageOps.fit(img, (W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    fg = img.copy()
    fg.thumbnail((W, H), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--treat", default="sepia", choices=["sepia", "bw", "color"])
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--no-vignette", action="store_true")
    a = ap.parse_args()

    img = Image.open(a.inp).convert("RGB")
    # upscale small archival images gently so zoompan has pixels to work with
    if img.width < a.w:
        r = a.w / img.width
        img = img.resize((a.w, int(img.height * r)), Image.LANCZOS)
    img = treat(img, a.treat)
    img = fit_canvas(img, a.w, a.h)
    if not a.no_vignette:
        img = vignette(img)
    img.save(a.out, quality=92)
    print(f"OK {a.out} {img.size}")


if __name__ == "__main__":
    main()
