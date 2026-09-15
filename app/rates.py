# -*- coding: utf-8 -*-
"""
دریافت نرخ ارز به‌صورت آنلاین از منابع مختلف

منابع:
    1. navasan    → https://api.navasan.tech/latest/?api_key=KEY  (نرخ بازار ایران، تومانی؛ نیاز به کلید)
    2. er-api     → https://open.er-api.com/v6/latest/USD  (رایگان، بدون کلید، شامل IRR)
    3. tgju       → https://api.tgju.org/v1/data/sana/json (نرخ رسمی/سنا ایران، تومانی)
    4. frankfurter → https://api.frankfurter.app/latest?from=USD (ECB؛ بدون IRR)

خروجی همه‌ی منابع یکسان است:
    { provider, fetched_at, rates: {CODE: rial_per_unit}, source_name }

نرخ‌ها به «ریال به ازای ۱ واحد ارز» تبدیل می‌شوند و در exchange_rates (per account)
ذخیره می‌گردند. منبع پیش‌فرض «نوسان» است و در صورت نبودِ کلید/سهمیه، به‌صورت
زنجیره‌ای به er-api و tgju بازمی‌گردد (fallback).
"""

import datetime
import json
import os
import urllib.parse
import urllib.request

TIMEOUT = 12

# ارزهایی که در سیستم داریم و می‌خواهیم نرخ بگیریم (غیر از IRR)
TARGET_CODES = ["USD", "EUR", "AED", "TRY", "GBP", "IQD", "CHF", "CNY", "RUB"]

# منبع پیش‌فرض و زنجیره‌ی بازگشت (اولین موفقیت استفاده می‌شود)
DEFAULT_PROVIDER = "navasan"
FALLBACK_CHAIN = ["navasan", "er-api", "tgju"]

PROVIDERS = {
    "navasan": {"name": "نوسان (navasan.tech)", "url": "https://api.navasan.tech/latest/",
                "has_irr": True, "needs_key": True, "desc": "نرخ لحظه‌ای بازار ایران (تومان)"},
    "er-api": {"name": "ER-API (open.er-api.com)", "url": "https://open.er-api.com/v6/latest/USD",
               "has_irr": True, "desc": "نرخ جهانی، رایگان و بدون کلید"},
    "tgju": {"name": "سنا — طلا و سکه (tgju.org)", "url": "https://api.tgju.org/v1/data/sana/json",
             "has_irr": True, "desc": "نرخ رسمی ایران (تومان)"},
    "frankfurter": {"name": "Frankfurter (ECB)", "url": "https://api.frankfurter.app/latest?from=USD",
                    "has_irr": False, "desc": "نرخ بانک مرکزی اروپا (بدون ریال)"},
}

# نگاشت نام‌های سنا به کد ارز
TGJU_NAME_MAP = {
    "دلار": "USD", "یورو": "EUR", "پوند": "GBP", "لیر ترکیه": "TRY",
    "درهم امارات": "AED", "دینار عراق": "IQD", "فرانک سوئیس": "CHF",
    "یوان چین": "CNY", "روبل روسیه": "RUB",
}

# نگاشت نمادهای نوسان به کد ارز — ترتیب مهم است: برای هر ارز اولین نمادِ موجود
# انتخاب می‌شود (مثلاً usd بر usd_sell اولویت دارد).
NAVASAN_MAP = [
    ("usd", "USD"), ("usd_sell", "USD"), ("usd_buy", "USD"),
    ("eur", "EUR"), ("gbp", "GBP"), ("aed", "AED"),
    ("try", "TRY"), ("chf", "CHF"), ("cny", "CNY"), ("rub", "RUB"),
]


def _get_raw(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sarrafi"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore").strip()
        except Exception:
            pass
        raise ValueError(f"HTTP {e.code}: {body[:120] or e.reason}")
    except urllib.error.URLError as e:
        raise ValueError(f"عدم دسترسی به منبع نرخ: {e.reason}")


def _get(url):
    raw = _get_raw(url)
    try:
        return json.loads(raw)
    except Exception:
        raise ValueError("پاسخ نامعتبر از منبع نرخ: " + raw[:100])


def fetch_er_api():
    data = _get(PROVIDERS["er-api"]["url"])
    if data.get("result") != "success" or not data.get("rates"):
        raise ValueError("پاسخ نامعتبر از ER-API")
    rates = data["rates"]
    irr = float(rates.get("IRR", 0))
    if irr <= 0:
        raise ValueError("نرخ ریال در پاسخ ER-API موجود نیست")
    out = {"IRR": 1}
    for code in TARGET_CODES:
        v = rates.get(code)
        if v and float(v) > 0:
            out[code] = int(round(irr / float(v)))
    return out


def fetch_tgju():
    data = _get(PROVIDERS["tgju"]["url"])
    if not isinstance(data, dict):
        # tgju گاهی ساختار را عوض می‌کند یا خالی برمی‌گرداند
        raise ValueError("منبع سنا در حال حاضر پاسخی ندارد — منبع دیگری را انتخاب کنید")
    items = (data.get("data") or {}).get("sana") or {}
    arr = items.get("data") if isinstance(items, dict) else items
    out = {"IRR": 1}
    if not isinstance(arr, list) or not arr:
        raise ValueError("منبع سنا پاسخی ندارد — منبع دیگری را انتخاب کنید")
    for it in arr:
        name = (it.get("name") or "").strip()
        code = TGJU_NAME_MAP.get(name)
        if not code:
            continue
        price = float(it.get("price") or 0)
        if price > 0:
            out[code] = int(round(price * 10))  # تومان → ریال
    if "USD" not in out:
        raise ValueError("نرخ دلار در پاسخ سنا یافت نشد")
    return out


