# -*- coding: utf-8 -*-
"""
تولید PDF از گزارش‌ها (فارسی، RTL) — با reportlab + فونت وزیرمتن (آفلاین)

وابستگی‌های اختیاری: reportlab ، arabic_reshaper ، python-bidi
اگر نصب نباشند، خروجی با خطای شفاف برمی‌گردد.
"""

import io
import os

from . import util, finance

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_REGULAR = os.path.join(HERE, "static", "fonts", "Vazirmatn-Regular.ttf")
FONT_BOLD = os.path.join(HERE, "static", "fonts", "Vazirmatn-Bold.ttf")

_registered = False


def _register_fonts():
    global _registered
    if _registered:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("Vazir", FONT_REGULAR))
    pdfmetrics.registerFont(TTFont("Vazir-Bold", FONT_BOLD))
    _registered = True


def _shape(text):
    """شکل‌دهی حروف فارسی + جهت راست‌به‌چپ"""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def _num(n, dec=0, ratio=1):
    v = (int(n or 0)) / (ratio or 1)
    return f"{v:,.{dec}f}"


def _wrap_cell(text, bold=False, color=None, align=1):
    """۱=راست، ۰=چپ، ۲=وسط"""
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    f = "Vazir-Bold" if bold else "Vazir"
    style = ParagraphStyle(
        "cell", fontName=f, fontSize=10, leading=15,
        alignment=align, textColor=color or "#0b1220")
    return Paragraph(_shape(text).replace("&", "&amp;"), style)


