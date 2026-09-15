# -*- coding: utf-8 -*-
"""
OCR سریال اسکناس — فقط به عنوان «پیشنهاد»؛ تأیید نهایی همیشه با کاربر است.

موتورها (به ترتیب اولویت):
    1. Tesseract محلی (اگر نصب باشد) — از طریق pytesseract
    2. سرویس آنلاین (ocr.space) — اگر کلید در تنظیمات باشد

اگر هیچ موتوری در دسترس نباشد، `available()` مقدار False برمی‌گرداند
و رابط کاربری ورود دستی را پیشنهاد می‌دهد.
"""

import io
import os
import re
import shutil

SERIAL_RE = re.compile(r"[A-Z0-9]{5,}")

# مسیرهای رایج نصب Tesseract در ویندوز (در صورتی که در PATH نباشد)
_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
]


def _tesseract_binary():
    """یافتن مسیر اجرایی tesseract: متغیر محیطی → PATH → مسیرهای رایج ویندوز"""
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd and os.path.exists(cmd):
        return cmd
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for p in _WINDOWS_TESSERACT_PATHS:
            if os.path.exists(p):
                return p
    return None


def available():
    return _tesseract_binary() is not None


def _tesseract_available():
    try:
        import pytesseract  # noqa
        return _tesseract_binary() is not None
    except Exception:
        return False


def _preprocess(image_bytes):
    """تبدیل عکس به تصویر خاکستری با کنتراست بالا برای OCR بهتر"""
    from PIL import Image, ImageOps, ImageFilter
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    # بزرگ‌نمایی برای دقت بالاتر
    w, h = img.size
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img)
    return img


def read_serial(image_bytes, psm=None):
    """بازگشت لیست سریال‌های پیشنهادی از روی عکس"""
    if not _tesseract_available():
        return {"available": False, "suggestions": []}

    import pytesseract
    bin_path = _tesseract_binary()
    if bin_path:
        pytesseract.pytesseract.tesseract_cmd = bin_path
    img = _preprocess(image_bytes)
    candidates = []
    for mode in (psm or [7, 6, 11]):
        try:
            txt = pytesseract.image_to_string(
                img, config=(f"--psm {mode} -c tessedit_char_whitelist="
                             "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
        except Exception:
            continue
        for tok in SERIAL_RE.findall(txt.upper()):
            # حذف رشته‌های خیلی طولانی (نویز) و خیلی کوتاه
            if 5 <= len(tok) <= 16 and tok not in candidates:
                candidates.append(tok)
    return {"available": True, "suggestions": candidates[:5]}


def ocr_serial_from_upload_dir(path):
    if not os.path.isfile(path):
        return {"available": False, "suggestions": []}
    with open(path, "rb") as f:
        return read_serial(f.read())
