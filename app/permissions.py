# -*- coding: utf-8 -*-
"""ماژول‌ها (فلگ امکانات) و ماتریس مجوز نقش‌ها — v0.7

- MODULES: فهرست قابلیت‌هایی که می‌توان برای هر حساب (و به‌صورت استثنا برای هر
  کاربر) روشن/خاموش کرد.
- ROLE_PERMS: پیش‌فرض سراسری مجوز هر نقش (fallback).
- role_permissions: جدول بازنویسی مجوزها در سطح هر حساب (قابل ویرایش در UI).
"""

# ---------------------------------------------------------------------------
# فهرست ماژول‌ها (قابلیت‌های قابل روشن/خاموش)
# ---------------------------------------------------------------------------
MODULES = [
    {"key": "fee_tax",       "name": "کارمزد و مالیات",
     "desc": "محاسبه‌ی کارمزد و مالیات روی فاکتورهای خرید/فروش ارز",
     "default": False, "icon": "💸"},
    {"key": "loans",         "name": "قرض و تسهیلات",
     "desc": "دریافت/اعطای قرض ریالی و ارزی با سررسید و یادآور",
     "default": True, "icon": "🤝"},
    {"key": "banknotes",     "name": "اسکناس (ثبت و پیگیری)",
     "desc": "ثبت تکی/گروهی اسکناس با سریال و تاریخچه‌ی مالکیت",
     "default": True, "icon": "💵"},
    {"key": "debts",         "name": "بدهی و طلب",
     "desc": "فهرست بدهکاران/بستانکاران و تسویه حساب",
     "default": True, "icon": "⚖️"},
    {"key": "expenses",      "name": "درآمد و هزینه",
     "desc": "ثبت هزینه‌ها و درآمدهای عملیاتی صرافی",
     "default": True, "icon": "💰"},
    {"key": "reports",       "name": "گزارش‌ها",
     "desc": "گزارش گردش صندوق، سود/زیان، ماهانه و خروجی PDF/اکسل",
     "default": True, "icon": "📄"},
    {"key": "charts",        "name": "نمودارها و تحلیل",
     "desc": "نمودار دایره‌ای/میله‌ای/مقایسه‌ای با تحلیل خودکار",
     "default": True, "icon": "📊"},
    {"key": "online_rates",  "name": "نرخ آنلاین",
     "desc": "دریافت لحظه‌ای نرخ از منابع اینترنتی و به‌روزرسانی خودکار",
     "default": True, "icon": "🌐"},
    {"key": "multi_cashbox", "name": "چند صندوق و زیرشاخه",
     "desc": "تعریف/نام‌گذاری صندوق‌های نقدی و بانکی با زیرشاخه‌ی ارزی",
     "default": True, "icon": "🏦"},
    {"key": "ocr",           "name": "تشخیص تصویری اسکناس",
     "desc": "تشخیص چند اسکناس از یک عکس + پیشنهاد سریال (OCR)",
     "default": True, "icon": "📷"},
    {"key": "invoices",      "name": "فاکتورها",
     "desc": "فهرست و چاپ فاکتورهای خرید/فروش",
     "default": True, "icon": "🧾"},
    {"key": "customers",     "name": "مشتریان و شرکت‌ها",
     "desc": "پروفایل کامل طرف حساب‌ها (مانده، فاکتور، اسکناس، قرض)",
     "default": True, "icon": "👥"},
]

MODULE_KEYS = [m["key"] for m in MODULES]


def module_name(key):
    for m in MODULES:
        if m["key"] == key:
            return m["name"]
    return key


# ---------------------------------------------------------------------------
# مجوزهای ریز (ماتریس سطح دسترسی)
# ---------------------------------------------------------------------------
PERMS = [
    {"key": "buy",             "name": "خرید ارز"},
    {"key": "sell",            "name": "فروش ارز"},
    {"key": "loan",            "name": "قرض و بازپرداخت"},
    {"key": "transfer",        "name": "انتقال بین صندوق"},
    {"key": "banknote",        "name": "ثبت اسکناس"},
    {"key": "party",           "name": "مدیریت طرف حساب"},
    {"key": "payment",         "name": "تسویه / پرداخت"},
    {"key": "expense",         "name": "ثبت هزینه"},
    {"key": "income",          "name": "ثبت درآمد"},
    {"key": "adjust",          "name": "اصلاح موجودی صندوق"},
    {"key": "void",            "name": "ابطال سند"},
    {"key": "delete",          "name": "حذف (نرم) و بازیابی رکوردها"},
    {"key": "rate",            "name": "مدیریت نرخ"},
    {"key": "report",          "name": "گزارش‌ها"},
    {"key": "cashbox_manage",  "name": "مدیریت صندوق‌ها (ساخت/ویرایش)"},
]

PERM_KEYS = [p["key"] for p in PERMS]

# نقش‌های قابل ویرایش در ماتریس (سوپرادمین همیشه «همه» است و قابل تغییر نیست)
EDITABLE_ROLES = ["admin", "cashier", "accountant", "operator"]

# ---------------------------------------------------------------------------
# پیش‌فرض سراسری مجوز هر نقش (fallback وقتی override وجود ندارد)
# ---------------------------------------------------------------------------
ROLE_PERMS = {
    "super_admin": {"all": True},
    "admin":       {"all": True},
    "cashier":     {"buy": True, "sell": True, "loan": True, "transfer": True,
                    "banknote": True, "party": True, "report": True,
                    "payment": True, "cashbox_manage": True},
    "accountant":  {"report": True, "expense": True, "income": True, "void": True,
                    "rate": True, "adjust": True, "cashbox_manage": True},
    "operator":    {"buy": True, "sell": True, "cashbox_manage": True},
}

