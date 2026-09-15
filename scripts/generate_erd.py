# -*- coding: utf-8 -*-
"""
تولید نمودار ERD سیستم صرافی به صورت PNG (با متن فارسی) — نسخه‌ی چندمشترکی (schema v5)
خروجی: docs/images/erd.png

اجرا:
    python scripts/generate_erd.py
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAVE_BIDI = True
except Exception:
    HAVE_BIDI = False

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_TTF = "/tmp/Vazirmatn-Regular.ttf"
FONT_TTF_BOLD = "/tmp/Vazirmatn-Bold.ttf"

# تلاش برای یافتن فونت TTF (برای matplotlib فونت woff2 کار نمی‌کند)
for _cand in ["/usr/share/fonts/truetype/vazirmatn/Vazirmatn-Regular.ttf",
              os.path.join(ROOT, "app", "static", "fonts", "Vazirmatn-Regular.ttf")]:
    if os.path.exists(_cand) and not os.path.exists(FONT_TTF):
        FONT_TTF = _cand


def fa(text):
    if HAVE_BIDI:
        return get_display(arabic_reshaper.reshape(text))
    return text


def make():
    plt.rcParams["figure.facecolor"] = "#0b1220"
    fig, ax = plt.subplots(figsize=(24, 17.5), dpi=110)
    ax.set_facecolor("#0b1220")
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 17.5)
    ax.axis("off")

    fp = font_manager.FontProperties(fname=FONT_TTF) if os.path.exists(FONT_TTF) else None
    fpb = font_manager.FontProperties(fname=FONT_TTF_BOLD) if os.path.exists(FONT_TTF_BOLD) else fp

    def prop(bold=False, size=11):
        f = fpb if bold else fp
        return font_manager.FontProperties(fname=f.get_file(), size=size) if f else None

    ENT = {}  # name -> (cx, cy, w, h)

    def box(name, fa_title, en_title, fields, x, y, w=3.6, h=2.4, accent="#38bdf8"):
        cx, cy = x + w / 2, y + h / 2
        ENT[name] = (cx, cy, w, h)
        rect = FancyBboxPatch((x, y), w, h,
                              boxstyle="round,pad=0.06,rounding_size=0.18",
                              linewidth=1.2, edgecolor=accent, facecolor="#111c33", zorder=2)
        ax.add_patch(rect)
        ax.text(cx, y + h - 0.46, fa(fa_title), ha="center", va="center",
                fontproperties=prop(True, 11.5), color="#ffffff", zorder=3)
        ax.text(cx, y + h - 0.86, en_title, ha="center", va="center",
                fontproperties=prop(False, 7.8), color="#8ea0bd", zorder=3)
        yy = y + h - 1.28
        for f in fields:
            ax.text(cx, yy, fa(f), ha="center", va="center",
                    fontproperties=prop(False, 8.6), color="#aab8d0", zorder=3)
            yy -= 0.38
        ax.plot([x + 0.15, x + w - 0.15], [y + h - 1.06, y + h - 1.06],
                color="#1e2c4a", lw=0.8, zorder=3)

    def link(a, b, label="1..N", lw=1.0, color="#3b4c6e", style="-"):
        xa, ya, wa, ha = ENT[a]
        xb, yb, wb, hb = ENT[b]
        p1 = (xa, ya + ha / 2)
        p2 = (xb, yb + hb / 2)
        arr = FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=12,
                              linewidth=lw, color=color, linestyle=style, zorder=1)
        ax.add_patch(arr)
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my + 0.2, fa(label), ha="center", va="bottom",
                fontproperties=prop(False, 7.8), color="#6b7ea0", zorder=4,
                bbox=dict(facecolor="#0b1220", edgecolor="none", pad=0.4))

    TEN = "#34d399"   # رنگ چندمشترکی
    REF = "#38bdf8"
    DOC = "#8a5cff"
    CORE = "#fbbf24"

    # ================== ردیف ۱: چندمشترکی و سیستم ==================
    box("accounts", "مشترک (حساب)", "accounts", ["id", "name", "plan", "status"],
        0.4, 13.15, h=2.7, accent=TEN)
    box("users", "کاربران", "users", ["account_id", "username", "role", "is_owner"],
        4.9, 13.15, h=2.7, accent=TEN)
    box("sessions", "نشست‌ها", "sessions", ["user_id", "token", "impersonated_by"],
        9.4, 13.15, h=2.7, accent=TEN)
    box("settings", "تنظیمات حساب", "settings", ["account_id", "key", "value"],
        13.9, 13.15, h=2.7, accent=TEN)
    box("audit_log", "لاگ کاربران", "audit_log", ["account_id", "user_id", "action", "entity"],
        18.4, 13.15, h=2.7, accent=TEN)

    # ================== ردیف ۲: مرجع و داده پایه ==================
    box("currencies", "ارزها", "currencies", ["code", "name", "decimals", "unit_ratio"],
        0.4, 10.0, h=2.7, accent=REF)
    box("exchange_rates", "نرخ ارز", "exchange_rates", ["account_id", "currency_id", "rate", "source"],
        4.9, 10.0, h=2.7, accent=REF)
    box("parties", "طرف حساب", "parties", ["account_id", "type", "full_name", "national_id"],
        9.4, 10.0, h=2.7, accent=REF)
    box("cashboxes", "صندوق‌ها", "cashboxes", ["account_id", "name", "kind", "parent_id", "currency_id"],
        13.9, 10.0, h=2.7, accent=REF)
    box("cashbox_opening", "موجودی اولیه", "cashbox_opening", ["account_id", "cashbox_id", "currency_id", "amount"],
        18.4, 10.0, h=2.7, accent=REF)

    # ================== ردیف ۳: اسناد و پرداخت ==================
    box("journal", "سند عملیات", "journal", ["account_id", "jtype", "status", "created_by"],
        0.3, 6.85, w=3.15, h=2.7, accent=DOC)
    box("invoices", "فاکتور", "invoices", ["account_id", "party_id", "invoice_no", "status"],
        3.85, 6.85, w=3.15, h=2.7, accent=DOC)
    box("loans", "قرض", "loans", ["account_id", "party_id", "direction", "amount"],
        7.4, 6.85, w=3.15, h=2.7, accent=DOC)
    box("payments", "پرداخت / تسویه", "payments", ["account_id", "party_id", "direction", "amount"],
        10.95, 6.85, w=3.15, h=2.7, accent=DOC)
    box("payment_allocations", "تخصیص پرداخت", "payment_allocations", ["payment_id", "invoice_id", "amount"],
        14.5, 6.85, w=3.15, h=2.7, accent=DOC)
    box("expense_categories", "دسته هزینه/درآمد", "expense_categories", ["name", "kind"],
        18.05, 6.85, w=3.15, h=2.7, accent=DOC)

    # ================== ردیف ۴: هسته، هزینه/درآمد و اسکناس ==================
    box("transactions", "تراکنش‌ها (هسته مالی)", "transactions",
        ["account_id", "journal_id", "direction", "amount", "rate"],
        0.15, 3.4, w=3.6, h=3.0, accent=CORE)
    box("expenses", "هزینه‌ها", "expenses", ["account_id", "category_id", "amount", "rial_value"],
        4.15, 3.4, w=3.15, h=2.7, accent=CORE)
    box("incomes", "درآمدها", "incomes", ["account_id", "amount", "rial_value"],
        7.7, 3.4, w=3.15, h=2.7, accent=CORE)
    box("banknotes", "اسکناس‌ها", "banknotes", ["account_id", "currency_id", "serial", "status"],
        11.25, 3.4, w=3.15, h=2.7, accent=CORE)
    box("banknote_images", "عکس اسکناس", "banknote_images", ["banknote_id", "file_path"],
        14.8, 3.4, w=3.15, h=2.7, accent=CORE)
    box("banknote_movements", "تاریخچه اسکناس", "banknote_movements",
        ["account_id", "banknote_id", "movement_type", "party_id"],
        18.35, 3.4, w=3.15, h=2.7, accent=CORE)

    # ================== ردیف ۵: امنیت (v0.4) و ماژول‌ها/نقش‌ها (v0.7) ==================
    box("login_attempts", "تلاش‌های ورود", "login_attempts",
        ["username", "attempts", "locked_until"],
        0.4, 0.55, w=3.6, h=2.2, accent=TEN)
    box("password_resets", "بازنشانی رمز", "password_resets",
        ["username", "code", "expires_at", "used"],
        4.9, 0.55, w=3.6, h=2.2, accent=TEN)
    box("role_permissions", "مجوز نقش‌ها", "role_permissions",
        ["role", "perm", "allowed"],
        9.4, 0.55, w=3.6, h=2.2, accent=TEN)
    box("account_modules", "ماژول‌های حساب", "account_modules",
        ["account_id", "module_key", "enabled"],
        13.9, 0.55, w=3.6, h=2.2, accent=TEN)
    box("user_modules", "ماژول‌های کاربر", "user_modules",
        ["account_id", "user_id", "module_key", "enabled"],
        18.4, 0.55, w=3.6, h=2.2, accent=TEN)

    # ================== روابط ==================
    # چندمشترکی (account_id) — خط‌چین سبز
    for t in ("users", "settings", "audit_log", "parties", "cashboxes", "journal",
              "invoices", "loans", "payments", "exchange_rates", "banknotes",
              "expenses", "incomes", "transactions", "account_modules", "user_modules"):
        link("accounts", t, "", lw=0.7, color="#2a7a5c", style="--")
    link("users", "sessions", "1..N", color=TEN)
    link("users", "audit_log", "1..N", color=TEN)
    link("users", "user_modules", "1..N", color=TEN)
    link("users", "role_permissions", "role", color=TEN)

    # مرجع
    link("currencies", "exchange_rates", "1..N")
    link("currencies", "transactions", "1..N", color=CORE)
    link("currencies", "invoices", "1..N")
    link("currencies", "banknotes", "1..N")
    link("parties", "invoices", "1..N", color=REF)
    link("parties", "loans", "1..N")
    link("parties", "payments", "1..N")
    link("parties", "transactions", "1..N", color=CORE)
    link("parties", "banknote_movements", "1..N")
    link("cashboxes", "transactions", "1..N", color=CORE)
    link("cashboxes", "banknotes", "1..N")
    link("cashboxes", "cashbox_opening", "1..N")
    link("expense_categories", "expenses", "1..N", color=DOC)
    link("payments", "payment_allocations", "1..N", color=DOC)
    link("invoices", "payment_allocations", "1..N", color=DOC)

    # اسناد → هسته
    link("journal", "transactions", "1..N", color=CORE)
    link("journal", "invoices", "1..1")
    link("journal", "loans", "1..1")
    link("journal", "payments", "1..1")
    link("journal", "expenses", "1..1", color=CORE)
    link("journal", "incomes", "1..1", color=CORE)
    link("banknotes", "banknote_movements", "1..N")
    link("banknotes", "banknote_images", "1..N")

    # عنوان
    ax.text(12, 17.05, fa("نمودار ERD — سیستم مدیریت صرافی (چندمشترکی)"),
            ha="center", va="center", fontproperties=prop(True, 17), color="#ffffff")
    ax.text(12, 16.3, "Exchange & Money-Changer Management System — Entity Relationship Diagram (schema v5)",
            ha="center", va="center", fontproperties=prop(False, 9.5), color="#8ea0bd")

    # راهنمای پایین
    ax.text(10.0, 2.6, fa("خط‌چین سبز = ایزوله‌سازی داده بر اساس account_id (هر مشترک فقط داده‌ی خودش را می‌بیند)"),
            ha="left", va="center", fontproperties=prop(False, 9.5), color="#6b7ea0")
    ax.text(10.0, 1.9, fa("رنگ‌ها:  سبز = چندمشترکی/سیستم    آبی = مرجع    بنفش = اسناد    طلایی = هسته‌ی مالی و اسکناس"),
            ha="left", va="center", fontproperties=prop(False, 9.5), color="#6b7ea0")

    out = os.path.join(ROOT, "docs", "images", "erd.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=110, facecolor="#0b1220", bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print("ERD saved to", out)


if __name__ == "__main__":
    make()
