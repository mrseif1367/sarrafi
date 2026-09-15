# -*- coding: utf-8 -*-
"""ابزارهای کمکی: تقویم شمسی (جلالی) و فرمت اعداد فارسی

الگوریتم تبدیل تاریخ بر اساس الگوریتم استاندارد jalaali (نزدیک به jalaali-js).
"""

import datetime

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _div(a, b):
    """تقسیم صحیح به سمت صفر (مطابق JS: ~~(a/b))"""
    a, b = int(a), int(b)
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _mod(a, b):
    """باقی‌مانده با علامت مقسوم‌علیه (مطابق JS)"""
    a, b = int(a), int(b)
    return a - _div(a, b) * b


# ---------------------------------------------------------------------------
# تبدیل میلادی -> جلالی
# ---------------------------------------------------------------------------
def _g2d(gy, gm, gd):
    d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) \
        + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d


def _d2g(jdn):
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd


def _jal_cal(jy):
    breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
              1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]
    bl = len(breaks)
    gy = jy + 621
    leap_j = -14
    jp = breaks[0]
    jump = 0
    if jy < jp or jy >= breaks[bl - 1]:
        # خارج از بازه: تخمین ساده
        return {"leap": 0, "gy": gy, "march": 20}
    for i in range(1, bl):
        jm = breaks[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j = leap_j + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return {"leap": leap, "gy": gy, "march": march}


def _d2j(jdn):
    gy, gm, gd = _d2g(jdn)
    jy = gy - 621
    r = _jal_cal(jy)
    jdn1f = _g2d(gy, 3, r["march"])
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if r["leap"] == 1:
            k += 1
    jm = 7 + _div(k, 30)
    jd = _mod(k, 30) + 1
    return jy, jm, jd


def gregorian_to_jalali(gy, gm, gd):
    return _d2j(_g2d(gy, gm, gd))


def jalali_to_gregorian(jy, jm, jd):
    # جستجوی معکوس دقیق روی محدوده‌ی ۳۶۶ روزه
    gy0 = jy + 621
    for delta in range(-1, 3):
        gy = gy0 + delta
        for m in range(1, 13):
            for d in range(1, 32):
                try:
                    if (m == 2 and d > 29):
                        continue
                    yy, mm, dd = gregorian_to_jalali(gy, m, d)
                    if (yy, mm, dd) == (jy, jm, jd):
                        return gy, m, d
                except Exception:
                    continue
    return jy + 621, jm, jd


def is_leap_jalali(jy):
    # در الگوریتم jalaali، مقدار leap==0 یعنی سال کبیسه
    return _jal_cal(jy)["leap"] == 0


# ---------------------------------------------------------------------------
# API راحت
# ---------------------------------------------------------------------------
def _to_date(v):
    if v is None:
        return datetime.date.today()
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        return datetime.datetime.strptime(v[:10], "%Y-%m-%d").date()
    return v


def fa_date(gregorian_date=None):
    d = _to_date(gregorian_date)
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def fa_year(gregorian_date=None):
    d = _to_date(gregorian_date)
    jy, _, _ = gregorian_to_jalali(d.year, d.month, d.day)
    return jy


def fa_month_name(jm):
    names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    return names[jm - 1] if 1 <= jm <= 12 else ""


def fa_digits(s):
    return str(s).translate(_FA_DIGITS)


def today_fa():
    return fa_date(datetime.date.today())


def now_fa():
    n = datetime.datetime.now()
    return fa_date(n.date()) + " — " + n.strftime("%H:%M")