ROLE_FA = {"super_admin": "سوپرادمین", "admin": "مدیر", "cashier": "صندوق‌دار",
           "accountant": "حسابدار", "operator": "اپراتور"}

# ---------------------------------------------------------------------------
# کدام endpoint سمت سرور به کدام ماژول وابسته است (اعمال اجباری)
# ---------------------------------------------------------------------------
MODULE_ENDPOINTS = {
    "loans":         ["/api/loan/receive", "/api/loan/give", "/api/loan/repay"],
    "banknotes":     ["/api/banknote/save", "/api/banknote/bulk", "/api/banknote/photo"],
    "debts":         ["/api/payment"],
    "expenses":      ["/api/expense", "/api/income"],
    "reports":       ["/api/report/cashbox", "/api/report/profit", "/api/report/monthly",
                      "/api/report/party", "/api/report/pdf", "/api/export/csv",
                      "/api/export/xlsx"],
    "charts":        ["/api/report/charts"],
    "online_rates":  ["/api/rates/fetch"],
    "multi_cashbox": ["/api/cashbox/save"],
    "ocr":           ["/api/detect", "/api/detect/register"],
}


# ---------------------------------------------------------------------------
# خواندن فلگ‌ها از دیتابیس
# ---------------------------------------------------------------------------
def account_module_flags(conn, account_id):
    """فلگ‌های ماژول یک حساب (با اعمال پیش‌فرض‌ها)."""
    out = {m["key"]: bool(m["default"]) for m in MODULES}
    try:
        rows = conn.execute(
            "SELECT module, enabled FROM account_modules WHERE account_id=?",
            (account_id,)).fetchall()
        for r in rows:
            out[r["module"]] = bool(r["enabled"])
    except Exception:
        pass
    return out


def user_module_overrides(conn, user_id):
    """فلگ‌های استثنای یک کاربر (فقط مواردی که صریحاً ذخیره شده‌اند)."""
    try:
        rows = conn.execute(
            "SELECT module, enabled FROM user_modules WHERE user_id=?",
            (user_id,)).fetchall()
        return {r["module"]: bool(r["enabled"]) for r in rows}
    except Exception:
        return {}


def effective_modules(conn, user):
    """فلگ‌های مؤثر برای کاربر = فلگ حساب + استثناهای کاربر (اولویت با کاربر)."""
    acct = user.get("account_id") or 0
    flags = account_module_flags(conn, acct)
    if user.get("id"):
        flags.update(user_module_overrides(conn, user["id"]))
    return flags


def module_on(conn, user, key):
    return bool(effective_modules(conn, user).get(key, True))


def save_account_modules(conn, account_id, data):
    for m in MODULES:
        k = m["key"]
        if k in data:
            conn.execute(
                """INSERT INTO account_modules(account_id, module, enabled)
                   VALUES (?,?,?)
                   ON CONFLICT(account_id, module) DO UPDATE SET enabled=excluded.enabled""",
                (account_id, k, 1 if data[k] else 0))


def save_user_modules(conn, user_id, data):
    for m in MODULES:
        k = m["key"]
        if k in data:
            conn.execute(
                """INSERT INTO user_modules(user_id, module, enabled)
                   VALUES (?,?,?)
                   ON CONFLICT(user_id, module) DO UPDATE SET enabled=excluded.enabled""",
                (user_id, k, 1 if data[k] else 0))


# ---------------------------------------------------------------------------
# ماتریس مجوزها
# ---------------------------------------------------------------------------
def role_perm_overrides(conn, account_id, role):
    try:
        rows = conn.execute(
            "SELECT perm, allowed FROM role_permissions WHERE account_id=? AND role=?",
            (account_id, role)).fetchall()
        return {r["perm"]: bool(r["allowed"]) for r in rows}
    except Exception:
        return {}


def role_perm_set(conn, account_id, role):
    """مجموعه‌ی مجوزهای مؤثر یک نقش در یک حساب (پیش‌فرض + بازنویسی)."""
    default = ROLE_PERMS.get(role, {})
    overrides = role_perm_overrides(conn, account_id, role)
    if default.get("all"):
        base = set(PERM_KEYS) | {"all"}
    else:
        base = {k for k, v in default.items() if v}
    if overrides:
        # وقتی override ذخیره شده، «همه» را به مجوزهای مشخص بسط می‌دهیم
        if "all" not in base:
            base = base
        for k, allowed in overrides.items():
            if allowed:
                base.add(k)
            else:
                base.discard(k)
                if k == "all":
                    base.discard("all")
    return base


def effective_perm_set(conn, user):
    role = user.get("role")
    if role == "super_admin":
        return {"all"}
    acct = user.get("account_id") or 0
    return role_perm_set(conn, acct, role)


def save_role_permissions(conn, account_id, matrix):
    """ذخیره‌ی ماتریس مجوز نقش‌ها برای یک حساب."""
    conn.execute("DELETE FROM role_permissions WHERE account_id=? AND role IN (?,?,?,?)",
                 (account_id, *EDITABLE_ROLES))
    for role in EDITABLE_ROLES:
        perms = matrix.get(role) or {}
        for pk in PERM_KEYS:
            allowed = bool(perms.get(pk))
            conn.execute(
                """INSERT INTO role_permissions(account_id, role, perm, allowed)
                   VALUES (?,?,?,?)
                   ON CONFLICT(account_id, role, perm) DO UPDATE SET allowed=excluded.allowed""",
                (account_id, role, pk, 1 if allowed else 0))


def role_matrix(conn, account_id):
    """ماتریس مجوزها برای نمایش در UI (فقط نقش‌های قابل ویرایش)."""
    out = {}
    for role in EDITABLE_ROLES:
        pset = role_perm_set(conn, account_id, role)
        out[role] = {pk: (pk in pset) for pk in PERM_KEYS}
    return out
