# -*- coding: utf-8 -*-
"""
تولید آیکون‌های PWA از روی طراحی لوگو (بدون نیاز به فایل خارجی)
خروجی: app/static/img/icons/icon-192.png ، icon-512.png ، icon-maskable-512.png
"""

import os
import math
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "app", "static", "img", "icons")


def _vgrad(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    return img


def _rounded(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_icon(size, maskable=False):
    # پس‌زمینه گرادیانی
    bg = _vgrad(size, size, (56, 189, 248), (99, 102, 241))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(bg, (0, 0))
    d = ImageDraw.Draw(img)

    # سکه (داخل ناحیه امن در حالت maskable)
    pad = size * 0.18 if maskable else size * 0.12
    cx, cy = size / 2, size / 2
    r = (size - 2 * pad) / 2

    # بدنه سکه
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(251, 191, 36), outline=(180, 83, 9), width=max(2, size // 128))
    # حلقه داخلی
    d.ellipse([cx - r * 0.72, cy - r * 0.72, cx + r * 0.72, cy + r * 0.72],
              outline=(180, 83, 9), width=max(2, size // 128))

    # چهار پیکان (تبادل)
    dark = (15, 23, 42)
    aw = max(4, size // 32)          # ضخامت پیکان
    ln = r * 0.9                     # طول بازو
    gap = r * 0.18                   # فاصله از مرکز

    for sx, sy, ex, ey in [
        (-1, 0, 1, 0), (1, 0, -1, 0), (0, -1, 0, 1), (0, 1, 0, -1)
    ]:
        x1 = cx + sx * gap
        y1 = cy + sy * gap
        x2 = cx + sx * ln
        y2 = cy + sy * ln
        d.line([x1, y1, x2, y2], fill=dark, width=aw)
        # سر پیکان
        if sx != 0:
            tip = x2
            base = x2 - sx * r * 0.22
            d.polygon([(tip, y2), (base, y2 - aw), (base, y2 + aw)], fill=dark)
        else:
            tip = y2
            base = y2 - sy * r * 0.22
            d.polygon([(x2, tip), (x2 - aw, base), (x2 + aw, base)], fill=dark)

    # گردکردن گوشه‌ها
    img = Image.composite(img, Image.new("RGBA", (size, size), (0, 0, 0, 0)),
                          _rounded(size, int(size * 0.22)))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    draw_icon(192).save(os.path.join(OUT, "icon-192.png"))
    draw_icon(512).save(os.path.join(OUT, "icon-512.png"))
    draw_icon(512, maskable=True).save(os.path.join(OUT, "icon-maskable-512.png"))
    draw_icon(180).save(os.path.join(ROOT, "app", "static", "img", "apple-touch-icon.png"))
    print("icons generated in", OUT)


if __name__ == "__main__":
    main()