def generate(conn, frm, to, account_id=None):
    """گزارش جامع دوره‌ای به صورت PDF — خروجی bytes"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle)
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm
    except Exception as e:
        raise RuntimeError("کتابخانه reportlab نصب نیست — pip install reportlab") from e

    _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)

    accent = colors.HexColor("#0e7490")
    title_style = ParagraphStyle("t", fontName="Vazir-Bold", fontSize=16, leading=22,
                                 alignment=1, textColor="#0f172a")
    sub_style = ParagraphStyle("s", fontName="Vazir", fontSize=11, leading=16,
                               alignment=1, textColor="#475569")
    h_style = ParagraphStyle("h", fontName="Vazir-Bold", fontSize=12.5, leading=18,
                             alignment=1, textColor=accent, spaceBefore=10, spaceAfter=4)

    # نام حساب
    acct_name = ""
    row = conn.execute("SELECT name FROM accounts WHERE id=?", (int(account_id or 0),)).fetchone()
    if row:
        acct_name = row["name"]

    pl = finance.profit_loss(conn, frm, to, account_id)
    from_fa, to_fa = util.fa_date(frm), util.fa_date(to)

    story = []
    story.append(Paragraph(_shape("گزارش مالی صرافی"), title_style))
    story.append(Paragraph(_shape(acct_name or ""), sub_style))
    story.append(Paragraph(_shape(f"بازه: {from_fa} تا {to_fa}"), sub_style))
    story.append(Spacer(1, 4))

    # ---------- خلاصه سود و زیان ----------
    story.append(Paragraph(_shape("خلاصه سود و زیان"), h_style))
    pl_rows = [
        ["فروش", _num(pl["sell"])],
        ["خرید", _num(pl["buy"])],
        ["سایر درآمدها", _num(pl["income"])],
        ["هزینه‌ها", _num(pl["expense"])],
        ["سود / زیان خالص", _num(pl["net"])],
    ]
    t = Table([[ _wrap_cell(a, bold=(i == len(pl_rows) - 1)),
                 _wrap_cell(b, bold=(i == len(pl_rows) - 1))] for i, (a, b) in enumerate(pl_rows)],
              colWidths=[90 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)

    # ---------- سود محقق به تفکیک ارز (FIFO) ----------
    story.append(Paragraph(_shape("سود محقق به تفکیک ارز (FIFO)"), h_style))
    fifo = []
    for c in conn.execute("SELECT * FROM currencies WHERE code!='IRR' AND is_active=1 ORDER BY sort_order,id").fetchall():
        prof, sold = finance.realized_profit_fifo(conn, c["id"], frm, to, account_id)
        fifo.append([c["name"] + " (" + c["code"] + ")", _num(sold, c["decimals"], c["unit_ratio"]), _num(prof)])
    head = [_wrap_cell("ارز", True, "#ffffff"), _wrap_cell("فروخته‌شده", True, "#ffffff"),
            _wrap_cell("سود محقق (ریال)", True, "#ffffff")]
    body = [[_wrap_cell(a), _wrap_cell(b, align=0), _wrap_cell(c, align=0)] for a, b, c in fifo]
    t2 = Table([head] + body, colWidths=[60 * mm, 45 * mm, 45 * mm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t2)

    # ---------- تفکیک ماهانه ----------
    story.append(Paragraph(_shape("تفکیک ماهانه (شمسی)"), h_style))
    months = []
    for it in _monthly_rows(conn, frm, to, account_id):
        months.append([it["month_name"], _num(it["buy"]), _num(it["sell"]),
                       _num(it["income"]), _num(it["expense"]), _num(it["net"])])
    if months:
        head3 = [_wrap_cell("ماه", True, "#ffffff"), _wrap_cell("خرید", True, "#ffffff"),
                 _wrap_cell("فروش", True, "#ffffff"), _wrap_cell("درآمد", True, "#ffffff"),
                 _wrap_cell("هزینه", True, "#ffffff"), _wrap_cell("خالص", True, "#ffffff")]
        body3 = [[_wrap_cell(a), _wrap_cell(b), _wrap_cell(c), _wrap_cell(d), _wrap_cell(e), _wrap_cell(f)]
                 for a, b, c, d, e, f in months]
        t3 = Table([head3] + body3, colWidths=[40 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm])
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t3)

    # ---------- موجودی صندوق‌ها ----------
    story.append(Paragraph(_shape("موجودی صندوق‌ها"), h_style))
    cb_rows = []
    for cb in conn.execute("SELECT * FROM cashboxes WHERE account_id=? AND is_active=1 ORDER BY id",
                           (int(account_id or 0),)).fetchall():
        bal = finance.cashbox_balances(conn, cb["id"], account_id)
        for code, v in bal.items():
            if v:
                c = conn.execute("SELECT * FROM currencies WHERE code=?", (code,)).fetchone()
                cb_rows.append([cb["name"], c["name"] if c else code,
                                _num(v, c["decimals"] if c else 0, c["unit_ratio"] if c else 1)])
    if cb_rows:
        head4 = [_wrap_cell("صندوق", True, "#ffffff"), _wrap_cell("ارز", True, "#ffffff"),
                 _wrap_cell("موجودی", True, "#ffffff")]
        body4 = [[_wrap_cell(a), _wrap_cell(b), _wrap_cell(c, align=0)] for a, b, c in cb_rows]
        t4 = Table([head4] + body4, colWidths=[60 * mm, 45 * mm, 45 * mm])
        t4.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t4)

    doc.build(story)
    return buf.getvalue()


def _monthly_rows(conn, frm, to, account_id):
    months = {}
    start, end = frm + " 00:00:00", to + " 23:59:59"

    def add(created, field, val):
        if not created:
            return
        y, m, _ = util.gregorian_to_jalali(int(created[:4]), int(created[5:7]), int(created[8:10]))
        key = f"{y:04d}/{m:02d}"
        months.setdefault(key, {"month": key, "month_name": util.fa_month_name(m),
                                "income": 0, "expense": 0, "buy": 0, "sell": 0})
        months[key][field] += int(val or 0)

    for r in conn.execute("SELECT created_at, rial_value FROM incomes WHERE account_id=? AND created_at>=? AND created_at<=?",
                          (int(account_id or 0), start, end)).fetchall():
        add(r["created_at"], "income", r["rial_value"])
    for r in conn.execute("SELECT created_at, rial_value FROM expenses WHERE account_id=? AND created_at>=? AND created_at<=?",
                          (int(account_id or 0), start, end)).fetchall():
        add(r["created_at"], "expense", r["rial_value"])
    for r in conn.execute(
            """SELECT confirmed_at created_at, total_rial FROM invoices
               WHERE account_id=? AND invoice_type='buy' AND status IN ('confirmed','settled')
                 AND confirmed_at>=? AND confirmed_at<=?""", (int(account_id or 0), start, end)).fetchall():
        add(r["created_at"], "buy", r["total_rial"])
    for r in conn.execute(
            """SELECT confirmed_at created_at, total_rial FROM invoices
               WHERE account_id=? AND invoice_type='sell' AND status IN ('confirmed','settled')
                 AND confirmed_at>=? AND confirmed_at<=?""", (int(account_id or 0), start, end)).fetchall():
        add(r["created_at"], "sell", r["total_rial"])
    items = list(months.values())
    items.sort(key=lambda x: x["month"])
    for it in items:
        it["net"] = it["sell"] - it["buy"] + it["income"] - it["expense"]
    return items
