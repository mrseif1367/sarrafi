# -*- coding: utf-8 -*-
"""تست‌های نسخه ۰٫۴ — امنیت، ارزها، اسکناس گروهی، کف موجودی، PDF"""

import os
import sys
import json
import datetime
import threading
import urllib.request
import urllib.error
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import schema, finance, util, seed, auth, report_pdf, context, web, totp


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test_v04.db")
    schema.init_db(p)
    conn = schema.get_connection(p)
    yield conn
    conn.close()


def _currencies(conn):
    conn.execute("INSERT INTO currencies(code,name,symbol,decimals,unit_ratio,sort_order) "
                 "VALUES ('IRR','ریال','﷼',0,1,0), ('USD','دلار','$',2,100,1)")
    conn.commit()
    return (conn.execute("SELECT id FROM currencies WHERE code='IRR'").fetchone()["id"],
            conn.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"])


# ---------------------------------------------------------------------------
# ۱) قفل ورود
# ---------------------------------------------------------------------------
def test_lockout_after_max_attempts(db):
    for _ in range(auth.MAX_ATTEMPTS):
        locked, remain = auth.register_failed_attempt(db, "admin")
        if locked:
            break
    assert locked is True
    assert remain == auth.LOCK_MINUTES * 60
    s = auth.lockout_status(db, "admin")
    assert s is not None and s > 0
    # ورود موفق باید قفل را بردارد
    auth.clear_attempts(db, "admin")
    assert auth.lockout_status(db, "admin") is None


def test_no_lockout_below_max(db):
    for _ in range(auth.MAX_ATTEMPTS - 1):
        locked, remain = auth.register_failed_attempt(db, "ali")
        assert locked is False
    assert auth.lockout_status(db, "ali") is None


# ---------------------------------------------------------------------------
# ۲) بازنشانی رمز عبور
# ---------------------------------------------------------------------------
def _make_user(db, username="u1", password="pass1"):
    conn = db
    conn.execute("INSERT INTO users(account_id,username,full_name,password_hash,role,is_active) "
                 "VALUES (1,?,?,?,?,1)",
                 (username, "تست", auth.hash_password(password), "admin"))
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]


def test_reset_code_lifecycle(db):
    uid = _make_user(db)
    code, ttl = auth.create_reset_code(db, "u1")
    assert ttl == auth.RESET_TTL_MINUTES
    assert auth.consume_reset_code(db, "u1", code) is True
    # کد یک‌بارمصرف است
    assert auth.consume_reset_code(db, "u1", code) is False
    # کد اشتباه
    code2, _ = auth.create_reset_code(db, "u1")
    assert auth.consume_reset_code(db, "u1", "000000") is False
    # تغییر رمز
    auth.set_password(db, uid, "newpass99")
    u = db.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
    assert auth.verify_password("newpass99", u["password_hash"]) is True


def test_reset_code_expiry(db):
    _make_user(db, "u2")
    code, _ = auth.create_reset_code(db, "u2")
    db.execute("UPDATE password_resets SET expires_at=? WHERE code=?",
               ("2000-01-01 00:00:00", code))
    db.commit()
    assert auth.consume_reset_code(db, "u2", code) is False


# ---------------------------------------------------------------------------
# ۳) مدیریت ارز
# ---------------------------------------------------------------------------
def test_currency_crud(db):
    # یک ارز پایه بسازیم تا سناریوی «کد تکراری» واقعی باشد
    finance.upsert_currency(db, {"code": "USD", "name": "دلار", "symbol": "$"})
    cid = finance.upsert_currency(db, {"code": "EUR", "name": "یورو", "symbol": "€",
                                       "decimals": 2, "unit_ratio": 100})
    row = db.execute("SELECT * FROM currencies WHERE id=?", (cid,)).fetchone()
    assert row["code"] == "EUR" and row["decimals"] == 2
    # ویرایش
    finance.upsert_currency(db, {"id": cid, "code": "EUR", "name": "یورو اروپا",
                                 "symbol": "€", "decimals": 3, "unit_ratio": 100})
    row = db.execute("SELECT * FROM currencies WHERE id=?", (cid,)).fetchone()
    assert row["name"] == "یورو اروپا" and row["decimals"] == 3
    # کد تکراری
    with pytest.raises(ValueError):
        finance.upsert_currency(db, {"code": "USD", "name": "تکراری"})
    # کد نامعتبر
    with pytest.raises(ValueError):
        finance.upsert_currency(db, {"code": "!!", "name": "x"})


