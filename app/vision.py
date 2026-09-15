# -*- coding: utf-8 -*-
"""تشخیص تصویری اسکناس‌ها — کاملاً آفلاین (OpenCV + Tesseract).

قابلیت‌ها:
    - بررسی کیفیت عکس (رزولوشن / تاری / نور)
    - یافتن کادر چند اسکناس در یک عکس (کانتور چهارضلعی + تصحیح پرسپکتیو)
    - برش هر اسکناس
    - خواندن شماره سریال (الگوی هر ارز) با امتیاز اطمینان
    - خواندن ارزش اسکناس از رقم بزرگ گوشه

وابستگی‌های اختیاری: opencv-python، numpy، pytesseract، pillow.
اگر نصب نباشند، توابع خطای شفاف برمی‌گردانند.
"""

import io
import re

try:
    import cv2
    import numpy as np
    HAVE_CV = True
except Exception:
    HAVE_CV = False

try:
    from PIL import Image, ImageOps, ImageFilter
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

DEFAULT_FACES = {"USD": [1, 2, 5, 10, 20, 50, 100], "EUR": [5, 10, 20, 50, 100, 200, 500]}


def available():
    return HAVE_CV and HAVE_PIL


def _decode(data):
    """تصحیح جهت EXIF + تبدیل به RGB"""
    if not HAVE_PIL:
        raise RuntimeError("کتابخانه Pillow نصب نیست")
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


# ---------------------------------------------------------------------------
# کیفیت
# ---------------------------------------------------------------------------
def analyze_quality(data):
    """بررسی کیفیت عکس و برگرداندن پیشنهاد"""
    im = _decode(data)
    w, h = im.size
    arr = np.array(im)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if HAVE_CV else None
    sharpness = None
    if gray is not None:
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # درصد نقاط اشباع (سوخته) — نور زیاد
    sat_ratio = float((np.max(arr, axis=2) > 250).mean()) if HAVE_CV else 0.0
    issues, tips = [], []
    if w < 1600:
        issues.append("resolution")
        tips.append("عکس را با کیفیت بالاتر بگیرید (رزولوشن پایین است)")
    if sharpness is not None and sharpness < 100:
        issues.append("blur")
        tips.append("عکس کمی تار است — ثابت نگه دارید و دوباره بگیرید")
    elif sharpness is not None and sharpness < 500:
        tips.append("وضوح عکس متوسط است")
    if sat_ratio > 0.25:
        issues.append("glare")
        tips.append("نور زیاد یا بازتاب دارد — زاویه یا نور را تغییر دهید")
    return {"width": w, "height": h, "sharpness": round(sharpness, 1) if sharpness else None,
            "saturation_ratio": round(sat_ratio, 3), "ok": not issues,
            "issues": issues, "tips": tips}