def fetch_frankfurter():
    data = _get(PROVIDERS["frankfurter"]["url"])
    rates = data.get("rates") or {}
    out = {}
    for code in TARGET_CODES:
        v = rates.get(code)
        if v and float(v) > 0:
            out[code] = float(v)  # نسبت به دلار (بدون ریال)
    if not out:
        raise ValueError("پاسخ نامعتبر از Frankfurter")
    return out


def fetch_navasan(api_key=None):
    """دریافت نرخ از نوسان — واحد تومان → تبدیل به ریال (×۱۰)."""
    key = (api_key or "").strip() or os.environ.get("SARRAFI_NAVASAN_KEY", "").strip()
    if not key:
        raise ValueError("کلید API نوسان تنظیم نشده — آن را در «تنظیمات → نرخ آنلاین» وارد کنید "
                         "(دریافت رایگان از ربات تلگرام @navasan_contact_bot)")
    url = PROVIDERS["navasan"]["url"] + "?api_key=" + urllib.parse.quote(key)
    try:
        raw = _get_raw(url)
    except ValueError as e:
        raise ValueError("اتصال به نوسان ناموفق (کلید نادرست است؟): " + str(e))
    try:
        data = json.loads(raw)
    except Exception:
        raise ValueError("پاسخ نامعتبر از نوسان: " + raw[:100])
    if not isinstance(data, dict):
        raise ValueError("پاسخ نامعتبر از نوسان")
    out = {"IRR": 1}
    got = 0
    for sym, code in NAVASAN_MAP:
        if code in out:
            continue  # اولین نمادِ موجود برای هر ارز کافی است
        item = data.get(sym)
        if not isinstance(item, dict):
            continue
        v = item.get("value")
        try:
            v = float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[code] = int(round(v * 10))  # تومان → ریال
            got += 1
    if not got:
        raise ValueError("نرخ معتبری از نوسان دریافت نشد")
    return out


FETCHERS = {"er-api": fetch_er_api, "tgju": fetch_tgju, "frankfurter": fetch_frankfurter,
            "navasan": fetch_navasan}


def fetch(provider=None, api_key=None):
    """دریافت نرخ از یک منبع؛ خروجی با کلید rates: {code: rial_per_unit}"""
    provider = provider or DEFAULT_PROVIDER
    if provider not in FETCHERS:
        raise ValueError("منبع نرخ نامعتبر است")
    fn = FETCHERS[provider]
    meta = PROVIDERS[provider]
    if provider == "navasan":
        rates = fn(api_key=api_key)
    else:
        rates = fn()
    if not meta.get("has_irr"):
        # منبع بدون ریال: فقط نرخ متقابل ارزها (برای ریال قابل استفاده نیست)
        return {"provider": provider, "source_name": meta["name"],
                "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "rates": {}, "fx": rates, "note": "این منبع نرخ ریال ندارد"}
    return {"provider": provider, "source_name": meta["name"],
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "rates": rates}


def fetch_with_fallback(preferred=None, api_key=None):
    """منابع را به ترتیب امتحان می‌کند تا اولین منبعِ دارای نرخ موفق شود.

    خروجی علاوه بر فیلدهای fetch، شامل:
        fallback : True اگر منبعِ ترجیحی شکست خورد و منبع پشتیبان استفاده شد
        tried    : فهرست خطاهای منابعی که شکست خوردند
    """
    chain = []
    if preferred and preferred in FETCHERS:
        chain.append(preferred)
    for p in FALLBACK_CHAIN:
        if p not in chain:
            chain.append(p)
    tried = []
    for p in chain:
        try:
            res = fetch(p, api_key=api_key)
            if res.get("rates"):
                res["fallback"] = bool(preferred) and p != preferred
                if tried:
                    res["tried"] = tried
                return res
            tried.append(p + ": " + (res.get("note") or "بدون نرخ"))
        except Exception as e:
            tried.append(p + ": " + str(e))
    raise ValueError("هیچ منبع نرخی در دسترس نیست — " + " | ".join(tried))


def apply_to_db(conn, result, account_id=None):
    """ذخیره‌ی نرخ‌های دریافتی در exchange_rates برای امروز (حساب جاری)"""
    from . import context
    acct = context.get_account() if account_id is None else int(account_id)
    today = datetime.date.today().strftime("%Y-%m-%d")
    updated = []
    for code, rial in (result.get("rates") or {}).items():
        if code == "IRR":
            continue
        cur = conn.execute("SELECT id FROM currencies WHERE code=?", (code,)).fetchone()
        if not cur:
            continue
        conn.execute(
            """INSERT INTO exchange_rates(account_id,currency_id,rate,rate_date,rate_type,source)
               VALUES (?,?,?,?,'market',?)
               ON CONFLICT(account_id,currency_id,rate_date,rate_type)
               DO UPDATE SET rate=excluded.rate, source=excluded.source""",
            (acct, cur["id"], int(rial), today, result["provider"]))
        updated.append({"code": code, "rate": int(rial)})
    conn.commit()
    return updated


def last_fetch_meta(conn, account_id=None):
    from . import context
    acct = context.get_account() if account_id is None else int(account_id)
    rows = conn.execute(
        """SELECT source, MAX(created_at) t FROM exchange_rates
           WHERE account_id=? AND rate_date=(SELECT MAX(rate_date) FROM exchange_rates WHERE account_id=?)
           GROUP BY source ORDER BY t DESC LIMIT 1""", (acct, acct)).fetchone()
    return dict(rows) if rows else None
