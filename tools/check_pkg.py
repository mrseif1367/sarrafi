# -*- coding: utf-8 -*-
"""بررسی نصب‌بودن پکیج‌ها.

- بدون آرگومان: خلاصه‌ی قابلیت‌های نصب‌شده را چاپ می‌کند.
- با یک آرگومان (نام ماژول): اگر قابل import باشد خروجی 0 وگرنه 1.
"""

import importlib.util
import sys

FEATURES = [
    ("خروجی PDF فارسی", "reportlab"),
    ("شکل‌دهی متن راست‌به‌چپ", "arabic_reshaper"),
    ("دوطرفه‌ی متن (Bidi)", "bidi"),
    ("OCR (تشخیص سریال)", "pytesseract"),
    ("تشخیص اسکناس (OpenCV)", "cv2"),
    ("پردازش تصویر", "PIL"),
    ("NumPy", "numpy"),
    ("PostgreSQL", "psycopg2"),
    ("خروجی اکسل", "openpyxl"),
]


def main():
    if len(sys.argv) < 2:
        for label, mod in FEATURES:
            ok = importlib.util.find_spec(mod) is not None
            if ok:
                print("  [OK]  " + label)
            else:
                print("  [--]  " + label + " - نصب نشده (اختیاری)")
        return 0
    mod = sys.argv[1]
    return 0 if importlib.util.find_spec(mod) is not None else 1


if __name__ == "__main__":
    sys.exit(main())