# ---------------------------------------------------------------------------
# ۴) ثبت گروهی اسکناس
# ---------------------------------------------------------------------------
def test_bulk_banknotes(db):
    _currencies(db)
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    r = finance.bulk_banknotes(db, usd, 100, ["AB123", "CD456", "EF789"], user_id=1)
    assert r["inserted"] == 3 and r["duplicates"] == [] and r["skipped"] == []
    # تکراری داخل همان فهرست + تکراری در دیتابیس
    r2 = finance.bulk_banknotes(db, usd, 100, ["AB123", "AB123", "NEW99"], user_id=1)
    assert r2["inserted"] == 1          # فقط NEW99
    assert r2["duplicates"] == ["AB123"]  # قبلاً ثبت شده
    assert r2["skipped"] == ["AB123"]     # تکرار داخل فهرست
    cnt = db.execute("SELECT COUNT(*) c FROM banknotes").fetchone()["c"]
    assert cnt == 4


# ---------------------------------------------------------------------------
# ۵) هشدار کف موجودی
# ---------------------------------------------------------------------------
def test_low_stock_alerts(db):
    irr, usd = _currencies(db)
    db.execute("INSERT INTO cashboxes(name,code) VALUES ('صندوق اصلی','MAIN')")
    db.commit()
    cb = db.execute("SELECT id FROM cashboxes WHERE code='MAIN'").fetchone()["id"]
    # حداقل موجودی ۵۰ دلار
    db.execute("INSERT INTO settings(account_id,key,value) VALUES (0,'min_stock_USD','50')")
    db.commit()
    # هیچ موجودی نداریم → باید هشدار بدهد
    alerts = finance.low_stock_alerts(db)
    assert any(a["code"] == "USD" for a in alerts)
    # ثبت خرید دلار نقدی تا موجودی بالای حد برود
    pid = None
    db.execute("INSERT INTO parties(type,full_name) VALUES ('customer','علی')")
    db.commit()
    pid = db.execute("SELECT id FROM parties WHERE full_name='علی'").fetchone()["id"]
    finance.buy_currency(db, pid, usd, 100_000, 121_000, cb, cb, "تست", user_id=1)
    alerts2 = finance.low_stock_alerts(db)
    assert not any(a["code"] == "USD" for a in alerts2)  # موجودی ۱۰۰۰ دلار > ۵۰


# ---------------------------------------------------------------------------
# ۶) خروجی PDF
# ---------------------------------------------------------------------------
def test_pdf_generation(db):
    _currencies(db)
    data = report_pdf.generate(db, "2026-08-01", "2026-09-08", 0)
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000


# ---------------------------------------------------------------------------
# ۷) تست سرتاسری HTTP (e2e) روی سرور واقعی
# ---------------------------------------------------------------------------
class _Http:
    def __init__(self, base):
        self.base = base
        self.token = None

    def _req(self, method, path, body=None, headers=None):
        h = dict(headers or {})
        if self.token:
            h["X-Token"] = self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                ct = r.headers.get("Content-Type", "")
                raw = r.read()
                if "json" in ct:
                    return r.status, json.loads(raw)
                return r.status, raw
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}

    def login(self, u, p):
        st, j = self._req("POST", "/api/login", {"username": u, "password": p})
        if st == 200:
            self.token = j["token"]
        return st, j


