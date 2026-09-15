# -*- coding: utf-8 -*-
"""تست یکپارچه‌سازی PostgreSQL

این تست فقط وقتی اجرا می‌شود که ``SARRAFI_DATABASE_URL`` تنظیم شده باشد
(در CI: job «test-postgres»). بقیه‌ی تست‌ها روی فایل SQLite موقت خودشان
اجرا می‌شوند و به دیتابیس PostgreSQL دست نمی‌زنند.

هدف: اطمینان از اینکه سرویس روی PostgreSQL واقعی هم کامل کار می‌کند —
اسکیما، seed، تراکنش خرید/فروش، موجودی صندوق، و مسیرهای SQL مخصوص PG
(مثل STRING_AGG در فهرست اسکناس‌ها و پشتیبان‌گیری JSON).
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import schema, web, finance  # noqa: E402

pytestmark = pytest.mark.skipif(
    not schema.PG_URL,
    reason="SARRAFI_DATABASE_URL تنظیم نشده — تست یکپارچه‌سازی PostgreSQL رد شد",
)


class _Http:
    def __init__(self, base):
        self.base = base
        self.token = None

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method)
        r.add_header("Content-Type", "application/json")
        if self.token:
            r.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}


def _reset_pg_schema():
    """پاک‌کردن کامل اسکیما تا هر اجرا از حالت تازه شروع شود."""
    import psycopg2
    raw = psycopg2.connect(schema.PG_URL)
    raw.autocommit = True
    with raw.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
        cur.execute("CREATE SCHEMA public")
    raw.close()
    # استخر اتصال قدیمی را دور بریز تا اتصال‌های بسته‌شده استفاده نشوند
    schema._pg_pool = None


def test_engine_is_postgres():
    """بدون مسیر دیتابیس، موتور باید PostgreSQL باشد."""
    schema.use_sqlite(None)
    assert schema.engine() == "postgres"
    assert schema.db_info()["engine"] == "postgresql"
    assert "***" in schema.db_info()["url"] or "@" in schema.db_info()["url"]


def test_end_to_end_on_postgres():
    schema.use_sqlite(None)        # اجبار نمونه به SQLite (اگر تست دیگری گذاشته) برداشته شود
    assert schema.engine() == "postgres"
    _reset_pg_schema()

    # اسکیما دو بار اجرا شود تا بی‌اثر بودن (idempotent) آن تأیید شود
    schema.init_db()
    schema.init_db()

    srv = web.run(port=0)          # بدون db_path → همان PostgreSQL
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        # ۱) سلامت + موتور دیتابیس
        st, hl = h._req("GET", "/api/health")
        assert st == 200 and hl["db"]["engine"] == "postgresql"

        # ۲) ورود و داده‌های پایه (seed)
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200, j
        h.token = j["token"]

        st, cur = h._req("GET", "/api/currencies")
        assert st == 200 and cur["items"], "ارزهای پایه ساخته نشدند"
        usd = next(c for c in cur["items"] if c["code"] == "USD")

        # ۳) طرف حساب و صندوق
        st, j = h._req("POST", "/api/party/save",
                       {"full_name": "مشتری پستگرس", "type": "customer"})
        assert st == 200 and j["ok"], j
        party_id = j["id"]

        st, j = h._req("POST", "/api/cashbox/save",
                       {"name": "صندوق پستگرس", "kind": "cash", "currency_id": usd["id"]})
        assert st == 200 and j["ok"], j
        st, boxes = h._req("GET", "/api/cashboxes")
        assert any(c["name"] == "صندوق پستگرس" for c in boxes["items"])

        # موجودی صندوق پیش از معامله‌ها (موجودی اولیه‌ی seed)
        conn = schema.get_connection()
        try:
            before = finance.cashbox_balances(conn, 1, account_id=1).get("USD", 0)
        finally:
            conn.close()

        # ۴) خرید ارز از مشتری (افزایش موجودی صندوق)
        st, j = h._req("POST", "/api/buy",
                       {"party_id": party_id, "currency_id": usd["id"], "amount": 5000,
                        "rate": 1200000, "cashbox": 1, "method": "cash"})
        assert st == 200 and j.get("ok"), j
        assert j.get("invoice_id") and j.get("journal_id")

        # ۵) فروش ارز به مشتری (کاهش موجودی + سود)
        st, j = h._req("POST", "/api/sell",
                       {"party_id": party_id, "currency_id": usd["id"], "amount": 2000,
                        "rate": 1250000, "cashbox": 1, "method": "cash"})
        assert st == 200 and j.get("ok"), j

        # ۶) موجودی صندوق: ۵۰۰۰ - ۲۰۰۰ = ۳۰۰۰
        conn = schema.get_connection()
        try:
            after = finance.cashbox_balances(conn, 1, account_id=1).get("USD", 0)
        finally:
            conn.close()
        assert after - before == 3000, (
            f"تغییر موجودی باید ۳۰۰۰ دلار باشد (۵۰۰۰ خرید − ۲۰۰۰ فروش)؛ "
            f"قبل={before} بعد={after}")

        # گزارش صندوق از طریق HTTP
        st, rp = h._req("GET", "/api/report/cashbox?cashbox=1")
        assert st == 200 and "rows" in rp or st == 200, rp

        # ۷) فهرست اسکناس‌ها — مسیر SQL مخصوص PG (STRING_AGG)
        st, bn = h._req("GET", "/api/banknotes?limit=5")
        assert st == 200 and "items" in bn, bn

        # ۸) گزارش‌ها و نمودارها
        st, rep = h._req("GET", "/api/report/charts")
        assert st == 200 and isinstance(rep, dict), rep

        # ۹) پشتیبان‌گیری JSON (مسیر مخصوص PG در کد سرور)
        st, bk = h._req("POST", "/api/backup")
        assert st == 200 and bk.get("ok"), bk
        assert bk.get("file", "").endswith(".json")

        # ۱۰) برگشت شناسه‌ها از PG: BIGINT باید عدد صحیح برگردد (نه Decimal/رشته)
        assert isinstance(party_id, int), f"شناسه از نوع {type(party_id)} برگشت"
        st, pl = h._req("GET", "/api/parties")
        assert st == 200, pl
        mine = [p for p in pl["items"] if p["id"] == party_id]
        assert mine and mine[0]["full_name"] == "مشتری پستگرس", mine
        assert isinstance(mine[0]["id"], int)

        # ۱۱) فاکتورهای ثبت‌شده در PG قابل خواندن‌اند
        st, inv = h._req("GET", "/api/invoices")
        assert st == 200, inv
        assert len(inv.get("items", [])) >= 2, inv
    finally:
        srv.shutdown()