# ---------------------------------------------------------------------------
# تشخیص کادر اسکناس‌ها
# ---------------------------------------------------------------------------
def detect(data):
    """یافتن کادر همه‌ی اسکناس‌ها در یک عکس.

    خروجی: {"rects": [{"quad": [[x,y]x4], "x":.., "y":.., "w":.., "h":..}], "quality": {...}}
    """
    if not HAVE_CV:
        raise RuntimeError("OpenCV نصب نیست — تشخیص تصویری در دسترس نیست")
    im = _decode(data)
    w, h = im.size
    img = np.array(im)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    rects = []

    # چند آستانه‌ی Canny تا در شرایط نوری مختلف جواب دهد
    for lo, hi in ((30, 100), (50, 150), (80, 200)):
        edges = cv2.Canny(blur, lo, hi)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_area = w * h
        for c in cnts:
            area = cv2.contourArea(c)
            if area < img_area * 0.012 or area > img_area * 0.85:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) != 4:
                continue
            quad = _order_quad(np.array(approx).reshape(4, 2))
            if quad is None:
                continue
            x, y, ww, hh = cv2.boundingRect(quad)
            ratio = max(ww, hh) / max(min(ww, hh), 1)
            if not (0.5 <= ratio <= 3.6):
                continue
            rects.append({"quad": [[int(p[0]), int(p[1])] for p in quad],
                          "x": int(x), "y": int(y), "w": int(ww), "h": int(hh)})

    # حذف کادرهای تکراری/تداخلی + کادرهایی که در واقع چند اسکناس را دربرگرفته‌اند
    rects = _dedupe(rects)
    rects = _drop_containers(rects)
    # مرتب‌سازی از بالا به پایین و چپ به راست
    rects.sort(key=lambda r: (r["y"] // 60, r["x"]))
    for i, r in enumerate(rects):
        r["index"] = i
    return {"rects": rects, "count": len(rects), "quality": analyze_quality(data)}


def _drop_containers(rects):
    """حذف کادری که مرکزِ کادر کوچک‌تری را در خود دارد (چند اسکناس را پوشانده)"""
    keep = []
    for r in rects:
        is_container = False
        for o in rects:
            if o is r:
                continue
            ox, oy = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
            rx2, ry2 = r["x"] + r["w"], r["y"] + r["h"]
            if (r["x"] <= ox <= rx2 and r["y"] <= oy <= ry2
                    and r["w"] * r["h"] > 1.4 * o["w"] * o["h"]):
                is_container = True
                break
        if not is_container:
            keep.append(r)
    return keep


def _order_quad(pts):
    """مرتب‌سازی ۴ گوشه: بالا-چپ، بالا-راست، پایین-راست، پایین-چپ"""
    pts = sorted(pts, key=lambda p: (p[1], p[0]))
    top = pts[:2]
    bot = pts[2:]
    tl = top[0] if top[0][0] < top[1][0] else top[1]
    tr = top[1] if top[0][0] < top[1][0] else top[0]
    bl = bot[0] if bot[0][0] < bot[1][0] else bot[1]
    br = bot[1] if bot[0][0] < bot[1][0] else bot[0]
    # حداقل اندازه‌ی معقول
    w = max(abs(tr[0] - tl[0]), abs(br[0] - bl[0]))
    h = max(abs(bl[1] - tl[1]), abs(br[1] - tr[1]))
    if w < 30 or h < 30:
        return None
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _dedupe(rects):
    """حذف کادرهایی که تقریباً یکی هستند (از آستانه‌های مختلف Canny)"""
    out = []
    for r in rects:
        dup = False
        for o in out:
            cx1, cy1 = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
            cx2, cy2 = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
            if abs(cx1 - cx2) < 20 and abs(cy1 - cy2) < 20:
                # کادر بزرگتر (کامل‌تر) را نگه دار
                if r["w"] * r["h"] > o["w"] * o["h"]:
                    out.remove(o)
                    out.append(r)
                dup = True
                break
        if not dup:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# برش پرسپکتیو
# ---------------------------------------------------------------------------
def crop_rect(data, quad, pad_ratio=0.0):
    """برش پرسپکتیو یک ناحیه (quad = ۴ نقطه به پیکسل) → bytes (JPEG)"""
    if not HAVE_CV:
        raise RuntimeError("OpenCV نصب نیست")
    im = _decode(data)
    img = np.array(im)
    h, w = img.shape[:2]
    quad = np.array(quad, dtype=np.float32)
    # pad
    if pad_ratio:
        cx, cy = quad[:, 0].mean(), quad[:, 1].mean()
        quad = quad + (quad - np.array([cx, cy], dtype=np.float32)) * pad_ratio
    tl, tr, br, bl = quad
    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if width < 20 or height < 20:
        return None
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                   dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    warped = cv2.warpPerspective(img, M, (width, height))
    ok, buf = cv2.imencode(".jpg", warped, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return buf.tobytes() if ok else None


# ---------------------------------------------------------------------------
# خواندن سریال
# ---------------------------------------------------------------------------
def read_serial(crop_data, pattern=None):
    """خواندن سریال از تصویر برش‌خورده + امتیاز اطمینان.

    سریال معمولاً متنی «کوچک» است (برخلاف رقم بزرگ ارزش در گوشه‌ها)، بنابراین:
      - کل تصویر با psm 6 و فیلتر ارتفاع کلمه (۱.۵٪ تا ۱۱٪ ارتفاع) پردازش می‌شود
      - سه نوار افقی هم‌پوشان هم جداگانه OCR می‌شوند
    کاندیدهایی که با الگوی ارز مطابق باشند اولویت دارند.
    """
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        return {"serial": "", "confidence": 0.0, "note": "pytesseract نصب نیست"}
    try:
        im = _decode(crop_data)
    except Exception:
        return {"serial": "", "confidence": 0.0}
    gray = np.array(im.convert("L"))
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    H, W = gray.shape
    variants = [("raw", gray)]
    try:
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("otsu", otsu))
    except Exception:
        pass

    WL = ("-c tessedit_char_whitelist="
          "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
    found = {}

    def add(txt):
        for cand in re.findall(r"[A-Za-z0-9]{6,14}", (txt or "").replace("\n", " ")):
            found[cand.upper()] = found.get(cand.upper(), 0) + 1

    # ۱) کل تصویر با فیلتر ارتفاع کلمه
    lo_h, hi_h = int(H * 0.015), int(H * 0.11)
    for _tag, img in variants:
        try:
            d = pytesseract.image_to_data(img, output_type=Output.DICT,
                                          config=f"--psm 6 {WL}")
        except Exception:
            continue
        lines = {}
        n = len(d["text"])
        for i in range(n):
            txt = (d["text"][i] or "").strip()
            if not txt or not re.fullmatch(r"[A-Za-z0-9]+", txt):
                continue
            hgt = int(d["height"][i])
            if not (lo_h <= hgt <= hi_h):
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            lines.setdefault(key, []).append((int(d["left"][i]), txt))
        for _k, words in lines.items():
            words.sort(key=lambda w: w[0])
            add("".join(w[1] for w in words))

    # ۲) سه نوار افقی هم‌پوشان
    bands = [(0, 0.45), (0.25, 0.75), (0.55, 1.0)]
    for _tag, img in variants:
        for b0, b1 in bands:
            band = img[int(H * b0):int(H * b1), :]
            if band.size == 0:
                continue
            for psm in ("--psm 6", "--psm 7"):
                try:
                    add(pytesseract.image_to_string(band, config=f"{psm} {WL}"))
                except Exception:
                    pass

    serial, conf = "", 0.0
    pat = None
    if pattern:
        try:
            pat = re.compile(pattern)
        except re.error:
            pat = None
    matches = [c for c in found if pat and pat.fullmatch(c)]
    if matches:
        serial = max(matches, key=lambda c: (found[c], len(c)))
        conf = 0.9 + 0.05 * min(found[serial], 2)
        return {"serial": serial, "confidence": round(conf, 2)}
    alnum = [c for c in found if re.search(r"[A-Za-z]", c) and re.search(r"\d", c)]
    if alnum:
        serial = max(alnum, key=lambda c: (found[c], len(c)))
        conf = 0.5 + 0.1 * min(found[serial], 3)
        return {"serial": serial, "confidence": round(conf, 2)}
    if found:
        serial = max(found, key=lambda c: (found[c], len(c)))
        conf = 0.35
        return {"serial": serial, "confidence": conf}
    return {"serial": "", "confidence": 0.0}


# ---------------------------------------------------------------------------
# خواندن ارزش (رقم بزرگ گوشه)
# ---------------------------------------------------------------------------
def read_value(crop_data, faces):
    """خواندن ارزش از رقم بزرگ گوشه‌ها + امتیاز اطمینان"""
    try:
        import pytesseract
    except Exception:
        return {"value": None, "confidence": 0.0}
    try:
        im = _decode(crop_data)
    except Exception:
        return {"value": None, "confidence": 0.0}
    w, h = im.size
    arr = np.array(im.convert("L"))
    # رقم بزرگ ارزش حدود ۱۵-۲۰٪ ارتفاع اسکناس است؛ برای OCR بهتر آن را
    # به ارتفاع ~۴۰۰ پیکسل کوچک می‌کنیم تا رقم ~۶۰px شود.
    target_h = 400
    scale = (target_h / h) if h > target_h else 1.0
    if scale != 1.0:
        arr = cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    H2, W2 = arr.shape
    zones = [
        ("c0", arr[0:int(H2 * 0.25), 0:int(W2 * 0.50)]),
        ("c1", arr[0:int(H2 * 0.25), int(W2 * 0.50):]),
        ("c2", arr[int(H2 * 0.75):, 0:int(W2 * 0.50)]),
        ("c3", arr[int(H2 * 0.75):, int(W2 * 0.50):]),
        ("full", arr),
    ]
    found = {}
    for _name, z in zones:
        if z.size == 0:
            continue
        for psm in ("--psm 11", "--psm 6"):
            try:
                t = pytesseract.image_to_string(
                    z, config=f"{psm} -c tessedit_char_whitelist=0123456789")
            except Exception:
                t = ""
            for d in re.findall(r"\d{1,7}", t):
                v = int(d)
                if v in faces:
                    found[v] = found.get(v, 0) + 1
    if not found:
        return {"value": None, "confidence": 0.0}
    # ارزش واقعی = طولانی‌ترین رقم منطبق (چون رقم‌های بریده‌شده کوتاه‌ترند)
    value = max(found, key=lambda v: (len(str(v)), found[v]))
    conf = min(0.55 + 0.13 * (found[value] - 1), 0.99)
    return {"value": value, "confidence": round(conf, 2)}


# ---------------------------------------------------------------------------
# پردازش کامل یک عکس
# ---------------------------------------------------------------------------
def process_photo(data, pattern=None, faces=None):
    """تشخیص + برش + سریال + ارزش برای همه‌ی اسکناس‌های یک عکس"""
    det = detect(data)
    faces = faces or DEFAULT_FACES.get("USD", [1, 2, 5, 10, 20, 50, 100])
    out = []
    for r in det["rects"]:
        crop = crop_rect(data, r["quad"])
        serial = read_serial(crop, pattern) if crop else {"serial": "", "confidence": 0.0}
        value = read_value(crop, faces) if crop else {"value": None, "confidence": 0.0}
        out.append({**r, "serial": serial["serial"], "serial_confidence": serial["confidence"],
                    "value": value["value"], "value_confidence": value["confidence"]})
    return {"quality": det["quality"], "items": out, "count": len(out)}