def test_e2e_v04(tmp_path):
    dbp = str(tmp_path / "e2e.db")
    srv = web.run(port=0, db_path=dbp)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        # سلامت سیستم
        st, j = h._req("GET", "/api/health")
        assert st == 200 and j["app"] == "sarrafi"
        assert j["version"] == "0.9.2"

        # قفل ورود: ۵ تلاش ناموفق برای sara
        for i in range(auth.MAX_ATTEMPTS):
            st, j = h._req("POST", "/api/login", {"username": "sara", "password": "bad"})
        assert st == 429
        # حتی با رمز درست هم فعلاً قفل است
        st, j = h._req("POST", "/api/login", {"username": "sara", "password": "1234"})
        assert st == 429

        # فراموشی + بازنشانی رمز ali
        st, j = h._req("POST", "/api/password/forgot", {"username": "ali"})
        assert st == 200 and "code" in j
        st, j = h._req("POST", "/api/password/reset",
                       {"username": "ali", "code": j["code"], "new_password": "ali4567"})
        assert st == 200
        st, j = h._req("POST", "/api/login", {"username": "ali", "password": "ali4567"})
        assert st == 200

        # ورود admin و ثبت گروهی اسکناس
        st, j = h.login("admin", "admin123")
        assert st == 200
        st, cur = h._req("GET", "/api/currencies")
        usd = next(c for c in cur["items"] if c["code"] == "USD")
        st, r = h._req("POST", "/api/banknote/bulk", {
            "currency_id": usd["id"], "denomination": 100,
            "serials": ["ZX0001", "ZX0002", "ZX0001"]})
        assert st == 200 and r["inserted"] == 2 and r["skipped"] == ["ZX0001"]

        # کف موجودی
        st, j = h._req("GET", "/api/lowstock")
        assert st == 200 and "items" in j

        # خروجی PDF گزارش
        st, pdf = h._req("GET", "/api/report/pdf?from=2026-08-01&to=2026-09-08")
        assert st == 200 and pdf[:5] == b"%PDF-"

        # احراز دومرحله‌ای (TOTP) روی admin
        st, j = h._req("POST", "/api/2fa/start")
        assert st == 200 and j.get("secret")
        tfa_secret = j["secret"]
        st, j = h._req("POST", "/api/2fa/confirm", {"secret": tfa_secret, "code": "000000"})
        assert st == 400                      # کد اشتباه
        st, j = h._req("POST", "/api/2fa/confirm", {"secret": tfa_secret, "code": totp.current_code(tfa_secret)})
        assert st == 200 and j.get("ok")
        # ورود بدون کد → نیاز به 2FA
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 401 and j.get("need_2fa") is True
        # ورود با کد غلط
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123", "code": "999999"})
        assert st == 401
        # ورود با کد درست
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123",
                                              "code": totp.current_code(tfa_secret)})
        assert st == 200 and j["user"]["totp_enabled"] is True
        # غیرفعال‌سازی 2FA با کد معتبر
        h2 = _Http(h.base); h2.token = j["token"]
        st, j = h2._req("POST", "/api/2fa/disable", {"code": totp.current_code(tfa_secret)})
        assert st == 200 and j.get("ok")
        # حالا ورود عادی دوباره کار می‌کند
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200

        # مدیریت ارز توسط سوپرادمین + محدودیت پلن
        st, j = h.login("root", "root123")
        assert st == 200
        st, j = h._req("POST", "/api/currency/save",
                       {"code": "CAD", "name": "دلار کانادا", "symbol": "C$", "decimals": 2})
        assert st == 200 and j.get("ok")
        st, allc = h._req("GET", "/api/currencies/all")
        assert any(c["code"] == "CAD" for c in allc["items"])
        # ویرایش ارز
        cad_id = next(c["id"] for c in allc["items"] if c["code"] == "CAD")
        st, j = h._req("POST", "/api/currency/save",
                       {"id": cad_id, "code": "CAD", "name": "دلار کانادا (ویرایش)", "decimals": 3})
        assert st == 200
        st, allc = h._req("GET", "/api/currencies/all")
        cad = next(c for c in allc["items"] if c["code"] == "CAD")
        assert cad["decimals"] == 3

        # حساب معلق نمی‌تواند وارد شود
        conn = schema.get_connection(dbp)
        conn.execute("UPDATE accounts SET status='suspended' WHERE id=2")
        conn.commit()
        conn.close()
        st, j = h._req("POST", "/api/login", {"username": "parscash", "password": "1234"})
        assert st == 403
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# ۸) احراز دومرحله‌ای (TOTP)
# ---------------------------------------------------------------------------
def test_totp_rfc6238():
    # بردار آزمون استاندارد RFC 6238 (SHA1) — secret=base32("12345678901234567890")
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    for t, expect in ((59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
                      (1234567890, "005924"), (2000000000, "279037"), (20000000000, "353130")):
        assert totp.totp_at(secret, t // totp.WINDOW) == expect


def test_totp_verify_and_generate():
    s = totp.generate_secret()
    assert len(s) >= 16
    code = totp.current_code(s)
    assert totp.verify(s, code) is True
    assert totp.verify(s, "000000" if code != "000000" else "111111") is False
    # ورودی نامعتبر
    assert totp.verify(s, "abc") is False
    # لینک otpauth
    assert totp.otpauth_url(s, "admin").startswith("otpauth://totp/")
