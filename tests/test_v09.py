# -*- coding: utf-8 -*-
"""تست‌های نسخه ۰٫۹ — ماسک اعداد (کلاینت)، الصاق/جداسازی اسکناس و فیلتر «در دسترس».

پوشش:
- list_available_banknotes فقط اسکناس‌های در خزانه و حذف‌نشده را برمی‌گرداند
- attach_banknotes (فروش) وضعیت را sold می‌کند و از لیست در دسترس خارج می‌شود
- attach تکراری به همان سند نادیده گرفته می‌شود (idempotent)
- detach_banknote اسکناس را به in_vault برمی‌گرداند و دوباره در دسترس می‌شود
- attach خرید (purchase) اسکناس را در خزانه نگه می‌دارد
- endpoint ها: available / attach / detach + گیت مجوز banknote
- جزئیات فاکتور شامل اسکناس‌های پیوندخورده است
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
    p = str(tmp_path / "test_v09.db")
    seed.reset_and_seed(p)
    conn = schema.get_connection(p)
    context.set_account(1)
    context.set_user(1)
    yield conn
    conn.close()


def _usd(conn):
    return conn.execute("SELECT id FROM currencies WHERE code='USD'").fetchone()["id"]


def _main_cb(conn):
    return conn.execute("SELECT id FROM cashboxes WHERE code='MAIN' AND account_id=1").fetchone()["id"]


def _party(conn):
    return conn.execute("SELECT id FROM parties WHERE account_id=1 LIMIT 1").fetchone()["id"]


def _jid(conn, jtype="sell", title="تست"):
    cur = conn.execute(
        "INSERT INTO journal(account_id,jtype,title,status) VALUES (1,?,?,'posted')",
        (jtype, title))
    return cur.lastrowid


# ---------------------------------------------------------------------------
# ۱) فهرست «در دسترس»
# ---------------------------------------------------------------------------
def test_available_excludes_sold(db):
    av = finance.list_available_banknotes(db, account_id=1)
    serials = {b["serial"] for b in av}
    assert "CD98765432" not in serials          # فروخته‌شده نباید بیاید
    assert "AB12345678" in serials              # در خزانه باید بیاید
    assert all(b["status"] == "in_vault" for b in av)


def test_available_filter_by_currency(db):
    usd = _usd(db)
    av = finance.list_available_banknotes(db, currency_id=usd, account_id=1)
    assert all(b["currency_id"] == usd for b in av)
    assert "XZ55667788" not in {b["serial"] for b in av}   # EUR حذف شود


def test_available_excludes_deleted(db):
    finance.delete_entity(db, "banknote", 1, user_id=1, account_id=1)
    av = finance.list_available_banknotes(db, account_id=1)
    assert all(b["id"] != 1 for b in av)


# ---------------------------------------------------------------------------
# ۲) الصاق (فروش) + نادیده‌گرفتن تکراری
# ---------------------------------------------------------------------------
def test_attach_sale_sets_sold_and_hides(db):
    usd = _usd(db)
    cb = _main_cb(db)
    party = _party(db)
    bn = finance.register_banknotes(
        db, usd, 10_000, [{"serial": "SALE00000001"}], status="in_vault",
        cashbox_id=cb, user_id=1, account_id=1)
    bid = bn["banknote_ids"][0]
    jid = _jid(db)
    r = finance.attach_banknotes(db, [bid], journal_id=jid, party_id=party,
                                 movement_type="sale", cashbox_id=cb,
                                 user_id=1, account_id=1)
    assert bid in r["attached"] and not r["rejected"]
    st = db.execute("SELECT status FROM banknotes WHERE id=?", (bid,)).fetchone()["status"]
    assert st == "sold"
    assert bid not in {b["id"] for b in finance.list_available_banknotes(db, account_id=1)}
    # تکراری به همان سند → skipped
    r2 = finance.attach_banknotes(db, [bid], journal_id=jid, party_id=party,
                                  movement_type="sale", cashbox_id=cb,
                                  user_id=1, account_id=1)
    assert bid in [s["id"] for s in r2["skipped"]]


def test_attach_rejects_used(db):
    sold = db.execute("SELECT id FROM banknotes WHERE serial='CD98765432'").fetchone()["id"]
    r = finance.attach_banknotes(db, [sold], movement_type="sale", user_id=1, account_id=1)
    assert not r["attached"] and r["rejected"]


def test_attach_requires_selection(db):
    with pytest.raises(ValueError):
        finance.attach_banknotes(db, [], movement_type="sale", user_id=1, account_id=1)


# ---------------------------------------------------------------------------
# ۳) جداسازی
# ---------------------------------------------------------------------------
def test_detach_returns_to_vault(db):
    usd = _usd(db)
    cb = _main_cb(db)
    bn = finance.register_banknotes(
        db, usd, 10_000, [{"serial": "DET00000001"}], status="in_vault",
        cashbox_id=cb, user_id=1, account_id=1)
    bid = bn["banknote_ids"][0]
    jid = _jid(db)
    finance.attach_banknotes(db, [bid], journal_id=jid, movement_type="sale",
                             cashbox_id=cb, user_id=1, account_id=1)
    r = finance.detach_banknote(db, bid, user_id=1, account_id=1)
    assert r["ok"]
    st = db.execute("SELECT status, cashbox_id FROM banknotes WHERE id=?", (bid,)).fetchone()
    assert st["status"] == "in_vault" and st["cashbox_id"] == cb
    assert bid in {b["id"] for b in finance.list_available_banknotes(db, account_id=1)}
    n_moves = db.execute(
        "SELECT COUNT(*) c FROM banknote_movements WHERE banknote_id=? AND journal_id=?",
        (bid, jid)).fetchone()["c"]
    assert n_moves == 0


def test_detach_no_link(db):
    usd = _usd(db)
    cb = _main_cb(db)
    bn = finance.register_banknotes(
        db, usd, 10_000, [{"serial": "NOLINK00001"}], status="in_vault",
        cashbox_id=cb, user_id=1, account_id=1)
    with pytest.raises(ValueError):
        finance.detach_banknote(db, bn["banknote_ids"][0], user_id=1, account_id=1)


def test_attach_purchase_keeps_in_vault(db):
    usd = _usd(db)
    cb = _main_cb(db)
    party = _party(db)
    bn = finance.register_banknotes(
        db, usd, 5_000, [{"serial": "PUR00000001"}], status="in_vault",
        cashbox_id=None, user_id=1, account_id=1)
    bid = bn["banknote_ids"][0]
    jid = _jid(db, jtype="buy", title="تست خرید")
    r = finance.attach_banknotes(db, [bid], journal_id=jid, party_id=party,
                                 movement_type="purchase", cashbox_id=cb,
                                 user_id=1, account_id=1)
    assert bid in r["attached"]
    st = db.execute("SELECT status, cashbox_id FROM banknotes WHERE id=?", (bid,)).fetchone()
    assert st["status"] == "in_vault" and st["cashbox_id"] == cb


# ---------------------------------------------------------------------------
# ۴) endpoint ها (e2e)
# ---------------------------------------------------------------------------
class _Http:
    def __init__(self, base):
        self.base = base
        self.token = None

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}


def test_e2e_attach_detach_http(tmp_path):
    dbp = str(tmp_path / "e2e_v09.db")
    srv = web.run(port=0, db_path=dbp)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200
        h.token = j["token"]

        st, cur = h._req("GET", "/api/currencies")
        usd = next(c for c in cur["items"] if c["code"] == "USD")
        st, cbs = h._req("GET", "/api/cashboxes")
        main_cb = next(c for c in cbs["items"] if c["code"] == "MAIN")
        st, parties = h._req("GET", "/api/parties")
        pid = parties["items"][0]["id"]

        # ثبت اسکناس جدید در خزانه
        st, j = h._req("POST", "/api/banknote/save", {
            "currency_id": usd["id"], "denomination": 10_000,
            "serial": "HTTP00000001", "status": "in_vault",
            "cashbox_id": main_cb["id"], "note": "تست e2e"})
        assert st == 200 and j["ok"]
        bid = j["id"]

        st, av = h._req("GET", f"/api/banknotes/available?currency_id={usd['id']}&q=HTTP")
        assert st == 200 and any(b["id"] == bid for b in av["items"])

        # فروش واقعی برای گرفتن journal_id و invoice_id
        st, j = h._req("POST", "/api/sell", {
            "party_id": pid, "currency_id": usd["id"], "amount": 10_000,
            "rate": 121_000, "cashbox": main_cb["id"], "method": "cash", "confirm": True})
        assert st == 200 and j["ok"]
        journal_id = j["journal_id"]
        invoice_id = j["invoice_id"]

        # الصاق فروش به فاکتور
        st, j = h._req("POST", "/api/banknote/attach", {
            "ids": [bid], "movement_type": "sale", "party_id": pid,
            "journal_id": journal_id, "invoice_id": invoice_id})
        assert st == 200 and bid in j["attached"]

        st, av = h._req("GET", f"/api/banknotes/available?currency_id={usd['id']}&q=HTTP")
        assert st == 200 and not any(b["id"] == bid for b in av["items"])

        # جزئیات فاکتور باید اسکناس پیوندخورده را نشان دهد
        st, inv = h._req("GET", f"/api/invoice?id={invoice_id}")
        assert st == 200 and any(b["id"] == bid for b in inv["banknotes"])

        # جداسازی
        st, j = h._req("POST", "/api/banknote/detach", {"id": bid})
        assert st == 200 and j["ok"]

        st, av = h._req("GET", f"/api/banknotes/available?currency_id={usd['id']}&q=HTTP")
        assert st == 200 and any(b["id"] == bid for b in av["items"])

        # گیت مجوز: حسابدار (sara) مجوز banknote ندارد
        st, j = h._req("POST", "/api/login", {"username": "sara", "password": "1234"})
        assert st == 200
        h.token = j["token"]
        st, _ = h._req("GET", "/api/banknotes/available")
        assert st == 403
        st, _ = h._req("POST", "/api/banknote/attach", {"ids": [bid], "movement_type": "sale"})
        assert st == 403
        st, _ = h._req("POST", "/api/banknote/detach", {"id": bid})
        assert st == 403
    finally:
        srv.shutdown()
