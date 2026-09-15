# -*- coding: utf-8 -*-
"""تست‌های تشخیص تصویری (vision) — آفلاین.

این تست‌ها نیازمند opencv-python، numpy، pillow و pytesseract هستند.
اگر وابستگی‌ها نصب نباشند، با پیام Skip رد می‌شوند.
"""
import os
import unittest

from app import vision

try:
    import cv2  # noqa
    import numpy  # noqa
    from PIL import Image  # noqa
    import pytesseract  # noqa
    HAVE_DEPS = True
except Exception:
    HAVE_DEPS = False

# تست‌هایی که واقعاً OCR می‌خوانند (سریال/ارزش) به موتور نصب‌شده‌ی سیستم
# نیاز دارند. نبودِ موتور نباید «شکست» گزارش شود، بلکه «رد شدن» است.
_NEED_OCR = HAVE_DEPS and vision.available() and __import__(
    "app.ocr", fromlist=["available"]).available()
needs_ocr = unittest.skipUnless(
    _NEED_OCR, "موتور OCR (tesseract) روی این سیستم نصب نیست")


def _make_synthetic(path, n=6, note_w=340, note_h=700, cols=3):
    """ساخت تصویر مصنوعی با n اسکناس سبز با سریال و رقم ارزش"""
    from PIL import Image, ImageDraw, ImageFont
    import random
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    if not os.path.exists(mono):
        mono = None
    rows = (n + cols - 1) // cols
    W = cols * (note_w + 40) + 60
    H = rows * (note_h + 60) + 50
    img = Image.new('RGB', (W, H), (240, 240, 240))
    d = ImageDraw.Draw(img)
    font_serial = ImageFont.truetype(mono, 34) if mono else ImageFont.load_default()
    font_big = ImageFont.truetype(mono, 78) if mono else ImageFont.load_default()
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    true = []
    for i in range(n):
        col, row = i % cols, i // cols
        x = 60 + col * (note_w + 40)
        y = 50 + row * (note_h + 60)
        d.rectangle([x, y, x + note_w, y + note_h], fill=(133, 187, 101),
                    outline=(60, 90, 50), width=4)
        d.rectangle([x + 14, y + 14, x + note_w - 14, y + note_h - 14],
                    outline=(60, 90, 50), width=3)
        for cx, cy in [(x + 28, y + 24), (x + note_w - 160, y + 24),
                       (x + 28, y + note_h - 96), (x + note_w - 160, y + note_h - 96)]:
            d.text((cx, cy), "100", fill=(20, 50, 20), font=font_big)
        serial = random.choice(letters) + "".join(random.choice("0123456789") for _ in range(8)) + random.choice(letters)
        d.text((x + 42, y + note_h // 2 - 14), serial, fill=(20, 50, 20), font=font_serial)
        true.append(serial)
    img.save(path, quality=95)
    return true


def _lev(a, b):
    """فاصله لون‌اشتاین — برای تلورانس خطاهای تک‌رقمی OCR"""
    if abs(len(a) - len(b)) > 1:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@unittest.skipUnless(HAVE_DEPS, "vision dependencies not installed")
class TestVision(unittest.TestCase):
    def setUp(self):
        self.path = "/tmp/test_notes.jpg"
        self.true = _make_synthetic(self.path, cols=4, note_w=400)
        self.data = open(self.path, "rb").read()

    def test_available(self):
        self.assertTrue(vision.available())

    def test_quality(self):
        q = vision.analyze_quality(self.data)
        self.assertTrue(q["ok"])
        self.assertGreater(q["sharpness"], 100)

    def test_detect_count(self):
        det = vision.detect(self.data)
        self.assertEqual(det["count"], len(self.true))

    @needs_ocr
    def test_serial_read(self):
        # OCR فقط «پیشنهاد» است؛ خطای تک‌رقمی مجاز است (فاصله لون‌اشتاین ≤ ۱)
        res = vision.process_photo(self.data, pattern=r"[A-Za-z]\d{8}[A-Za-z]?",
                                   faces=[1, 2, 5, 10, 20, 50, 100])
        self.assertEqual(res["count"], len(self.true))
        got = [it["serial"] for it in res["items"] if it["serial"]]
        unmatched = list(self.true)
        for s in got:
            best = min(unmatched, key=lambda t: _lev(s, t))
            self.assertLessEqual(_lev(s, best), 1, f"سریال {s} با هیچ سریال واقعی نزدیک نیست")
            unmatched.remove(best)
        # نباید سریالی از قلم افتاده باشد
        self.assertEqual(len(unmatched), len(self.true) - len(got))

    @needs_ocr
    def test_value_read(self):
        res = vision.process_photo(self.data, pattern=r"[A-Za-z]\d{8}[A-Za-z]?",
                                   faces=[1, 2, 5, 10, 20, 50, 100])
        values = [it["value"] for it in res["items"]]
        self.assertTrue(all(v == 100 for v in values), values)

    def test_crop_rect(self):
        det = vision.detect(self.data)
        crop = vision.crop_rect(self.data, det["rects"][0]["quad"])
        self.assertTrue(crop.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
