# -*- coding: utf-8 -*-
"""تست‌های نسخه ۰٫۶ — چندنرخی، کارمزد/مالیات، سقف اعتبار، یادآور سررسید،
شمارش فقط-تعداد، تطبیق فاکتور، خروجی xlsx، جستجوی سراسری، بکاپ رمزنگاری‌شده،
پیش‌بینی نقدینگی، پلن/صورتحساب SaaS و محدودسازی نرخ"""

import base64
import datetime
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import schema, finance, context, web, seed, crypto, ocr


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test_v06.db")
    seed.reset_and_seed(p)
    conn = schema.get_connection(p)
    context.set_account(1)
    context.set_user(1)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# ۱) سقف اعتبار مشتری
# ---------------------------------------------------------------------------
def test_party_credit_limit_save(db):
    # ذخیره مستقیم از طریق SQL — ستون باید موجود باشد
    db.execute("UPDATE parties SET credit_limit=? WHERE id=1", (10_000_000,))
    db.commit()
    check = finance.party_credit_check(db, 1, extra_rial=0)
    assert check["credit_limit"] == 10_000_000
    assert check["used_rial"] == 0
    assert check["would_exceed"] is False
    check2 = finance.party_credit_check(db, 1, extra_rial=12_000_000)
    assert check2["would_exceed"] is True
    assert check2["available_rial"] == 10_000_000


def test_party_credit_usage_from_sell(db):
    db.execute("UPDATE parties SET credit_limit=? WHERE id=1", (500_000,))
    db.commit()
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    # فروش نسیه: ۱۰۰ دلار × ۵۰۰۰ = ۵۰۰٬۰۰۰ ریال بدهی
    finance.sell_currency(db, 1, usd, 10000, 5000, 2, 1, user_id=1,
                          payment_method="later", allow_negative=True)
    check = finance.party_credit_check(db, 1)
    assert check["used_rial"] == 500_000
    assert check["would_exceed"] is False  # دقیقاً در سقف
    assert finance.party_credit_check(db, 1, extra_rial=1)["would_exceed"] is True


