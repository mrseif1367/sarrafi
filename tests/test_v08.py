# -*- coding: utf-8 -*-
"""تست‌های نسخه ۰٫۸ — حذف نرم سراسری با تأیید، سطل بازیافت و بازیابی.

پوشش:
- delete_preview برای هر موجودیت (نام + هشدار + مسدودیت)
- delete_entity (پنهان‌کردن + لغو سند برای اسناد مالی)
- restore_entity
- مسدودیت آخرین صندوق / آخرین مالک / حذف خود
- پنهان شدن از فهرست‌ها پس از حذف و برگشت پس از بازیابی
- گیت مجوز delete در endpoint ها
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import schema, finance, context, web, seed


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test_v08.db")
    seed.reset_and_seed(p)
    conn = schema.get_connection(p)
    context.set_account(1)
    context.set_user(1)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# ۱) پیش‌نمایش حذف
# ---------------------------------------------------------------------------
def test_delete_preview_party(db):
    pid = db.execute("SELECT id FROM parties WHERE account_id=1 LIMIT 1").fetchone()["id"]
    name = db.execute("SELECT full_name FROM parties WHERE id=?", (pid,)).fetchone()["full_name"]
    pv = finance.delete_preview(db, "party", pid, account_id=1)
    assert pv["type"] == "party" and pv["name"] == name
    assert pv["reversible"] is True and pv["blocked"] is False
    assert isinstance(pv["warnings"], list) and pv["warnings"]


def test_delete_preview_blocks_last_cashbox(db):
    # فقط یک صندوق فعال بگذاریم
    db.execute("UPDATE cashboxes SET deleted_at='2025-01-01 00:00:00' WHERE account_id=1")
    db.commit()
    cb = db.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (1,'تنها صندوق','ONLY','physical')")
    db.commit()
    cbid = cb.lastrowid
    pv = finance.delete_preview(db, "cashbox", cbid, account_id=1)
    assert pv["blocked"] is True and "آخرین صندوق" in pv["blocked_reason"]
    with pytest.raises(ValueError):
        finance.delete_entity(db, "cashbox", cbid, user_id=1, account_id=1)


def test_delete_preview_unknown_type(db):
    with pytest.raises(ValueError):
        finance.delete_preview(db, "nope", 1, account_id=1)


# ---------------------------------------------------------------------------
# ۲) حذف و بازیابی طرف حساب
# ---------------------------------------------------------------------------
def test_delete_restore_party(db):
    pid = db.execute("SELECT id FROM parties WHERE account_id=1 LIMIT 1").fetchone()["id"]
    r = finance.delete_entity(db, "party", pid, user_id=1, account_id=1)
    assert r["ok"] and r["id"] == pid
    row = db.execute("SELECT deleted_at, is_active FROM parties WHERE id=?", (pid,)).fetchone()
    assert row["deleted_at"] is not None and row["is_active"] == 0
    # در سطل بازیافت دیده می‌شود
    items = finance.list_deleted(db, account_id=1)["items"]
    assert any(i["type"] == "party" and i["id"] == pid for i in items)
    # بازیابی
    r = finance.restore_entity(db, "party", pid, user_id=1, account_id=1)
    assert r["ok"]
    row = db.execute("SELECT deleted_at, is_active FROM parties WHERE id=?", (pid,)).fetchone()
    assert row["deleted_at"] is None and row["is_active"] == 1


# ---------------------------------------------------------------------------
# ۳) حذف سند مالی (هزینه) → لغو سند
# ---------------------------------------------------------------------------
def test_delete_expense_voids_journal(db):
    usd = db.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]
    jid = finance.add_expense(db, "هزینه تست", usd, 1000, 500000, 1,
                              description="x", user_id=1, account_id=1)["journal_id"]
    eid = db.execute("SELECT id FROM expenses WHERE journal_id=?", (jid,)).fetchone()["id"]
    r = finance.delete_entity(db, "expense", eid, user_id=1, account_id=1)
    assert r["ok"] and r["voided_journal"] == jid
    row = db.execute("SELECT deleted_at FROM expenses WHERE id=?", (eid,)).fetchone()
    assert row["deleted_at"] is not None
    j = db.execute("SELECT status FROM journal WHERE id=?", (jid,)).fetchone()
    assert j["status"] == "voided"


# ---------------------------------------------------------------------------
# ۴) محافظت‌ها: حذف خود / آخرین مالک
# ---------------------------------------------------------------------------
def test_self_delete_blocked(db):
    owner = db.execute("SELECT id FROM users WHERE is_owner=1 AND account_id=1 LIMIT 1").fetchone()["id"]
    with pytest.raises(ValueError):
        finance.delete_entity(db, "user", owner, user_id=owner, account_id=1, self_id=owner)


def test_last_owner_delete_blocked(db):
    owner = db.execute("SELECT id FROM users WHERE is_owner=1 AND account_id=1 LIMIT 1").fetchone()["id"]
    # کسی دیگر (غیرمالک) سعی می‌کند تنها مالک حساب را حذف کند
    other = db.execute("SELECT id FROM users WHERE account_id=1 AND is_owner=0 LIMIT 1").fetchone()["id"]
    with pytest.raises(ValueError):
        finance.delete_entity(db, "user", owner, user_id=other, account_id=1, self_id=other)


def test_super_admin_delete_guarded(db):
    root = db.execute("SELECT id FROM users WHERE role='super_admin' LIMIT 1").fetchone()["id"]
    # ادمین نمی‌تواند سوپرادمین را حذف کند
    with pytest.raises(ValueError):
        finance.delete_entity(db, "user", root, user_id=2, account_id=1, self_id=2)
    # پیش‌نمایش نیز مسدود گزارش می‌کند
    pv = finance.delete_preview(db, "user", root, account_id=1, actor={"role": "admin"})
    assert pv["blocked"] is True


# ---------------------------------------------------------------------------
# ۵) گیت مجوز + سناریوی سرتاسری HTTP
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
                raw = r.read()
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}


def test_e2e_delete(tmp_path):
    dbp = str(tmp_path / "e2e_v08.db")
    srv = web.run(port=0, db_path=dbp)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200
        h.token = j["token"]

        # فهرست مجوزها شامل delete است
        st, perms = h._req("GET", "/api/permissions")
        assert any(p["key"] == "delete" for p in perms["perms"])

        # ساخت طرف حساب و حذف آن
        st, j = h._req("POST", "/api/party/save",
                       {"full_name": "طرف حذف‌شدنی", "type": "customer"})
        assert st == 200 and j["ok"]
        pid = j["id"]

        st, info = h._req("GET", f"/api/delete/info?type=party&id={pid}")
        assert st == 200 and info["name"] == "طرف حذف‌شدنی"

        st, j = h._req("POST", "/api/delete", {"type": "party", "id": pid})
        assert st == 200 and j["ok"]

        st, parties = h._req("GET", "/api/parties")
        assert all(p["id"] != pid for p in parties["items"])

        st, deleted = h._req("GET", "/api/deleted")
        assert any(i["type"] == "party" and i["id"] == pid for i in deleted["items"])

        st, j = h._req("POST", "/api/restore", {"type": "party", "id": pid})
        assert st == 200 and j["ok"]
        st, parties = h._req("GET", "/api/parties")
        assert any(p["id"] == pid for p in parties["items"])

        # صندوق‌دار بدون مجوز delete باید 403 بگیرد
        st, j = h._req("POST", "/api/login", {"username": "ali", "password": "1234"})
        assert st == 200
        h.token = j["token"]
        st, deleted = h._req("GET", "/api/deleted")
        assert st == 403
        st, j = h._req("POST", "/api/delete", {"type": "party", "id": pid})
        assert st == 403
    finally:
        srv.shutdown()
