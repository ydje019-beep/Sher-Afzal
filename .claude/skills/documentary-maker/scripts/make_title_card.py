#!/usr/bin/env python3
"""
make_title_card.py — Typographic cards in the reference style (NOT AI imagery).
Types:
  chapter : small-caps "CHAPTER N" + big serif title, white on black
  stat    : huge serif number/phrase + small sub-line, white on black
  hook    : like stat but slightly warmer tone
  map     : parchment card with place label + red pin + optional route line text

Usage:
  python3 make_title_card.py chapter out.jpg --title "The Valley Before the Money" --sub "CHAPTER ONE"
  python3 make_title_card.py stat out.jpg --title "EIGHTY ROOMS" --sub "one summer house"
  python3 make_title_card.py map out.jpg --title "LENOX" --sub "Massachusetts — 3 hours by rail from Manhattan"
"""
import argparse
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
SERIF_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
]


def font(size, bold=True):
    for p in SERIF_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def center_text(d, y, text, f, fill, tracking=0):
    if tracking:
        text = (" " * 1).join(list(text)) if tracking >= 2 else text
    bbox = d.textbbox((0, 0), text, font=f)
    d.text(((W - (bbox[2] - bbox[0])) / 2, y), text, font=f, fill=fill)
    return bbox[3] - bbox[1]


def base_black():
    img = Image.new("RGB", (W, H), (8, 8, 8))
    # subtle vignette-glow center
    glow = Image.new("L", (W, H), 0)
    dg = ImageDraw.Draw(glow)
    dg.ellipse([W*0.2, H*0.15, W*0.8, H*0.85], fill=26)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    img = Image.composite(Image.new("RGB", (W, H), (22, 20, 18)), img, glow)
    return img


def card_chapter(title, sub):
    img = base_black(); d = ImageDraw.Draw(img)
    if sub:
        center_text(d, H*0.36, sub.upper(), font(44), (200, 190, 170), tracking=2)
    # wrap long titles
    words, lines, cur = title.split(), [], ""
    for w_ in words:
        if len(cur + " " + w_) > 26:
            lines.append(cur.strip()); cur = w_
        else:
            cur += " " + w_
    lines.append(cur.strip())
    y = H*0.46 - (len(lines)-1)*55
    for ln in lines:
        center_text(d, y, ln, font(96), (240, 236, 228)); y += 118
    d.line([(W/2-140, y+30), (W/2+140, y+30)], fill=(150, 140, 120), width=2)
    return img


def card_stat(title, sub, warm=False):
    img = base_black(); d = ImageDraw.Draw(img)
    col = (238, 226, 200) if warm else (242, 240, 235)
    size = 170 if len(title) <= 14 else (120 if len(title) <= 24 else 88)
    center_text(d, H*0.40, title, font(size), col)
    if sub:
        center_text(d, H*0.62, sub, font(46), (170, 162, 148))
    return img


def card_map(title, sub):
    img = Image.new("RGB", (W, H), (222, 208, 178))
    d = ImageDraw.Draw(img)
    # aged blotches
    for i, (x, y, r) in enumerate([(300, 250, 420), (1550, 800, 380), (900, 600, 500)]):
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).ellipse([x-r, y-r, x+r, y+r], fill=18)
        img = Image.composite(Image.new("RGB", (W, H), (205, 188, 152)), img, sh.filter(ImageFilter.GaussianBlur(120)))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, W-40, H-40], outline=(120, 100, 70), width=3)
    d.rectangle([52, 52, W-52, H-52], outline=(120, 100, 70), width=1)
    # dotted route to pin
    px, py = W*0.60, H*0.42
    sx, sy = W*0.22, H*0.78
    steps = 26
    for i in range(steps):
        t0, t1 = i/steps, (i+0.5)/steps
        d.line([(sx+(px-sx)*t0, sy+(py-sy)*t0), (sx+(px-sx)*t1, sy+(py-sy)*t1)],
               fill=(90, 70, 50), width=4)
    # red pin
    d.ellipse([px-16, py-16, px+16, py+16], fill=(165, 30, 25), outline=(90, 20, 15), width=3)
    d.ellipse([px-6, py-6, px+6, py+6], fill=(230, 220, 205))
    f = font(92)
    d.text((px+34, py-58), title.upper(), font=f, fill=(60, 45, 28))
    if sub:
        d.text((sx-40, sy+26), sub, font=font(40), fill=(95, 78, 55))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["chapter", "stat", "hook", "map"])
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--sub", default="")
    a = ap.parse_args()
    if a.kind == "chapter":
        img = card_chapter(a.title, a.sub)
    elif a.kind == "stat":
        img = card_stat(a.title, a.sub)
    elif a.kind == "hook":
        img = card_stat(a.title, a.sub, warm=True)
    else:
        img = card_map(a.title, a.sub)
    img.save(a.out, quality=94)
    print(f"OK {a.out}")


if __name__ == "__main__":
    main()
