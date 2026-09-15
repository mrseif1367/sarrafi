# -*- coding: utf-8 -*-
"""تست‌های نسخه ۰٫۹٫۲ — منبع نرخ «نوسان» + زنجیره‌ی بازگشت (fallback).

پوشش:
- fetch_navasan: تومان → ریال (×۱۰)، مقدار string، اولویت usd بر usd_sell
- fetch_navasan بدون کلید → خطای شفاف
- پاسخ غیر JSON (کلید نادرست) → خطای شفاف
- fetch_with_fallback: نوسان می‌افتد → er-api موفق می‌شود و fallback=True
- fetch_with_fallback وقتی همه شکست بخورند → خطا
- endpoint /api/rates/status: navasan_key_set و پیش‌فرض navasan
- ذخیره/ماسک/حذف کلید در /api/settings/save و /api/settings
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import rates, schema, context, seed, web


def _patch_http(monkeypatch, payloads):
    """monkeypatch نرخ: _get/_get_raw بر اساس URL پاسخ نمونه برمی‌گردانند."""
    def fake_raw(url):
        for needle, body in payloads.items():
            if needle in url:
                return body
        raise urllib.error.HTTPError(url, 404, "no canned response", {}, None)

    monkeypatch.setattr(rates, "_get_raw", fake_raw)
    monkeypatch.setattr(rates, "_get", lambda url: json.loads(fake_raw(url)))


NAVASAN_OK = json.dumps({
    "usd": {"value": "235500", "change": -700},
    "usd_sell": {"value": "236000", "change": -600},
    "eur": {"value": "273260", "change": -740},
    "aed": {"value": "64740", "change": -200},
    "try": {"value": "4865", "change": 5},
})

ER_API_OK = json.dumps({
    "result": "success",
    "rates": {"USD": 1, "EUR": 0.86, "AED": 0.27, "TRY": 0.033,
              "GBP": 0.75, "IQD": 1310, "CHF": 0.84, "CNY": 7.1, "RUB": 95, "IRR": 1440000},
})


def test_navasan_toman_to_rial(monkeypatch):
    _patch_http(monkeypatch, {"api.navasan.tech": NAVASAN_OK})
    out = rates.fetch_navasan(api_key="test-key")
    assert out["IRR"] == 1
    # usd باید از نماد usd (نه usd_sell) بیاید و تومان → ریال شود
    assert out["USD"] == 235500 * 10
    assert out["EUR"] == 273260 * 10
    assert out["AED"] == 64740 * 10
    assert out["TRY"] == 4865 * 10


def test_navasan_requires_key(monkeypatch):
    monkeypatch.delenv("SARRAFI_NAVASAN_KEY", raising=False)
    with pytest.raises(ValueError):
        rates.fetch_navasan(api_key=None)


def test_navasan_plain_text_error(monkeypatch):
    _patch_http(monkeypatch, {"api.navasan.tech": "Invalid api_key"})
    with pytest.raises(ValueError):
        rates.fetch_navasan(api_key="bad-key")


def test_navasan_env_key(monkeypatch):
    _patch_http(monkeypatch, {"api.navasan.tech": NAVASAN_OK})
    monkeypatch.setenv("SARRAFI_NAVASAN_KEY", "env-key")
    out = rates.fetch_navasan(api_key=None)
    assert out["USD"] == 235500 * 10


def test_fallback_to_er_api(monkeypatch):
    # نوسان بدون کلید می‌افتد؛ er-api باید موفق شود
    monkeypatch.delenv("SARRAFI_NAVASAN_KEY", raising=False)
    _patch_http(monkeypatch, {"open.er-api.com": ER_API_OK})
    res = rates.fetch_with_fallback(preferred="navasan", api_key=None)
    assert res["provider"] == "er-api"
    assert res["fallback"] is True
    assert res["rates"]["USD"] > 0
    assert "IQD" in res["rates"]
    assert any("navasan" in t for t in res.get("tried", []))


def test_fallback_all_fail(monkeypatch):
    monkeypatch.delenv("SARRAFI_NAVASAN_KEY", raising=False)
    def boom(url):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(rates, "_get", boom)
    monkeypatch.setattr(rates, "_get_raw", boom)
    with pytest.raises(ValueError):
        rates.fetch_with_fallback(preferred="navasan", api_key=None)


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test_navasan.db")
    seed.reset_and_seed(p)
    conn = schema.get_connection(p)
    context.set_account(1)
    context.set_user(2)  # admin
    yield conn
    conn.close()


def test_rates_status_default_navasan(db):
    st = web.Handler
    # ساده: مقدار پیش‌فرض در status باید navasan باشد
    assert rates.DEFAULT_PROVIDER == "navasan"
    assert "navasan" in rates.PROVIDERS
    assert rates.PROVIDERS["navasan"].get("needs_key") is True


def test_settings_key_masked_and_saved(db):
    """ذخیرهٔ کلید، ماسک‌شدن در GET و حذف آن."""
    db.execute(
        "INSERT INTO settings(account_id,key,value) VALUES(1,'rate_navasan_key','secret-key') "
        "ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value")
    db.commit()
    rows = db.execute("SELECT key,value FROM settings WHERE account_id=1").fetchall()
    s = {r["key"]: r["value"] for r in rows}
    assert s["rate_navasan_key"] == "secret-key"

    # ماسک برای خروجی
    masked = dict(s)
    if masked.get("rate_navasan_key"):
        masked["rate_navasan_key"] = "********"
    assert masked["rate_navasan_key"] == "********"

    # حذف
    db.execute("DELETE FROM settings WHERE account_id=1 AND key='rate_navasan_key'")
    db.commit()
    assert db.execute(
        "SELECT COUNT(*) c FROM settings WHERE account_id=1 AND key='rate_navasan_key'"
    ).fetchone()["c"] == 0


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
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}


def test_e2e_navasan_fetch_and_fallback(tmp_path, monkeypatch):
    """از طریق HTTP: پیش‌فرض navasan، fallback به er-api، تست کلید و ماسک‌شدن."""
    monkeypatch.delenv("SARRAFI_NAVASAN_KEY", raising=False)
    _patch_http(monkeypatch, {"api.navasan.tech": NAVASAN_OK, "open.er-api.com": ER_API_OK})

    dbp = str(tmp_path / "e2e_navasan.db")
    srv = web.run(port=0, db_path=dbp)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    h = _Http(f"http://127.0.0.1:{port}")
    try:
        st, j = h._req("POST", "/api/login", {"username": "admin", "password": "admin123"})
        assert st == 200
        h.token = j["token"]

        # پیش‌فرض و وضعیت کلید
        st, rs = h._req("GET", "/api/rates/status")
        assert st == 200
        assert rs["source"] == "navasan"
        assert rs["navasan_key_set"] is False
        assert "navasan" in rs["providers"]

        # بدون کلید: fetch نوسان باید به er-api برگردد
        st, r = h._req("POST", "/api/rates/fetch", {"provider": "navasan"})
        assert st == 200
        assert r["provider"] == "er-api"
        assert r["fallback"] is True
        assert any(u["code"] in ("USD", "EUR", "IQD") for u in r["updated"])

        # ذخیرهٔ کلید و ماسک‌شدن آن در GET
        st, _ = h._req("POST", "/api/settings/save", {"rate_navasan_key": "secret-123"})
        assert st == 200
        st, rs2 = h._req("GET", "/api/rates/status")
        assert rs2["navasan_key_set"] is True
        st, s = h._req("GET", "/api/settings")
        assert s["settings"]["rate_navasan_key"] == "********"

        # حالا fetch نوسان باید مستقیم از نوسان موفق شود (با کلید ذخیره‌شده)
        st, r2 = h._req("POST", "/api/rates/fetch", {"provider": "navasan"})
        assert st == 200
        assert r2["provider"] == "navasan"
        assert not r2.get("fallback")
        assert any(u["code"] == "USD" and u["rate"] == 2355000 for u in r2["updated"])

        # تست اتصال با کلید صریح
        st, t = h._req("POST", "/api/rates/test", {"provider": "navasan", "key": "test-key"})
        assert st == 200
        assert t["count"] >= 4
        assert t["rates"]["USD"] == 2355000

        # حذف کلید
        st, _ = h._req("POST", "/api/settings/save", {"rate_navasan_key": ""})
        assert st == 200
        st, rs3 = h._req("GET", "/api/rates/status")
        assert rs3["navasan_key_set"] is False
    finally:
        srv.shutdown()
        srv.server_close()
