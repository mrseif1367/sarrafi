# -*- coding: utf-8 -*-
"""تست‌های خودکار هسته‌ی مالی و تقویم"""

import os
import sys
import datetime
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import schema, finance, util, seed, auth


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test.db")
    schema.init_db(p)
    conn = schema.get_connection(p)
    yield conn
    conn.close()


def _setup_currencies(conn):
    conn.execute("INSERT INTO currencies(code,name,symbol,decimals,unit_ratio,sort_order) "
                 "VALUES ('IRR','ریال','﷼',0,1,0), ('USD','دلار','$',2,100,1)")
    conn.commit()
    conn.execute("INSERT INTO cashboxes(name,code) VALUES ('صندوق اصلی','MAIN')")
    conn.commit()
    return (conn.execute("SELECT id FROM currencies WHERE code='IRR'").fetchone()["id"],
            conn.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"],
            conn.execute("SELECT id FROM cashboxes WHERE code='MAIN'").fetchone()["id"])


def _party(conn, name="علی"):
    conn.execute("INSERT INTO parties(type,full_name) VALUES ('customer',?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM parties WHERE full_name=?", (name,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# تقویم
# ---------------------------------------------------------------------------
def test_jalali_reference_dates():
    assert util.gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
    assert util.gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert util.gregorian_to_jalali(2026, 9, 8) == (1405, 6, 17)
    assert util.gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    # تبدیل معکوس
    assert util.jalali_to_gregorian(1405, 6, 17) == (2026, 9, 8)
    assert util.is_leap_jalali(1403) is True
    assert util.is_leap_jalali(1404) is False


def test_fa_date_format():
    d = util.fa_date(datetime.date(2026, 9, 8))
    assert d == "1405/06/17"


# ---------------------------------------------------------------------------
# خرید / فروش
# ---------------------------------------------------------------------------
def test_buy_cash_affects_cashboxes_only(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    finance.buy_currency(db, pid, usd, 100_000, 121_000, cb, cb, "تست", user_id=1)
    bal = finance.cashbox_balances(db, cb)
    assert bal["USD"] == 100_000      # ۱۰۰۰ دلار وارد شد
    assert bal["IRR"] == -121_000_000  # ۱۲۱ میلیون ریال خارج شد
    # طرف حساب نباید بدهی داشته باشد (نقدی)
    pb = finance.party_balances(db, pid)
    assert pb.get(usd, {}).get("amount", 0) == 0
    assert pb.get(irr, {}).get("amount", 0) == 0


def test_buy_later_creates_creditor(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    finance.buy_currency(db, pid, usd, 100_000, 121_000, cb, cb,
                         "نسیه", user_id=1, payment_method="later")
    bal = finance.cashbox_balances(db, cb)
    assert bal["USD"] == 100_000      # ارز وارد صندوق شد
    assert bal["IRR"] == 0            # ریالی از صندوق خارج نشد
    pb = finance.party_balances(db, pid)
    assert pb[usd]["amount"] == 100_000  # ما به او بدهکاریم (بستانکار)


def test_sell_later_creates_debtor(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    # اول موجودی بدهیم
    finance.adjust_cashbox(db, cb, usd, 100_000, 120_000, "موجودی اولیه", user_id=1)
    finance.sell_currency(db, pid, usd, 40_000, 125_000, cb, cb,
                          "نسیه", user_id=1, payment_method="later")
    bal = finance.cashbox_balances(db, cb)
    assert bal["USD"] == 60_000
    pb = finance.party_balances(db, pid)
    assert pb[usd]["amount"] == -40_000  # او به ما بدهکار است


def test_sell_insufficient_stock_raises(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    with pytest.raises(ValueError):
        finance.sell_currency(db, pid, usd, 100_000, 125_000, cb, cb, user_id=1)


# ---------------------------------------------------------------------------
# قرض
# ---------------------------------------------------------------------------
def test_loan_flow(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    finance.loan_receive(db, pid, usd, 500_000, 122_000, cb, "قرض", user_id=1)
    assert finance.cashbox_balances(db, cb)["USD"] == 500_000
    assert finance.party_balances(db, pid)[usd]["amount"] == 500_000  # ما بدهکاریم

    loan_id = db.execute("SELECT id FROM loans WHERE party_id=?", (pid,)).fetchone()["id"]
    finance.loan_repay(db, loan_id, usd, 200_000, 122_500, cb, "بازپرداخت", user_id=1)
    assert finance.cashbox_balances(db, cb)["USD"] == 300_000
    assert finance.party_balances(db, pid)[usd]["amount"] == 300_000


# ---------------------------------------------------------------------------
# FIFO
# ---------------------------------------------------------------------------
def test_fifo_profit(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    finance.buy_currency(db, pid, usd, 100_000, 120_000, cb, cb, "ل1", user_id=1)
    finance.buy_currency(db, pid, usd, 100_000, 122_000, cb, cb, "ل2", user_id=1)
    finance.sell_currency(db, pid, usd, 50_000, 125_000, cb, cb, "ف1", user_id=1)
    profit, sold = finance.realized_profit_fifo(db, usd)
    # (125000-120000)*500 = 2,500,000 ریال
    assert profit == 2_500_000
    assert int(sold) == 50_000


# ---------------------------------------------------------------------------
# لغو سند
# ---------------------------------------------------------------------------
def test_void_journal_reverts_balance(db):
    irr, usd, cb = _setup_currencies(db)
    pid = _party(db)
    r = finance.buy_currency(db, pid, usd, 100_000, 121_000, cb, cb, "تست", user_id=1)
    assert finance.cashbox_balances(db, cb)["USD"] == 100_000
    finance.void_journal(db, r["journal_id"], "اشتباه", user_id=1)
    assert finance.cashbox_balances(db, cb)["USD"] == 0


# ---------------------------------------------------------------------------
# داده‌ی نمونه
# ---------------------------------------------------------------------------
def test_seed_runs(tmp_path):
    p = str(tmp_path / "seed.db")
    seed.reset_and_seed(p)
    conn = schema.get_connection(p)
    try:
        assert conn.execute("SELECT COUNT(*) c FROM currencies").fetchone()["c"] == 7
        assert conn.execute("SELECT COUNT(*) c FROM parties").fetchone()["c"] == 9
        assert conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 2
        assert conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] > 0
        assert conn.execute("SELECT COUNT(*) c FROM banknotes").fetchone()["c"] == 6
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------
def test_password_hash_verify():
    h = auth.hash_password("secret123")
    assert h.startswith("pbkdf2$")
    assert auth.verify_password("secret123", h)
    assert not auth.verify_password("wrong", h)
    # سازگاری با هش قدیمی sha256
    import hashlib
    legacy = hashlib.sha256(b"oldpass").hexdigest()
    assert auth.verify_password("oldpass", legacy)


def test_session_expiry():
    expired = "2020-01-01 00:00:00"
    assert auth.is_expired(expired)
    future = "2099-01-01 00:00:00"
    assert not auth.is_expired(future)


# ---------------------------------------------------------------------------
# OCR (در صورت وجود tesseract)
# ---------------------------------------------------------------------------
def test_ocr_reads_serial(tmp_path):
    import shutil
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract نصب نیست")
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("L", (900, 200), 245)
    d = ImageDraw.Draw(img)
    font = None
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]:
        try:
            font = ImageFont.truetype(p, 72)
            break
        except Exception:
            pass
    d.text((80, 55), "AB12345678", fill=0, font=font)
    buf = tmp_path / "serial.png"
    img.save(str(buf))
    from app import ocr
    res = ocr.read_serial(open(str(buf), "rb").read())
    assert res["available"] is True
    assert "AB12345678" in res["suggestions"]


# ---------------------------------------------------------------------------
# یکپارچه‌سازی PostgreSQL (در صورت وجود SARRAFI_DATABASE_URL)
# ---------------------------------------------------------------------------
def test_postgres_parity():
    """در صورت وجود Postgres، seed و مانده‌ها باید با مقادیر مرجع یکسان باشند."""
    if not os.environ.get("SARRAFI_DATABASE_URL", "").startswith("postgres"):
        pytest.skip("SARRAFI_DATABASE_URL تنظیم نشده — تست فقط در CI/PG اجرا می‌شود")
    from app import schema, seed, context
    seed.reset_and_seed()
    conn = schema.get_connection()
    try:
        rows = conn.execute(
            """SELECT cb.name, c.code,
                   SUM(CASE WHEN t.direction='debit' THEN t.amount ELSE -t.amount END) bal
               FROM transactions t JOIN journal j ON j.id=t.journal_id
               JOIN cashboxes cb ON cb.id=t.cashbox_id JOIN currencies c ON c.id=t.currency_id
               WHERE j.status='posted' AND t.account_type='cashbox'
               GROUP BY cb.name, c.code""").fetchall()
        got = {f"{r['name']}:{r['code']}": r["bal"] for r in rows}
        assert got.get("صندوق اصلی:IRR") == 567100000
        assert got.get("صندوق اصلی:USD") == 1215000
        assert got.get("گاوصندوق:USD") == 800000
        assert conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 2
        # مانده‌ی حساب‌ها باید با موتور SQLite یکسان باشد (پاریتی)
        sqlite_rows = conn.execute(
            """SELECT cb.name, c.code, SUM(CASE WHEN t.direction='debit' THEN t.amount ELSE -t.amount END) bal
               FROM transactions t JOIN journal j ON j.id=t.journal_id
               JOIN cashboxes cb ON cb.id=t.cashbox_id JOIN currencies c ON c.id=t.currency_id
               WHERE j.status='posted' AND t.account_type='cashbox'
               GROUP BY cb.name, c.code""").fetchall()
        assert len(sqlite_rows) == len(rows)
    finally:
        conn.close()