# ---------------------------------------------------------------------------
# ۲) یادآور سررسید قرض + تاریخ سررسید
# ---------------------------------------------------------------------------
def test_loan_due_reminders(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    today = datetime.date.today()
    due_soon = (today + datetime.timedelta(days=3)).isoformat()
    overdue = (today - datetime.timedelta(days=2)).isoformat()
    finance.loan_give(db, 2, usd, 10000, 500000, 2, "قرض کوتاه‌مدت",
                      user_id=1, allow_negative=True, due_date=due_soon)
    finance.loan_give(db, 2, usd, 20000, 500000, 2, "قرض معوق",
                      user_id=1, allow_negative=True, due_date=overdue)
    finance.loan_give(db, 2, usd, 30000, 500000, 2, "قرض بدون سررسید",
                      user_id=1, allow_negative=True)
    rem = finance.loan_reminders(db, days_ahead=7)
    parties = {(r["party"], r["remaining"]): (r["overdue"], r["days_left"]) for r in rem}
    # هر دو قرضِ دارای سررسید باید بیایند؛ بدون‌سررسید نه
    assert len(rem) == 2
    assert any(r["overdue"] for r in rem)
    assert all(r["due_date"] for r in rem)
    # بازپرداخت کامل یکی → از یادآورها حذف شود
    loan_overdue = [r for r in rem if r["overdue"]][0]
    finance.loan_repay(db, loan_overdue["loan_id"], usd, loan_overdue["remaining"],
                       500000, 2, user_id=1, allow_negative=True)
    rem2 = finance.loan_reminders(db, days_ahead=7)
    assert all(r["loan_id"] != loan_overdue["loan_id"] for r in rem2)


# ---------------------------------------------------------------------------
# ۳) ثبت شمارشی (count-only) + تطبیق با فاکتور
# ---------------------------------------------------------------------------
def test_register_count_only_and_reconciliation(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    r = finance.buy_currency(db, 1, usd, 100000, 500000, 2, 1, user_id=1)
    # فاکتور ۱۰۰۰ دلار؛ شمارش فقط ۹ اسکناس ۱۰۰ دلاری → ۹۰۰ دلار → اختلاف ۱۰۰ دلار
    # (denomination به واحد کسری ذخیره می‌شود: ۱۰۰ دلار = ۱۰۰۰۰)
    res = finance.register_banknotes(db, usd, 10000, [], status="in_vault",
                                     cashbox_id=2, party_id=1, user_id=1,
                                     invoice_id=r["invoice_id"], count_only=9)
    assert res["count_only"] == 9
    assert res["inserted"] == 9
    assert res["reconciliation"]["registered_minor"] == 9 * 10000
    assert res["reconciliation"]["matched"] is False
    assert res["reconciliation"]["diff_minor"] == 10000
    # سریال‌های موقت ساخته شده‌اند
    n = db.execute("SELECT COUNT(*) c FROM banknotes WHERE batch_id=?",
                   (res["batch_id"],)).fetchone()["c"]
    assert n == 9
    ser = db.execute("SELECT serial FROM banknotes WHERE batch_id=? LIMIT 1",
                     (res["batch_id"],)).fetchone()["serial"]
    assert ser.startswith("NB")


def test_register_exact_match_reconciliation(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    # فاکتور ۱۰۰۰ سنت = ۱۰ دلار؛ ۱۰ اسکناس ۱ دلاری (۱ دلار = ۱۰۰ واحد کسری)
    r = finance.buy_currency(db, 1, usd, 1000, 500000, 2, 1, user_id=1)
    items = [{"serial": f"EX{i:08d}A"} for i in range(10)]
    res = finance.register_banknotes(db, usd, 100, items, status="in_vault",
                                     cashbox_id=2, party_id=1, user_id=1,
                                     invoice_id=r["invoice_id"])
    assert res["reconciliation"]["matched"] is True
    assert res["reconciliation"]["diff_minor"] == 0


# ---------------------------------------------------------------------------
# ۴) کارمزد و مالیات + چندنرخی
# ---------------------------------------------------------------------------
def test_fee_tax_on_invoice(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    # ۱۰۰ دلار × ۵۰۰۰ ریال/دلار؛ کارمزد ۲ دلار؛ مالیات ۱ دلار
    r = finance.sell_currency(db, 1, usd, 10000, 5000, 2, 1, user_id=1,
                              fee_minor=200, tax_minor=100, rate_type="sell")
    inv = db.execute("SELECT * FROM invoices WHERE id=?", (r["invoice_id"],)).fetchone()
    assert inv["fee_minor"] == 200 and inv["tax_minor"] == 100
    assert inv["rate_type"] == "sell"
    assert inv["total_rial"] == 10000 * 5000 // 100 + 200 * 5000 // 100 + 100 * 5000 // 100
    assert r["fee_rial"] == 10000 and r["tax_rial"] == 5000


def test_multirate_upsert(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    today = datetime.date.today().strftime("%Y-%m-%d")
    for t, v in [("buy", 495000), ("sell", 505000), ("sana", 500000)]:
        db.execute(
            """INSERT INTO exchange_rates(account_id,currency_id,rate,rate_date,rate_type,source)
               VALUES (?,?,?,?,?,?) ON CONFLICT(account_id,currency_id,rate_date,rate_type)
               DO UPDATE SET rate=excluded.rate""",
            (1, usd, v, today, t, "manual"))
    # آپدیت همان روز/نوع → جایگزینی به‌جای درج تکراری
    db.execute(
        """INSERT INTO exchange_rates(account_id,currency_id,rate,rate_date,rate_type,source)
           VALUES (?,?,?,?,?,?) ON CONFLICT(account_id,currency_id,rate_date,rate_type)
           DO UPDATE SET rate=excluded.rate""",
        (1, usd, 496000, today, "buy", "manual"))
    db.commit()
    rows = db.execute(
        "SELECT rate_type, rate FROM exchange_rates WHERE currency_id=? AND rate_date=? AND rate_type!='market'",
        (usd, today)).fetchall()
    assert {(r["rate_type"], r["rate"]) for r in rows} == {
        ("buy", 496000), ("sell", 505000), ("sana", 500000)}


# ---------------------------------------------------------------------------
# ۵) رمزنگاری بکاپ
# ---------------------------------------------------------------------------
def test_crypto_roundtrip():
    data = ("سلام دنیا ۱۲۳".encode("utf-8") * 100)
    enc = crypto.encrypt(data, "my-secret")
    assert enc.startswith(b"SRFENC01")
    assert crypto.decrypt(enc, "my-secret") == data
    with pytest.raises(ValueError):
        crypto.decrypt(enc, "wrong-pass")


def test_forecast(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    finance.sell_currency(db, 1, usd, 10000, 500000, 2, 1, user_id=1,
                          payment_method="later", allow_negative=True)
    f = finance.cashflow_forecast(db, days=30)
    assert f["incoming_rial"] >= 50_000_000  # ۱۰۰ دلار × ۵۰۰ هزار
    assert isinstance(f["net_rial"], int)


# ---------------------------------------------------------------------------
# ۶) تست سرتاسری HTTP
# ---------------------------------------------------------------------------
class _Http:
    def __init__(self, base):
        self.base = base
        self.token = None

    def _req(self, method, path, body=None):
        h = {}
        if self.token:
            h["X-Token"] = self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                ct = r.headers.get("Content-Type", "")
                raw = r.read()
                return r.status, (json.loads(raw) if "json" in ct else raw)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}


def test_e2e_v06(tmp_path):
    dbp = str(tmp_path / "e2e_v06.db")
    srv = web.run(port=0, db_path=dbp)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200
        h.token = j["token"]

        # ۱) سلامت و نسخه
        st, hl = h._req("GET", "/api/health")
        assert hl["version"] == "0.9.2"
        if ocr.available():
            assert hl["ocr"] is True  # فقط وقتی موتور OCR نصب است

        # ۲) ذخیره‌ی طرف حساب با سقف اعتبار
        st, j = h._req("POST", "/api/party/save",
                       {"full_name": "مشتری اعتباری", "type": "customer",
                        "credit_limit": 1000000})
        assert st == 200 and j["ok"]
        pid = j["id"]

        # ۳) فروش نسیه → هشدار سقف اعتبار
        st, cur = h._req("GET", "/api/currencies")
        usd = next(c for c in cur["items"] if c["code"] == "USD")
        st, j = h._req("POST", "/api/sell",
                       {"party_id": pid, "currency_id": usd["id"], "amount": 30000,
                        "rate": 500000, "cashbox": 1, "method": "later",
                        "fee_minor": 100, "tax_minor": 50})
        assert st == 200 and j["ok"]
        assert j["credit"]["would_exceed"] is True
        assert j["credit"]["credit_limit"] == 1000000

        # ۴) چندنرخی (ثبت و خواندن)
        st, j = h._req("POST", "/api/rate",
                       {"currency_id": usd["id"], "rate": 501000, "rate_type": "buy"})
        assert st == 200 and j["ok"]
        st, j = h._req("POST", "/api/rate",
                       {"currency_id": usd["id"], "rate": 509000, "rate_type": "sell"})
        assert st == 200
        st, rates = h._req("GET", "/api/rates")
        assert "by_type" in rates
        assert "buy" in rates["by_type"] and "sell" in rates["by_type"]

        # ۵) جستجوی سراسری
        st, s = h._req("GET", "/api/search?q=" + urllib.request.quote("مشتری اعتباری"))
        assert st == 200 and any(i["type"] == "party" for i in s["items"])

        # ۶) خروجی xlsx
        st, xl = h._req("GET", "/api/export/xlsx?type=invoices")
        assert st == 200
        assert xl[:2] == b"PK"  # فایل zip/xlsx

        # ۷) پیش‌بینی نقدینگی
        st, f = h._req("GET", "/api/forecast?days=30")
        assert st == 200 and f["incoming_rial"] > 0

        # ۸) پلن‌ها و صورتحساب (شبیه‌سازی پرداخت)
        st, pl = h._req("GET", "/api/plans")
        assert st == 200 and any(p["code"] == "pro" for p in pl["items"])
        st, co = h._req("POST", "/api/billing/checkout", {"plan_code": "pro"})
        assert st == 200 and co["ref_code"].startswith("sim-")
        st, cf = h._req("POST", "/api/billing/confirm", {"ref_code": co["ref_code"]})
        assert st == 200 and cf["ok"]
        st, acc = h._req("GET", "/api/me")
        assert acc["account"]["plan"] == "pro"

        # ۹) بکاپ رمزنگاری‌شده + بازیابی
        st, j = h._req("POST", "/api/backup/passphrase", {"passphrase": "test-pp"})
        assert st == 200 and j["encrypted"] is True
        st, b = h._req("POST", "/api/backup", {})
        assert st == 200 and b["encrypted"] is True
        assert b["file"].endswith(".enc")

        # ۱۰) بازیابی رمز (بدون SMTP → کد برمی‌گردد)
        st, j = h._req("POST", "/api/password/forgot", {"username": "admin"})
        assert st == 200 and j["ok"]
        assert "code" in j  # حالت دمو
        st, j = h._req("POST", "/api/password/reset",
                       {"username": "admin", "code": j["code"], "new_password": "admin123"})
        assert st == 200

        # ۱۱) یادآور سررسید در داشبورد
        st, dash = h._req("GET", "/api/dashboard")
        assert "reminders" in dash and "alerts" in dash

        # ۱۲) محدودسازی نرخ (۲۰ درخواست در دقیقه) — بدون لاگین ۲۱ بار
        got429 = False
        for _ in range(25):
            st, _ = h._req("POST", "/api/signup", {})
            if st == 429:
                got429 = True
                break
        assert got429
    finally:
        srv.shutdown()
