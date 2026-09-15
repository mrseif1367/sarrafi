# -*- coding: utf-8 -*-
"""
سرور وب سیستم صرافی — HTTP + JSON API + صفحات (چندمشترکی)

اجرا:
    python run.py
"""

import json
import os
import re
import shutil
import glob
import threading
import time
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import schema, finance, seed, util, auth, context, rates, oauth, report_pdf, ocr, totp
from . import vision as vision_mod
from . import crypto as crypto_mod
from . import mailer
from . import permissions

# نسخه‌ی برنامه (منبع یکتا — در /api/health هم همین استفاده می‌شود)
VERSION = "0.9.2"

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

AUTH_REQUIRED = os.environ.get("SARRAFI_AUTH_REQUIRED", "0") == "1"
START_TIME = datetime.datetime.now()

# ---------------- محدودسازی نرخ (in-memory) ----------------
_RATE_LIMITS = {}   # key -> [timestamps]
_RATE_LOCK = threading.Lock()


def _rate_check(key, max_req, window_sec):
    """اجازه‌ی عبور بر اساس پنجره‌ی لغزان؛ False یعنی محدود شد."""
    now = time.time()
    with _RATE_LOCK:
        hits = [t for t in _RATE_LIMITS.get(key, []) if now - t < window_sec]
        if len(hits) >= max_req:
            _RATE_LIMITS[key] = hits
            return False
        hits.append(now)
        _RATE_LIMITS[key] = hits
        return True

def reset_rate_limits():
    """پاک‌کردن پنجره‌ی محدودیت نرخ — برای تست‌ها و راه‌اندازی مجدد سرویس."""
    with _RATE_LOCK:
        _RATE_LIMITS.clear()


ROLE_PERMS = permissions.ROLE_PERMS
ROLE_FA = permissions.ROLE_FA

EXPORT_TABLES = ["accounts", "users", "currencies", "exchange_rates", "parties",
                 "cashboxes", "cashbox_opening", "journal", "transactions", "invoices",
                 "payments", "payment_allocations", "loans", "expense_categories",
                 "expenses", "incomes", "banknotes", "banknote_images",
                 "banknote_batches", "banknote_movements", "settings", "audit_log",
                 "plans", "billing", "login_attempts",
                 "account_modules", "user_modules", "role_permissions"]

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _json_bytes(obj, status=200):
    body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def _can(user, perm):
    """بررسی مجوز کاربر. اولویت: ماتریس ذخیره‌شده (user['_perms']) سپس پیش‌فرض نقش."""
    if user.get("role") == "super_admin":
        return True
    if "_perms" in user:
        perms = user["_perms"]
        return "all" in perms or perm in perms
    perms = ROLE_PERMS.get(user["role"], {})
    return perms.get("all") or perms.get(perm)


def _module_blocked(user, path):
    """اگر endpoint به ماژولِ خاموشی وابسته باشد، پیام خطا برمی‌گرداند."""
    if user.get("role") == "super_admin":
        return None
    if "_modules" not in user:
        return None
    for mod, endpoints in permissions.MODULE_ENDPOINTS.items():
        if path in endpoints and not user["_modules"].get(mod, True):
            return {"error": f"قابلیت «{permissions.module_name(mod)}» برای شما غیرفعال است"}, 403
    return None


def _db(handler):
    return schema.get_connection()


def _body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def export_all(conn):
    out = {"app": "sarrafi", "schema_version": schema.SCHEMA_VERSION,
           "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "tables": {}}
    for t in EXPORT_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            out["tables"][t] = [dict(r) for r in rows]
        except Exception:
            out["tables"][t] = []
    return out


def _backup_passphrase():
    """عبارت عبور رمزنگاری بکاپ از متغیر محیطی یا تنظیمات سراسری."""
    env = os.environ.get("SARRAFI_BACKUP_PASSPHRASE", "").strip()
    if env:
        return env
    try:
        conn = schema.get_connection()
        try:
            r = conn.execute("SELECT value FROM settings WHERE account_id=0 AND key='backup_passphrase'").fetchone()
            return (r["value"] if r and r["value"] else "")
        finally:
            conn.close()
    except Exception:
        return ""


def _write_backup(conn, fname):
    """نوشتن بکاپ (JSON رمزنگاری‌شده در صورت تنظیم عبارت عبور)."""
    data = export_all(conn)
    raw = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    passphrase = _backup_passphrase()
    if passphrase:
        raw = crypto_mod.encrypt(raw, passphrase)
        fname += ".enc"
    with open(os.path.join(BACKUP_DIR, fname), "wb") as f:
        f.write(raw)
    return fname


def _auto_backup_loop(interval_hours):
    while True:
        time.sleep(interval_hours * 3600)
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            conn = schema.get_connection()
            try:
                _write_backup(conn, f"auto-{stamp}.json")
            finally:
                conn.close()
            # پاکسازی بکاپ‌های قدیمی (نگه‌داشتن ۲۰ نسخه اخیر)
            files = sorted(glob.glob(os.path.join(BACKUP_DIR, "auto-*.json*")),
                           key=os.path.getmtime, reverse=True)
            for old in files[20:]:
                try:
                    os.remove(old)
                except OSError:
                    pass
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "Sarrafi/0.8"

    def log_message(self, fmt, *args):
        pass

    # ---------- پاسخ ----------
    def _send(self, status, body, ctype, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token, X-Account-Id")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        s, b, c = _json_bytes(obj, status)
        self._send(s, b, c)

    def _redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _static(self, path):
        rel = path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        fp = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not fp.startswith(STATIC_DIR) or not os.path.isfile(fp):
            self._send(404, b"not found", "text/plain")
            return
        ext = os.path.splitext(fp)[1].lower()
        with open(fp, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def _serve_data_file(self, rel, base):
        fp = os.path.normpath(os.path.join(base, rel))
        if not fp.startswith(base) or not os.path.isfile(fp):
            self._send(404, b"not found", "text/plain")
            return
        ext = os.path.splitext(fp)[1].lower()
        with open(fp, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    # ---------- احراز ----------
    def _current_user(self):
        conn = _db(self)
        try:
            token = self.headers.get("X-Token")
            if token:
                s = conn.execute(
                    """SELECT s.expires_at, s.impersonated_by, u.* FROM sessions s
                       JOIN users u ON u.id=s.user_id WHERE s.token=?""", (token,)).fetchone()
                if s and not auth.is_expired(s["expires_at"]) and s["is_active"]:
                    conn.execute("UPDATE sessions SET last_seen=? WHERE token=?",
                                 (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), token))
                    conn.commit()
                    u = dict(s)
                    u.pop("password_hash", None)
                    return u
            if AUTH_REQUIRED:
                return {"id": 0, "full_name": "مهمان", "role": "guest", "account_id": None}
            u = conn.execute("SELECT * FROM users WHERE username='root'").fetchone()
            if u:
                return dict(u)
            u = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
            return dict(u) if u else {"id": 0, "full_name": "دمو", "role": "admin", "account_id": 1}
        finally:
            conn.close()

    def _setup_context(self, user):
        """ایزوله‌کردن داده بر اساس حساب کاربر؛ سوپرادمین با هدر X-Account-Id"""
        aid = user.get("account_id") or 0
        if user.get("role") == "super_admin":
            h = self.headers.get("X-Account-Id")
            if h:
                aid = int(h)
            else:
                # بدون انتخاب حساب: پیش‌فرض اولین مشترک تا فرم‌ها/کمبوها خالی نمانند
                conn = _db(self)
                try:
                    first = conn.execute("SELECT id FROM accounts ORDER BY id LIMIT 1").fetchone()
                    aid = first["id"] if first else 0
                finally:
                    conn.close()
        context.set_account(aid)
        context.set_user(user.get("id") or 0)
        return aid

    def _hydrate(self, user, conn):
        """محاسبه و الصاق مجوزها و فلگ ماژول‌های مؤثر به شیء کاربر."""
        user["_perms"] = permissions.effective_perm_set(conn, user)
        user["_modules"] = permissions.effective_modules(conn, user)
        return user

    def _audit_add(self, conn, user_id, action, entity, entity_id, detail):
        conn.execute(
            "INSERT INTO audit_log(account_id,user_id,action,entity,entity_id,detail) VALUES (?,?,?,?,?,?)",
            (context.get_account(), user_id, action, entity, str(entity_id) if entity_id is not None else None, detail))

    def _guard_suspended(self, user, conn):
        """مشترک معلق (غیر سوپرادمین) اجازه‌ی هیچ عملیاتی ندارد"""
        if user.get("role") == "super_admin":
            return None
        aid = user.get("account_id")
        if not aid:
            return None
        acc = conn.execute("SELECT status, deleted_at FROM accounts WHERE id=?", (aid,)).fetchone()
        if acc and (acc["status"] == "suspended" or acc["deleted_at"]):
            return {"error": "حساب شما معلق یا حذف شده است — با پشتیبانی تماس بگیرید"}, 403
        return None

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._static("index.html")
            return
        if path == "/landing":
            self._static("landing.html")
            return
        if path.startswith("/static/"):
            self._static(path)
            return
        if path.startswith("/uploads/"):
            self._serve_data_file(path[len("/uploads/"):], UPLOAD_DIR)
            return
        if path == "/favicon.ico":
            self._static("img/logo.svg")
            return
        if path == "/api/auth/google/url":
            self._google_url()
            return
        if path == "/api/auth/google/callback":
            self._google_callback(qs)
            return
        if path.startswith("/api/"):
            self._api_get(path, qs)
            return
        self._static("index.html")

    def _api_get(self, path, qs):
        user = self._current_user()
        self._setup_context(user)
        conn = _db(self)
        try:
            self._hydrate(user, conn)
            blocked = self._guard_suspended(user, conn)
            if blocked is not None and path not in ("/api/me", "/api/health"):
                self._json(blocked[0], blocked[1])
                return
            blk = _module_blocked(user, path)
            if blk is not None:
                self._json(blk[0], blk[1])
                return
            if path == "/api/me":
                self._json(self._me(conn, user))
            elif path == "/api/dashboard":
                self._json(self._dashboard(conn, user))
            elif path == "/api/accounts":
                if user["role"] != "super_admin":
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                self._json(self._accounts(conn, user))
            elif path == "/api/users":
                if user["role"] not in ("super_admin", "admin"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                self._json(self._users(conn, user))
            elif path == "/api/currencies":
                self._json({"items": [dict(r) for r in conn.execute(
                    "SELECT * FROM currencies WHERE is_active=1 AND deleted_at IS NULL ORDER BY sort_order,id").fetchall()]})
            elif path == "/api/currencies/all":
                if user["role"] != "super_admin":
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                self._json({"items": [dict(r) for r in conn.execute(
                    "SELECT * FROM currencies ORDER BY sort_order,id").fetchall()]})
            elif path == "/api/parties":
                limit = int(qs.get("limit", [1000])[0])
                page = int(qs.get("page", [1])[0])
                off = max(0, (page - 1) * limit)
                total = conn.execute("SELECT COUNT(*) c FROM parties WHERE account_id=? AND deleted_at IS NULL",
                                     (context.get_account(),)).fetchone()["c"]
                self._json({"items": [dict(r) for r in conn.execute(
                    """SELECT p.*, (SELECT COUNT(*) FROM invoices i WHERE i.party_id=p.id AND i.deleted_at IS NULL) invoice_count
                       FROM parties p WHERE p.account_id=? AND p.deleted_at IS NULL ORDER BY p.id DESC LIMIT ? OFFSET ?""",
                    (context.get_account(), limit, off)).fetchall()],
                    "total": total, "page": page, "limit": limit})
            elif path == "/api/party":
                self._json(self._party_detail(conn, int(qs.get("id", [0])[0])))
            elif path == "/api/cashboxes":
                self._json({"items": self._cashboxes(conn)})
            elif path == "/api/batches":
                self._json({"items": self._batches(conn, qs)})
            elif path == "/api/search":
                self._json(self._search(conn, qs.get("q", [""])[0]))
            elif path == "/api/invoices":
                limit = int(qs.get("limit", [100])[0])
                page = int(qs.get("page", [1])[0])
                off = max(0, (page - 1) * limit)
                total = conn.execute("SELECT COUNT(*) c FROM invoices WHERE account_id=? AND deleted_at IS NULL",
                                     (context.get_account(),)).fetchone()["c"]
                self._json({"items": [dict(r) for r in conn.execute(
                    """SELECT i.*, p.full_name party_name, c.code currency_code, c.decimals, c.unit_ratio
                       FROM invoices i JOIN parties p ON p.id=i.party_id
                       JOIN currencies c ON c.id=i.currency_id
                       WHERE i.account_id=? AND i.deleted_at IS NULL ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (context.get_account(), limit, off)).fetchall()],
                    "total": total, "page": page, "limit": limit})
            elif path == "/api/invoice":
                self._json(self._invoice_detail(conn, int(qs.get("id", [0])[0])))
            elif path == "/api/debts":
                self._json(self._debts(conn))
            elif path == "/api/loans":
                self._json({"items": self._loans(conn)})
            elif path == "/api/banknotes":
                self._json(self._banknotes(conn, qs))
            elif path == "/api/banknotes/available":
                if not _can(user, "banknote"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                self._json({"items": finance.list_available_banknotes(
                    conn, currency_id=qs.get("currency_id", [None])[0],
                    denomination=qs.get("denomination", [None])[0],
                    q=qs.get("q", [None])[0])})
            elif path == "/api/banknote":
                self._json(self._banknote_detail(conn, qs.get("id", [None])[0]))
            elif path == "/api/expenses":
                kind = qs.get("kind", ["expense"])[0]
                tbl = "expenses" if kind == "expense" else "incomes"
                self._json({"items": [dict(r) for r in conn.execute(
                    f"""SELECT e.*, c.code, c.decimals, c.unit_ratio, ec.name category
                        FROM {tbl} e JOIN currencies c ON c.id=e.currency_id
                        LEFT JOIN expense_categories ec ON ec.id=e.category_id
                        WHERE e.account_id=? AND e.deleted_at IS NULL ORDER BY e.id DESC LIMIT 200""",
                    (context.get_account(),)).fetchall()]})
            elif path == "/api/transactions":
                limit = int(qs.get("limit", [100])[0])
                page = int(qs.get("page", [1])[0])
                off = max(0, (page - 1) * limit)
                total = conn.execute("SELECT COUNT(*) c FROM transactions WHERE account_id=?",
                                     (context.get_account(),)).fetchone()["c"]
                self._json({"items": [dict(r) for r in conn.execute(
                    """SELECT t.*, j.jtype, j.title, j.ref_no, j.status,
                              c.code, c.decimals, c.unit_ratio, c.symbol,
                              cb.name cashbox_name, p.full_name party_name
                       FROM transactions t
                       JOIN journal j ON j.id=t.journal_id
                       JOIN currencies c ON c.id=t.currency_id
                       LEFT JOIN cashboxes cb ON cb.id=t.cashbox_id
                       LEFT JOIN parties p ON p.id=t.party_id
                       WHERE t.account_id=? ORDER BY t.id DESC LIMIT ? OFFSET ?""",
                    (context.get_account(), limit, off)).fetchall()],
                    "total": total, "page": page, "limit": limit})
            elif path == "/api/journal":
                self._json(self._journal_detail(conn, int(qs.get("id", [0])[0])))
            elif path == "/api/rates":
                rows = conn.execute(
                    """SELECT r.*, c.code, c.name, c.symbol, c.decimals, c.unit_ratio
                       FROM exchange_rates r JOIN currencies c ON c.id=r.currency_id
                       WHERE r.account_id=? AND r.rate_date=(SELECT MAX(rate_date) FROM exchange_rates r2
                           WHERE r2.currency_id=r.currency_id AND r2.account_id=?)
                       ORDER BY c.sort_order""",
                    (context.get_account(), context.get_account())).fetchall()
                # گروه‌بندی بر اساس نوع نرخ (چندنرخی: market/buy/sell/sana)
                by_type = {}
                for r in rows:
                    by_type.setdefault(r["rate_type"] or "market", []).append(dict(r))
                self._json({"items": [dict(r) for r in rows], "by_type": by_type})
            elif path == "/api/rates/status":
                self._json(self._rates_status(conn))
            elif path == "/api/report/cashbox":
                day = qs.get("day", [util.today_fa().replace("/", "-")])[0]
                cb = int(qs.get("cashbox", [1])[0])
                self._json(self._cashbox_report(conn, cb, day))
            elif path == "/api/report/profit":
                frm = qs.get("from", [None])[0]
                to = qs.get("to", [None])[0]
                self._json(self._profit_report(conn, frm, to))
            elif path == "/api/report/monthly":
                frm = qs.get("from", [None])[0]
                to = qs.get("to", [None])[0]
                if not frm or not to:
                    today = datetime.date.today()
                    frm = (today.replace(day=1)).strftime("%Y-%m-%d")
                    to = today.strftime("%Y-%m-%d")
                self._json(self._monthly_report(conn, frm, to))
            elif path == "/api/report/party":
                self._json(self._party_detail(conn, int(qs.get("id", [0])[0])))
            elif path == "/api/report/charts":
                frm = qs.get("from", [None])[0]
                to = qs.get("to", [None])[0]
                self._json(self._charts(conn, frm, to))
            elif path == "/api/lowstock":
                self._json({"items": finance.low_stock_alerts(conn)})
            elif path == "/api/forecast":
                self._json(finance.cashflow_forecast(conn, days=int(qs.get("days", [30])[0])))
            elif path == "/api/plans":
                self._json({"items": finance.plan_catalog()})
            elif path == "/api/billing":
                if user["role"] not in ("super_admin", "admin"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                rows = conn.execute(
                    """SELECT b.*, a.name account_name FROM billing b
                       JOIN accounts a ON a.id=b.account_id ORDER BY b.id DESC LIMIT 200""").fetchall()
                if user["role"] == "admin":
                    rows = [r for r in rows if r["account_id"] == user.get("account_id")]
                self._json({"items": [dict(r) for r in rows]})
            elif path == "/api/settings":
                rows = conn.execute("SELECT key,value FROM settings WHERE account_id=?",
                                    (context.get_account(),)).fetchall()
                s = {r["key"]: r["value"] for r in rows}
                # کلید API نوسان هرگز در پاسخ لو نمی‌رود
                if s.get("rate_navasan_key"):
                    s["rate_navasan_key"] = "********"
                self._json({"settings": s})
            elif path == "/api/modules":
                # فلگ‌های حساب هدف (سوپرادمین می‌تواند هر حسابی را ببیند)
                acct_q = context.get_account()
                if user["role"] == "super_admin" and qs.get("account_id"):
                    acct_q = int(qs.get("account_id", [0])[0])
                uid_q = None
                if qs.get("user_id"):
                    uid_q = int(qs.get("user_id", [0])[0])
                    tu = conn.execute("SELECT * FROM users WHERE id=?", (uid_q,)).fetchone()
                    if not tu:
                        uid_q = None
                    elif user["role"] == "admin" and tu["account_id"] != user.get("account_id"):
                        uid_q = None  # ادمین فقط کارمندان خودش را می‌بیند
                out = {"catalog": permissions.MODULES,
                       "account_id": acct_q,
                       "account_flags": permissions.account_module_flags(conn, acct_q),
                       "user_overrides": permissions.user_module_overrides(conn, uid_q) if uid_q else {},
                       "target_user_id": uid_q,
                       "effective": user.get("_modules", {}),
                       "can_edit_account": user["role"] in ("super_admin", "admin"),
                       "can_edit_users": user["role"] in ("super_admin", "admin"),
                       "is_super": user["role"] == "super_admin"}
                if user["role"] == "super_admin":
                    out["accounts"] = [dict(r) for r in conn.execute(
                        "SELECT id,name FROM accounts ORDER BY id").fetchall()]
                    out["users"] = [dict(r) for r in conn.execute(
                        "SELECT id,username,full_name,role,account_id FROM users ORDER BY account_id,id").fetchall()]
                elif user["role"] == "admin":
                    out["users"] = [dict(r) for r in conn.execute(
                        """SELECT id,username,full_name,role FROM users
                           WHERE account_id=? ORDER BY id""",
                        (context.get_account(),)).fetchall()]
                self._json(out)
            elif path == "/api/permissions":
                if user["role"] not in ("super_admin", "admin"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                acct_q = context.get_account()
                if user["role"] == "super_admin" and qs.get("account_id"):
                    acct_q = int(qs.get("account_id", [0])[0])
                self._json({"perms": permissions.PERMS,
                            "roles": permissions.EDITABLE_ROLES,
                            "role_fa": permissions.ROLE_FA,
                            "matrix": permissions.role_matrix(conn, acct_q),
                            "account_id": acct_q})
            elif path == "/api/report/pdf":
                frm = qs.get("from", [None])[0]
                to = qs.get("to", [None])[0]
                today = datetime.date.today()
                if not frm or not to:
                    frm = today.replace(day=1).strftime("%Y-%m-%d")
                    to = today.strftime("%Y-%m-%d")
                try:
                    data = report_pdf.generate(conn, frm, to, context.get_account())
                except Exception as e:
                    self._json({"error": f"تولید PDF ممکن نشد: {e}"}, 500)
                    return
                fname = f"sarrafi-report-{frm}-{to}.pdf"
                self._send(200, data, "application/pdf",
                           extra_headers={"Content-Disposition": f'attachment; filename="{fname}"'})
            elif path == "/api/audit":
                if not _can(user, "report"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                limit = int(qs.get("limit", [60])[0])
                self._json({"items": [dict(r) for r in conn.execute(
                    """SELECT a.*, u.full_name FROM audit_log a
                       LEFT JOIN users u ON u.id=a.user_id
                       WHERE a.account_id=? ORDER BY a.id DESC LIMIT ?""",
                    (context.get_account(), limit)).fetchall()]})
            elif path == "/api/delete/info":
                if not _can(user, "delete"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                typ = qs.get("type", [""])[0]
                eid = qs.get("id", [None])[0]
                self._json(finance.delete_preview(conn, typ, eid, actor=user))
            elif path == "/api/deleted":
                if not _can(user, "delete"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                self._json(finance.list_deleted(conn))
            elif path == "/api/backup/list":
                if not _can(user, "all"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                files = sorted(glob.glob(os.path.join(BACKUP_DIR, "*.db")) +
                               glob.glob(os.path.join(BACKUP_DIR, "*.json")),
                               key=os.path.getmtime, reverse=True)
                self._json({"items": [{"name": os.path.basename(f),
                                       "size": os.path.getsize(f),
                                       "mtime": os.path.getmtime(f)} for f in files]})
            elif path == "/api/backup/download":
                name = qs.get("file", [None])[0]
                if not name or not re.match(r"^[A-Za-z0-9_\-\.]+$", name):
                    self._json({"error": "نام نامعتبر"}, 400)
                    return
                fp = os.path.join(BACKUP_DIR, name)
                if not os.path.isfile(fp):
                    self._json({"error": "یافت نشد"}, 404)
                    return
                with open(fp, "rb") as f:
                    self._send(200, f.read(), "application/octet-stream")
            elif path == "/api/health":
                up = str(datetime.datetime.now() - START_TIME)
                self._json({"ok": True, "app": "sarrafi", "version": VERSION,
                            "db": schema.db_info(), "uptime": up,
                            "auth_required": AUTH_REQUIRED,
                            "ocr": ocr.available(),
                            "tesseract": ocr._tesseract_binary(),
                            "vision": vision_mod.available(),
                            "google": self._google_configured(conn),
                            "roles": list(ROLE_PERMS.keys())})
            elif path == "/api/export/all":
                if not _can(user, "all"):
                    self._json({"error": "دسترسی ندارید"}, 403)
                    return
                body = json.dumps(export_all(conn), ensure_ascii=False, default=str).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            elif path == "/api/export/csv":
                self._csv(conn, qs.get("type", ["transactions"])[0])
            elif path == "/api/export/xlsx":
                self._xlsx(conn, qs.get("type", ["transactions"])[0])
            else:
                self._json({"error": "not found"}, 404)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({"error": f"خطا: {e}"}, 500)
        finally:
            conn.close()

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # محدودسازی نرخ برای نقاط عمومی (ضد اسپم/brute-force در سطح HTTP)
        if path in ("/api/login", "/api/signup", "/api/password/forgot",
                    "/api/password/reset", "/api/ocr"):
            ip = self.client_address[0]
            if not _rate_check(f"{path}:{ip}", 20, 60):
                self._json({"error": "تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید"}, 429)
                return
        if path == "/api/login":
            self._login()
            return
        if path == "/api/signup":
            self._signup()
            return
        if path in ("/api/password/forgot", "/api/password/reset"):
            self._password_reset(path)
            return
        if not path.startswith("/api/"):
            self._json({"error": "not found"}, 404)
            return
        user = self._current_user()
        self._setup_context(user)
        data = _body(self)
        conn = _db(self)
        try:
            self._hydrate(user, conn)
            out = self._api_post(path, data, user, conn)
            if out is not None:
                if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], int):
                    self._json(out[0], out[1])
                else:
                    self._json(out)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({"error": f"خطا: {e}"}, 500)
        finally:
            conn.close()

    def _password_reset(self, path):
        """فراموشی / بازنشانی رمز عبور (بدون نیاز به ورود)"""
        data = _body(self)
        conn = _db(self)
        try:
            username = str(data.get("username", "")).strip()
            if not username:
                self._json({"error": "نام کاربری را وارد کنید"}, 400)
                return
            u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if path == "/api/password/forgot":
                if not u or not u["is_active"]:
                    # پاسخ عمومی برای جلوگیری از لو رفتن نام کاربری
                    self._json({"ok": True, "hint": "اگر نام کاربری معتبر باشد، کد بازیابی ساخته می‌شود"})
                    return
                if u["account_id"]:
                    acc = conn.execute("SELECT status FROM accounts WHERE id=?", (u["account_id"],)).fetchone()
                    if acc and acc["status"] == "suspended":
                        self._json({"error": "حساب معلق است؛ امکان بازیابی وجود ندارد"}, 403)
                        return
                code, ttl = auth.create_reset_code(conn, username)
                email = u["email"] or (username if "@" in username else None)
                sent = False
                if email:
                    try:
                        if mailer.configured(conn):
                            body = ("<div dir='rtl' style='font-family:sans-serif'>"
                                    f"<h3>بازیابی رمز عبور</h3><p>{u['full_name']} عزیز،</p>"
                                    f"<p>کد بازیابی شما: <b style='font-size:22px;letter-spacing:4px'>{code}</b></p>"
                                    f"<p>این کد تا {ttl} دقیقه معتبر است.</p></div>")
                            mailer.send(conn, email, "کد بازیابی رمز عبور", body)
                            sent = True
                    except Exception:
                        sent = False
                resp = {"ok": True, "ttl_minutes": ttl, "sent": sent,
                        "email": (email if sent else None)}
                if not sent:
                    # SMTP پیکربندی نشده → نمایش کد (حالت توسعه/دمو)
                    resp["code"] = code
                    resp["note"] = ("ایمیل ارسال نشد (SMTP پیکربندی نشده)؛ کد برای آزمایش "
                                    "در همین‌جا نمایش داده می‌شود.")
                else:
                    resp["note"] = "کد بازیابی به ایمیل شما ارسال شد."
                self._json(resp)
                return
            # /api/password/reset
            if not u:
                self._json({"error": "نام کاربری یا کد نامعتبر است"}, 400)
                return
            code = str(data.get("code", "")).strip()
            new_pass = str(data.get("new_password", ""))
            if len(new_pass) < 4:
                self._json({"error": "رمز جدید حداقل ۴ نویسه باشد"}, 400)
                return
            if not auth.consume_reset_code(conn, username, code):
                self._json({"error": "کد بازیابی نامعتبر یا منقضی شده است"}, 400)
                return
            auth.set_password(conn, u["id"], new_pass)
            auth.clear_attempts(conn, username)
            self._json({"ok": True, "message": "رمز عبور تغییر کرد؛ اکنون وارد شوید"})
        finally:
            conn.close()

    # ---------- احراز ----------
    def _login(self):
        data = _body(self)
        conn = _db(self)
        try:
            username = str(data.get("username", "")).strip()
            # قفل ورود (ضد brute-force)
            lock = auth.lockout_status(conn, username)
            if lock:
                self._json({"error": f"به دلیل تلاش‌های ناموفق، ورود برای {lock} ثانیه قفل است"},
                           429)
                return
            u = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1",
                             (username,)).fetchone()
            ok = u and u["password_hash"] and \
                auth.verify_password(str(data.get("password", "")), u["password_hash"])
            if ok:
                # بررسی وضعیت مشترک (حساب معلق نمی‌تواند وارد شود)
                if u["account_id"]:
                    acc = conn.execute("SELECT status, plan FROM accounts WHERE id=?",
                                       (u["account_id"],)).fetchone()
                    if acc and acc["status"] == "suspended":
                        self._json({"error": "حساب شما توسط مدیر سیستم معلق شده است"}, 403)
                        return
                # احراز دومرحله‌ای (در صورت فعال بودن)
                if u["totp_secret"]:
                    code = str(data.get("code", "")).strip()
                    if not code:
                        self._json({"error": "کد تأیید دومرحله‌ای را وارد کنید", "need_2fa": True}, 401)
                        return
                    if not totp.verify(u["totp_secret"], code):
                        self._json({"error": "کد تأیید دومرحله‌ای نامعتبر است", "need_2fa": True}, 401)
                        return
                auth.clear_attempts(conn, username)
                token = auth.new_token()
                conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)",
                             (token, u["id"], auth.expires_at()))
                conn.execute("DELETE FROM sessions WHERE user_id=? AND expires_at<?",
                             (u["id"], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                self._json({"token": token, "user": self._public_user(dict(u))})
            else:
                locked, _ = auth.register_failed_attempt(conn, username)
                if locked:
                    self._json({"error": "ورود ناموفق؛ حساب به مدت ۱۵ دقیقه قفل شد"}, 429)
                else:
                    self._json({"error": "نام کاربری یا رمز عبور اشتباه است"}, 401)
        finally:
            conn.close()

    def _signup(self):
        data = _body(self)
        conn = _db(self)
        try:
            name = str(data.get("name", "")).strip()
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
            if not name or not username or len(password) < 4:
                raise ValueError("نام، نام کاربری و رمز عبور (حداقل ۴ کاراکتر) الزامی است")
            if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                raise ValueError("این نام کاربری قبلاً ثبت شده است")
            cur = conn.execute(
                "INSERT INTO accounts(name,phone) VALUES (?,?) RETURNING id",
                (name, data.get("phone", "")))
            acct_id = cur.fetchone()["id"]
            cur = conn.execute(
                """INSERT INTO users(account_id,username,full_name,email,password_hash,role,is_owner)
                   VALUES (?,?,?,?,?,?,1) RETURNING id""",
                (acct_id, username, name, data.get("email") or None,
                 auth.hash_password(password), "admin"))
            uid = cur.fetchone()["id"]
            token = auth.new_token()
            conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)",
                         (token, uid, auth.expires_at()))
            conn.commit()
            self._json({"token": token, "user": {"id": uid, "username": username,
                                                 "full_name": name, "role": "admin",
                                                 "account_id": acct_id}})
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            self._json({"error": f"خطا: {e}"}, 500)
        finally:
            conn.close()

    def _public_user(self, u):
        u.pop("password_hash", None)
        out = {k: u.get(k) for k in ("id", "username", "full_name", "role", "account_id", "is_owner")}
        out["totp_enabled"] = bool(u.get("totp_secret"))
        return out

    def _google_configured(self, conn):
        try:
            return oauth.configured(conn)
        except Exception:
            return False

    def _google_url(self):
        conn = _db(self)
        try:
            redirect_uri = self._redirect_uri()
            u = oauth.auth_url(conn, redirect_uri)
            if not u:
                self._json({"configured": False})
                return
            self._json({"configured": True, "url": u[0]})
        finally:
            conn.close()

    def _google_callback(self, qs):
        code = qs.get("code", [None])[0]
        conn = _db(self)
        try:
            redirect_uri = self._redirect_uri()
            info = oauth.exchange_code(conn, code, redirect_uri)
            sub, email, name = info["sub"], info["email"], info["name"]
            u = conn.execute("SELECT * FROM users WHERE google_sub=?", (sub,)).fetchone()
            if not u:
                # حساب جدید + کاربر مالک
                acct_name = f"{name} ({email})"
                cur = conn.execute(
                    "INSERT INTO accounts(name) VALUES (?) RETURNING id", (acct_name,))
                acct_id = cur.fetchone()["id"]
                uname = email
                if conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone():
                    uname = "google_" + sub[:12]
                cur = conn.execute(
                    """INSERT INTO users(account_id,username,full_name,password_hash,google_sub,role,is_owner)
                       VALUES (?,?,?,NULL,?, 'admin', 1) RETURNING id""",
                    (acct_id, uname, name, sub))
                uid = cur.fetchone()["id"]
            else:
                uid = u["id"]
            token = auth.new_token()
            conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)",
                         (token, uid, auth.expires_at()))
            conn.commit()
            self._redirect(f"/?token={token}")
        except Exception as e:
            self._send(200, f"<html dir='rtl'><body style='font-family:sans-serif;padding:40px'>"
                            f"<h2>خطا در ورود با گوگل</h2><p>{e}</p></body></html>".encode(),
                       "text/html; charset=utf-8")
        finally:
            conn.close()

    def _redirect_uri(self):
        host = self.headers.get("Host", "localhost:8000")
        proto = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{proto}://{host}/api/auth/google/callback"

    def _logout(self):
        token = self.headers.get("X-Token")
        conn = _db(self)
        try:
            if token:
                conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                conn.commit()
            self._json({"ok": True})
        finally:
            conn.close()

    # ---------- POST API ----------
    def _api_post(self, path, d, user, conn):
        # مشترک معلق نمی‌تواند عملیات انجام دهد
        blocked = self._guard_suspended(user, conn)
        if blocked is not None and path not in ("/api/account/save",):
            return blocked
        # ماژول خاموش → endpoint مسدود
        blk = _module_blocked(user, path)
        if blk is not None:
            return blk

        # ---- مدیریت ارزها (سوپرادمین) ----
        if path == "/api/currency/save":
            if user["role"] != "super_admin":
                return {"error": "دسترسی ندارید"}, 403
            try:
                cid = finance.upsert_currency(conn, d)
            except ValueError as e:
                raise ValueError(str(e))
            return {"ok": True, "id": cid}

        # ---- ثبت گروهی اسکناس ----
        if path == "/api/banknote/bulk":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            serials = d.get("serials", [])
            if isinstance(serials, str):
                serials = [s for s in serials.splitlines() if s.strip()]
            if not serials:
                raise ValueError("حداقل یک سریال وارد کنید")
            r = finance.bulk_banknotes(
                conn, int(d["currency_id"]), int(d["denomination"]), serials,
                status=d.get("status", "in_vault"), cashbox_id=d.get("cashbox_id"),
                note=d.get("note", ""), user_id=user["id"],
                party_id=d.get("party_id"), movement_type=d.get("movement_type"))
            return r

        # ---- مدیریت حساب‌ها (سوپرادمین) ----
        if path == "/api/account/save":
            if user["role"] != "super_admin":
                return {"error": "دسترسی ندارید"}, 403
            aid = d.get("id")
            if aid:
                conn.execute("UPDATE accounts SET name=?, plan=?, status=?, phone=?, logo=? WHERE id=?",
                             (d.get("name", ""), d.get("plan", "free"),
                              d.get("status", "active"), d.get("phone", ""),
                              d.get("logo") or None, int(aid)))
                conn.commit()
                return {"ok": True, "id": int(aid)}
            cur = conn.execute(
                "INSERT INTO accounts(name,plan,status,phone,logo) VALUES (?,?,?,?,?) RETURNING id",
                (d.get("name", ""), d.get("plan", "free"),
                 d.get("status", "active"), d.get("phone", ""), d.get("logo") or None))
            new_aid = cur.fetchone()["id"]
            conn.commit()
            return {"ok": True, "id": new_aid}

        if path == "/api/account/logo":
            if user["role"] not in ("super_admin", "admin"):
                return {"error": "دسترسی ندارید"}, 403
            if user["role"] == "super_admin":
                target = int(d.get("account_id") or 0)
            else:
                target = context.get_account()
            acc = conn.execute("SELECT * FROM accounts WHERE id=?", (target,)).fetchone()
            if not acc:
                raise ValueError("حساب (مشترک) یافت نشد")
            b64 = d.get("data") or ""
            if b64:
                import base64
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                header, _, b64data = b64.partition(",")
                ext = ".png" if "png" in header else ".jpg"
                fname = f"acct_logo_{target}{ext}"
                fpath = os.path.join(UPLOAD_DIR, fname)
                with open(fpath, "wb") as f:
                    f.write(base64.b64decode(b64data))
                conn.execute("UPDATE accounts SET logo=? WHERE id=?", (f"uploads/{fname}", target))
            else:
                conn.execute("UPDATE accounts SET logo=NULL WHERE id=?", (target,))
            conn.commit()
            self._audit_add(conn, user["id"], "account_logo", "account", target, "تغییر لوگوی حساب")
            return {"ok": True, "logo": f"uploads/{fname}" if b64 else None}

        # ---- ورود به‌جای کاربر (impersonation) ----
        if path == "/api/impersonate":
            target_id = int(d["user_id"])
            t = conn.execute("SELECT * FROM users WHERE id=?", (target_id,)).fetchone()
            if not t:
                raise ValueError("کاربر یافت نشد")
            allowed = False
            if user["role"] == "super_admin":
                allowed = True
            elif user["role"] == "admin" and user.get("account_id") \
                    and user["account_id"] == t["account_id"]:
                allowed = True
            if not allowed:
                return {"error": "دسترسی ندارید"}, 403
            token = auth.new_token()
            conn.execute("INSERT INTO sessions(token,user_id,impersonated_by,expires_at) VALUES (?,?,?,?)",
                         (token, target_id, user["id"], auth.expires_at()))
            conn.commit()
            return {"ok": True, "token": token, "user": self._public_user(dict(t))}

        # ---- نرخ آنلاین ----
        if path == "/api/rates/fetch":
            if not _can(user, "rate"):
                return {"error": "دسترسی ندارید"}, 403
            preferred = d.get("provider") or self._get_setting(conn, "rate_source") or rates.DEFAULT_PROVIDER
            res = rates.fetch_with_fallback(preferred, api_key=self._navasan_key(conn))
            updated = rates.apply_to_db(conn, res, context.get_account())
            if not updated and not res.get("rates"):
                raise ValueError(res.get("note") or "این منبع نرخ ریالی ندارد — منبع دیگری را انتخاب کنید")
            conn.execute(
                """INSERT INTO settings(account_id,key,value) VALUES(?,?,?)
                   ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                (context.get_account(), "rate_source", preferred))
            conn.execute(
                """INSERT INTO settings(account_id,key,value) VALUES(?,?,?)
                   ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                (context.get_account(), "rate_last_fetch", datetime.datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            return {"ok": True, "provider": res["provider"], "source_name": res["source_name"],
                    "fetched_at": res["fetched_at"], "updated": updated,
                    "fallback": bool(res.get("fallback")), "tried": res.get("tried") or []}

        if path == "/api/rates/test":
            if not _can(user, "rate"):
                return {"error": "دسترسی ندارید"}, 403
            provider = d.get("provider") or "navasan"
            key = d.get("key") or self._navasan_key(conn)
            res = rates.fetch(provider, api_key=key)
            return {"ok": True, "provider": provider, "source_name": res["source_name"],
                    "count": len(res.get("rates") or {}),
                    "rates": {k: v for k, v in (res.get("rates") or {}).items() if k != "IRR"}}

        # ---- تنظیمات ----
        if path == "/api/settings/save":
            if not _can(user, "rate"):
                return {"error": "دسترسی ندارید"}, 403
            for k in ("rate_source", "rate_auto_refresh"):
                if k in d:
                    conn.execute(
                        """INSERT INTO settings(account_id,key,value) VALUES(?,?,?)
                           ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                        (context.get_account(), k, str(d[k])))
            # کلید نوسان: مقدار واقعی ذخیره می‌شود؛ «********» یعنی بدون تغییر؛ رشتهٔ خالی یعنی حذف کلید
            if "rate_navasan_key" in d:
                v = str(d.get("rate_navasan_key") or "").strip()
                if v and v not in ("********", "******"):
                    conn.execute(
                        """INSERT INTO settings(account_id,key,value) VALUES(?,?,?)
                           ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                        (context.get_account(), "rate_navasan_key", v))
                elif v == "":
                    conn.execute("DELETE FROM settings WHERE account_id=? AND key='rate_navasan_key'",
                                 (context.get_account(),))
            conn.commit()
            return {"ok": True}

        # ---- فلگ ماژول‌ها (امکانات قابل روشن/خاموش) ----
        if path == "/api/modules/save":
            flags = d.get("flags") or {}
            target_uid = d.get("user_id")
            if target_uid:
                if user["role"] not in ("super_admin", "admin"):
                    return {"error": "دسترسی ندارید"}, 403
                target = conn.execute("SELECT * FROM users WHERE id=?", (int(target_uid),)).fetchone()
                if not target:
                    raise ValueError("کاربر یافت نشد")
                if user["role"] == "admin" and target["account_id"] != user.get("account_id"):
                    return {"error": "دسترسی ندارید"}, 403
                permissions.save_user_modules(conn, int(target_uid), flags)
                self._audit_add(conn, user["id"], "modules_save_user", "users", target_uid,
                                json.dumps(flags, ensure_ascii=False))
            else:
                if user["role"] not in ("super_admin", "admin"):
                    return {"error": "دسترسی ندارید"}, 403
                acct = int(d.get("account_id") or context.get_account())
                if user["role"] == "admin":
                    acct = context.get_account()
                permissions.save_account_modules(conn, acct, flags)
                self._audit_add(conn, user["id"], "modules_save_account", "accounts", acct,
                                json.dumps(flags, ensure_ascii=False))
            conn.commit()
            return {"ok": True}

        # ---- ماتریس مجوز نقش‌ها ----
        if path == "/api/permissions/save":
            if user["role"] not in ("super_admin", "admin"):
                return {"error": "دسترسی ندارید"}, 403
            acct = context.get_account()
            if user["role"] == "super_admin" and d.get("account_id"):
                acct = int(d["account_id"])
            permissions.save_role_permissions(conn, acct, d.get("matrix") or {})
            self._audit_add(conn, user["id"], "permissions_save", "accounts", acct, "")
            conn.commit()
            return {"ok": True}

        # ---- احراز دومرحله‌ای (TOTP) ----
        if path == "/api/2fa/start":
            if user["role"] not in ("admin", "super_admin"):
                return {"error": "فقط مدیر و سوپرادمین می‌توانند 2FA فعال کنند"}, 403
            secret = totp.generate_secret()
            return {"secret": secret,
                    "url": totp.otpauth_url(secret, user["full_name"] or user["username"]),
                    "note": "کد را در Google Authenticator یا برنامه مشابه وارد کنید"}
        if path == "/api/2fa/confirm":
            if user["role"] not in ("admin", "super_admin"):
                return {"error": "دسترسی ندارید"}, 403
            secret = str(d.get("secret", "")).strip()
            code = str(d.get("code", "")).strip()
            if not secret or not totp.verify(secret, code):
                return {"error": "کد نامعتبر است — دوباره تلاش کنید"}, 400
            conn.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, user["id"]))
            conn.commit()
            self._audit_add(conn, user["id"], "2fa_enable", "users", user["id"], "فعال‌سازی 2FA")
            return {"ok": True, "message": "احراز دومرحله‌ای فعال شد ✔"}
        if path == "/api/2fa/disable":
            target = user["id"]
            if user["role"] == "super_admin" and d.get("user_id"):
                target = int(d["user_id"])
            row = conn.execute("SELECT totp_secret FROM users WHERE id=?", (target,)).fetchone()
            if not row or not row["totp_secret"]:
                return {"error": "2FA برای این کاربر فعال نیست"}, 400
            # برای غیرفعال‌کردن: کد فعلی یا رمز عبور لازم است (مگر سوپرادمین برای دیگری)
            if target == user["id"] or user["role"] != "super_admin":
                ok = totp.verify(row["totp_secret"], str(d.get("code", ""))) or \
                    (d.get("password") and auth.verify_password(str(d["password"]),
                                                                conn.execute("SELECT password_hash FROM users WHERE id=?", (target,)).fetchone()["password_hash"]))
                if not ok:
                    return {"error": "کد یا رمز عبور اشتباه است"}, 400
            conn.execute("UPDATE users SET totp_secret=NULL WHERE id=?", (target,))
            conn.commit()
            self._audit_add(conn, user["id"], "2fa_disable", "users", target, "غیرفعال‌سازی 2FA")
            return {"ok": True, "message": "احراز دومرحله‌ای غیرفعال شد"}

        # ---- تغییر رمز عبور شخصی ----
        if path == "/api/password/change":
            old = str(d.get("old_password", ""))
            new = str(d.get("new_password", ""))
            if len(new) < 4:
                raise ValueError("رمز جدید حداقل ۴ نویسه باشد")
            u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            if not u or not auth.verify_password(old, u["password_hash"]):
                return {"error": "رمز فعلی اشتباه است"}, 400
            auth.set_password(conn, u["id"], new)
            return {"ok": True, "message": "رمز عبور تغییر کرد"}

        # ---- هشدار کف موجودی (تنظیم حداقل برای هر ارز) ----
        if path == "/api/lowstock/save":
            if not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            acct = context.get_account()
            for k, v in (d.get("thresholds") or {}).items():
                code = re.sub(r"[^A-Z0-9]", "", str(k).upper())
                if not code:
                    continue
                try:
                    val = int(v or 0)
                except (ValueError, TypeError):
                    continue
                if val <= 0:
                    conn.execute("DELETE FROM settings WHERE account_id=? AND key=?",
                                 (acct, f"min_stock_{code}"))
                else:
                    conn.execute(
                        """INSERT INTO settings(account_id,key,value) VALUES(?,?,?)
                           ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                        (acct, f"min_stock_{code}", str(val)))
            conn.commit()
            return {"ok": True}

        # ---- گوگل (تنظیم توسط سوپرادمین) ----
        if path == "/api/google/save":
            if user["role"] != "super_admin":
                return {"error": "دسترسی ندارید"}, 403
            for k in ("google_client_id", "google_client_secret"):
                if d.get(k):
                    conn.execute(
                        """INSERT INTO settings(account_id,key,value) VALUES(0,?,?)
                           ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                        (k, d[k]))
            conn.commit()
            return {"ok": True}

        # ---- طرف حساب ----
        if path == "/api/party/save":
            if not _can(user, "party"):
                return {"error": "دسترسی ندارید"}, 403
            pid = d.get("id")
            fields = ["type", "full_name", "phone", "mobile", "national_id", "address",
                      "notes", "credit_limit", "is_active"]
            vals = [d.get(k) for k in fields]
            vals[-1] = int(vals[-1]) if vals[-1] is not None else 1
            vals[0] = vals[0] or "customer"
            try:
                vals[7] = int(vals[7]) if vals[7] not in (None, "") else None
            except (ValueError, TypeError):
                vals[7] = None
            if not d.get("full_name"):
                raise ValueError("نام طرف حساب الزامی است")
            if pid:
                conn.execute(
                    "UPDATE parties SET type=?,full_name=?,phone=?,mobile=?,national_id=?,address=?,notes=?,credit_limit=?,is_active=? WHERE id=? AND account_id=?",
                    (*vals, int(pid), context.get_account()))
                conn.commit()
                return {"ok": True, "id": int(pid)}
            cur = conn.execute(
                f"INSERT INTO parties(account_id,{','.join(fields)}) VALUES (?,{','.join(['?']*len(fields))}) RETURNING id",
                (context.get_account(), *vals))
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"ok": True, "id": new_id}

        # ---- کاربران ----
        if path == "/api/user/save":
            uid = d.get("id")
            if uid:
                target = conn.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
                if not target:
                    raise ValueError("کاربر یافت نشد")
                # فقط سوپرادمین یا ادمینِ همان حساب می‌تواند کارمندانش را مدیریت کند
                if user["role"] != "super_admin" and not (
                        user["role"] == "admin" and user.get("account_id")
                        and user["account_id"] == target["account_id"]):
                    return {"error": "دسترسی ندارید"}, 403
                role = d.get("role", target["role"])
                if role not in ROLE_PERMS:
                    raise ValueError("نقش نامعتبر است")
                conn.execute(
                    "UPDATE users SET username=?,full_name=?,email=?,role=?,is_active=? WHERE id=?",
                    (d.get("username", target["username"]), d.get("full_name", target["full_name"]),
                     d.get("email", target["email"]),
                     role, int(d.get("is_active", target["is_active"])), int(uid)))
                if d.get("password"):
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (auth.hash_password(str(d["password"])), int(uid)))
                conn.commit()
                return {"ok": True, "id": int(uid)}
            # کاربر جدید (کارمند)
            if user["role"] == "super_admin":
                acct = int(d.get("account_id") or 0)
            elif user["role"] == "admin" and user.get("account_id"):
                acct = user["account_id"]
            else:
                return {"error": "دسترسی ندارید"}, 403
            role = d.get("role", "operator")
            if role not in ROLE_PERMS:
                raise ValueError("نقش نامعتبر است")
            # محدودیت تعداد کاربر بر اساس پلن مشترک
            if acct:
                prow = conn.execute("SELECT plan FROM accounts WHERE id=?", (acct,)).fetchone()
                plan = prow["plan"] if prow else "free"
                lim = finance.plan_limits(plan)["users"]
                if lim:
                    cnt = conn.execute("SELECT COUNT(*) c FROM users WHERE account_id=?", (acct,)).fetchone()["c"]
                    if cnt >= lim:
                        raise ValueError(f"سقف کاربران پلن «{plan}» (حداکثر {lim} کاربر) پر شده است")
            cur = conn.execute(
                """INSERT INTO users(account_id,username,full_name,email,password_hash,role,is_active)
                   VALUES (?,?,?,?,?,?,?) RETURNING id""",
                (acct, d.get("username"), d.get("full_name"), d.get("email") or None,
                 auth.hash_password(str(d.get("password", "1234"))),
                 role, int(d.get("is_active", 1))))
            new_uid = cur.fetchone()["id"]
            conn.commit()
            return {"ok": True, "id": new_uid}

        # ---- خرید / فروش / قرض / ... ----
        if path == "/api/buy":
            if not _can(user, "buy"):
                return {"error": "دسترسی ندارید"}, 403
            fee_minor = tax_minor = 0
            if user.get("_modules", {}).get("fee_tax", True):
                fee_minor = int(d.get("fee_minor") or 0)
                tax_minor = int(d.get("tax_minor") or 0)
            r = finance.buy_currency(
                conn, int(d["party_id"]), int(d["currency_id"]), int(d["amount"]), int(d["rate"]),
                int(d.get("cashbox") or 1), int(d.get("cashbox") or 1),
                description=d.get("description", ""), user_id=user["id"],
                confirm=bool(d.get("confirm", True)), payment_method=d.get("method", "cash"),
                fee_minor=fee_minor, tax_minor=tax_minor,
                rate_type=d.get("rate_type") or "market")
            return {"ok": True, "invoice_no": r["invoice_no"], "rial_value": r["rial_value"],
                    "total_rial": r.get("total_rial"), "fee_rial": r.get("fee_rial"),
                    "tax_rial": r.get("tax_rial"),
                    "invoice_id": r.get("invoice_id"), "journal_id": r.get("journal_id")}

        if path == "/api/sell":
            if not _can(user, "sell"):
                return {"error": "دسترسی ندارید"}, 403
            allow_neg = bool(d.get("allow_negative")) and _can(user, "all")
            fee_minor = tax_minor = 0
            if user.get("_modules", {}).get("fee_tax", True):
                fee_minor = int(d.get("fee_minor") or 0)
                tax_minor = int(d.get("tax_minor") or 0)
            r = finance.sell_currency(
                conn, int(d["party_id"]), int(d["currency_id"]), int(d["amount"]), int(d["rate"]),
                int(d.get("cashbox") or 1), int(d.get("cashbox") or 1),
                description=d.get("description", ""), user_id=user["id"],
                confirm=bool(d.get("confirm", True)), payment_method=d.get("method", "cash"),
                allow_negative=allow_neg,
                fee_minor=fee_minor, tax_minor=tax_minor,
                rate_type=d.get("rate_type") or "market")
            credit = None
            if d.get("method") == "later":
                credit = finance.party_credit_check(conn, int(d["party_id"]),
                                                    extra_rial=int(r.get("total_rial") or 0))
            return {"ok": True, "invoice_no": r["invoice_no"], "rial_value": r["rial_value"],
                    "total_rial": r.get("total_rial"), "fee_rial": r.get("fee_rial"),
                    "tax_rial": r.get("tax_rial"), "credit": credit,
                    "invoice_id": r.get("invoice_id"), "journal_id": r.get("journal_id")}

        if path == "/api/loan/receive":
            if not _can(user, "loan"):
                return {"error": "دسترسی ندارید"}, 403
            finance.loan_receive(conn, int(d["party_id"]), int(d["currency_id"]),
                                 int(d["amount"]), int(d["rate"]), int(d.get("cashbox") or 1),
                                 d.get("description", ""), user_id=user["id"],
                                 due_date=d.get("due_date"))
            return {"ok": True}
        if path == "/api/loan/give":
            if not _can(user, "loan"):
                return {"error": "دسترسی ندارید"}, 403
            finance.loan_give(conn, int(d["party_id"]), int(d["currency_id"]),
                              int(d["amount"]), int(d["rate"]), int(d.get("cashbox") or 1),
                              d.get("description", ""), user_id=user["id"],
                              allow_negative=_can(user, "all"),
                              due_date=d.get("due_date"))
            return {"ok": True}
        if path == "/api/loan/repay":
            if not _can(user, "loan"):
                return {"error": "دسترسی ندارید"}, 403
            loan = conn.execute("SELECT * FROM loans WHERE id=? AND account_id=?",
                                (int(d["loan_id"]), context.get_account())).fetchone()
            if not loan:
                raise ValueError("قرض یافت نشد")
            finance.loan_repay(conn, int(d["loan_id"]), loan["currency_id"],
                               int(d["amount"]), int(d["rate"]), int(d.get("cashbox") or 1),
                               d.get("description", ""), user_id=user["id"],
                               allow_negative=_can(user, "all"))
            return {"ok": True}

        if path == "/api/payment":
            if not _can(user, "loan"):
                return {"error": "دسترسی ندارید"}, 403
            finance.register_payment(
                conn, int(d["party_id"]), d["direction"], int(d["currency_id"]),
                int(d["amount"]), int(d["rate"]), int(d.get("cashbox") or 1),
                method=d.get("method", "cash"), description=d.get("description", ""),
                user_id=user["id"])
            return {"ok": True}

        if path == "/api/transfer":
            if not _can(user, "transfer"):
                return {"error": "دسترسی ندارید"}, 403
            finance.transfer(conn, int(d["from"]), int(d["to"]), int(d["currency_id"]),
                             int(d["amount"]), int(d["rate"]), d.get("description", ""),
                             user_id=user["id"], allow_negative=_can(user, "all"))
            return {"ok": True}

        if path == "/api/expense":
            if not _can(user, "expense"):
                return {"error": "دسترسی ندارید"}, 403
            finance.add_expense(conn, d["title"], int(d["currency_id"]), int(d["amount"]),
                                int(d["rate"]), int(d.get("cashbox") or 1),
                                category_id=d.get("category_id"), description=d.get("description", ""),
                                user_id=user["id"])
            return {"ok": True}
        if path == "/api/income":
            if not _can(user, "income"):
                return {"error": "دسترسی ندارید"}, 403
            finance.add_income(conn, d["title"], int(d["currency_id"]), int(d["amount"]),
                               int(d["rate"]), int(d.get("cashbox") or 1),
                               category_id=d.get("category_id"), description=d.get("description", ""),
                               user_id=user["id"])
            return {"ok": True}

        if path == "/api/adjust":
            if not _can(user, "adjust"):
                return {"error": "دسترسی ندارید"}, 403
            finance.adjust_cashbox(conn, int(d["cashbox"]), int(d["currency_id"]),
                                   int(d["amount"]), int(d["rate"]), reason=d.get("reason", ""),
                                   user_id=user["id"], allow_negative=_can(user, "all"))
            return {"ok": True}

        if path == "/api/void":
            if not _can(user, "void"):
                return {"error": "دسترسی ندارید"}, 403
            finance.void_journal(conn, int(d["journal_id"]), d.get("reason", ""), user_id=user["id"])
            return {"ok": True}

        if path == "/api/delete":
            if not _can(user, "delete"):
                return {"error": "دسترسی ندارید"}, 403
            return finance.delete_entity(conn, d.get("type", ""), int(d["id"]),
                                         user_id=user["id"], self_id=user["id"])

        if path == "/api/restore":
            if not _can(user, "delete"):
                return {"error": "دسترسی ندارید"}, 403
            return finance.restore_entity(conn, d.get("type", ""), int(d["id"]), user_id=user["id"])

        if path == "/api/rate":
            if not _can(user, "rate"):
                return {"error": "دسترسی ندارید"}, 403
            today = datetime.date.today().strftime("%Y-%m-%d")
            rate_type = d.get("rate_type") or "market"
            if rate_type not in ("market", "buy", "sell", "sana"):
                raise ValueError("نوع نرخ نامعتبر است")
            conn.execute(
                """INSERT INTO exchange_rates(account_id,currency_id,rate,rate_date,rate_type,source)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(account_id,currency_id,rate_date,rate_type)
                   DO UPDATE SET rate=excluded.rate, source='manual'""",
                (context.get_account(), int(d["currency_id"]), int(d["rate"]), today,
                 rate_type, "manual"))
            conn.commit()
            return {"ok": True}

        if path == "/api/banknote/attach":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            ids = d.get("ids") or []
            if isinstance(ids, (int, str)):
                ids = [ids]
            r = finance.attach_banknotes(
                conn, ids, invoice_id=d.get("invoice_id"), journal_id=d.get("journal_id"),
                party_id=d.get("party_id"), movement_type=d.get("movement_type"),
                cashbox_id=d.get("cashbox_id"), user_id=user["id"])
            return {"ok": True, **r}

        if path == "/api/banknote/detach":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            return finance.detach_banknote(conn, d["id"], user_id=user["id"])

        if path == "/api/banknote/save":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            cid = int(d["currency_id"])
            denom = int(d["denomination"])
            serial = str(d["serial"]).strip().upper()
            if not serial:
                raise ValueError("شماره سریال الزامی است")
            dup = conn.execute(
                "SELECT id,serial FROM banknotes WHERE account_id=? AND currency_id=? AND denomination=? AND serial=?",
                (context.get_account(), cid, denom, serial)).fetchone()
            if dup and not d.get("force"):
                return {"duplicate": True, "id": dup["id"]}
            cur = conn.execute(
                """INSERT INTO banknotes(account_id,currency_id,denomination,serial,status,cashbox_id,note)
                   VALUES (?,?,?,?,?,?,?) RETURNING id""",
                (context.get_account(), cid, denom, serial, d.get("status", "in_vault"),
                 d.get("cashbox_id") or None, d.get("note", "")))
            new_id = cur.fetchone()["id"]
            conn.commit()
            if d.get("party_id") and d.get("movement_type"):
                conn.execute(
                    """INSERT INTO banknote_movements(account_id,banknote_id,movement_type,party_id,from_cashbox,to_cashbox,note)
                       VALUES (?,?,?,?,?,?,?)""",
                    (context.get_account(), new_id, d.get("movement_type"), int(d["party_id"]),
                     None if d.get("movement_type") == "purchase" else d.get("cashbox_id"),
                     d.get("cashbox_id") if d.get("movement_type") == "purchase" else None,
                     d.get("note", "")))
                conn.commit()
            return {"ok": True, "id": new_id}

        if path == "/api/banknote/photo":
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            bn_id = int(d["banknote_id"])
            b64 = d.get("data", "")
            if not b64:
                raise ValueError("تصویری ارسال نشده")
            import base64
            header, _, b64data = b64.partition(",")
            ext = ".jpg"
            if "png" in header:
                ext = ".png"
            fname = f"bn_{bn_id}_{int(datetime.datetime.now().timestamp())}{ext}"
            fpath = os.path.join(UPLOAD_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(b64data))
            conn.execute(
                "INSERT INTO banknote_images(account_id,banknote_id,file_path,mime,note,meta) VALUES (?,?,?,?,?,?)",
                (context.get_account(), bn_id, f"uploads/{fname}",
                 header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg",
                 d.get("note", ""),
                 json.dumps(d.get("meta") or {}, ensure_ascii=False) if d.get("meta") else None))
            conn.commit()
            return {"ok": True, "file": f"uploads/{fname}"}

        if path == "/api/ocr":
            from . import ocr
            b64 = d.get("data", "")
            if not b64:
                raise ValueError("تصویری ارسال نشده")
            import base64
            _, _, b64data = b64.partition(",")
            if not ocr.available():
                return {"available": False, "suggestions": [],
                        "message": "موتور OCR روی سرور نصب نیست — سریال را دستی وارد کنید."}
            try:
                return ocr.read_serial(base64.b64decode(b64data))
            except Exception as e:
                return {"available": True, "suggestions": [], "message": f"خطای OCR: {e}"}

        if path == "/api/import":
            if not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            data = d.get("data")
            if not isinstance(data, dict):
                raise ValueError("داده نامعتبر است")
            self._import_all(conn, data)
            return {"ok": True}

        if path == "/api/backup":
            if not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            if schema.engine() == "postgres":
                fname = _write_backup(conn, f"sarrafi-{stamp}.json")
                self._json({"ok": True, "file": fname,
                            "encrypted": _backup_passphrase() != ""})
            else:
                fname = f"sarrafi-{stamp}.db"
                dst = os.path.join(BACKUP_DIR, fname)
                src = schema.DB_PATH
                conn.commit()
                shutil.copy2(src, dst)
                # رمزنگاری نسخه‌ی sqlite در صورت تنظیم عبارت عبور
                encrypted = False
                pp = _backup_passphrase()
                if pp:
                    with open(dst, "rb") as f:
                        blob = crypto_mod.encrypt(f.read(), pp)
                    with open(dst + ".enc", "wb") as f:
                        f.write(blob)
                    os.remove(dst)
                    fname += ".enc"
                    encrypted = True
                self._json({"ok": True, "file": fname, "encrypted": encrypted})
            return None

        if path == "/api/backup/passphrase":
            if not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            pp = str(d.get("passphrase", ""))
            if pp:
                conn.execute(
                    """INSERT INTO settings(account_id,key,value) VALUES(0,'backup_passphrase',?)
                       ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                    (pp,))
            else:
                conn.execute("DELETE FROM settings WHERE account_id=0 AND key='backup_passphrase'")
            conn.commit()
            return {"ok": True, "encrypted": bool(pp)}

        if path == "/api/backup/restore":
            if not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            b64 = d.get("data", "")
            if not b64:
                raise ValueError("فایل بکاپ ارسال نشده")
            import base64
            _hdr, _, _b = b64.partition(",")
            raw = base64.b64decode(_b)
            pp = str(d.get("passphrase", ""))
            try:
                if raw.startswith(b"SRFENC01"):
                    raw = crypto_mod.decrypt(raw, pp)
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return {"error": f"بازیابی ناموفق: {e}"}, 400
            self._import_all(conn, data)
            return {"ok": True}

        # ---- مدیریت صندوق (تعریف/نام‌گذاری توسط کاربر) ----
        if path == "/api/cashbox/save":
            if not _can(user, "cashbox_manage") and not _can(user, "all"):
                return {"error": "دسترسی ندارید"}, 403
            cid = finance.upsert_cashbox(conn, d)
            self._audit_add(conn, user["id"], "cashbox_save", "cashboxes", cid,
                            d.get("name", ""))
            conn.commit()
            return {"ok": True, "id": cid}

        # ---- تشخیص تصویری اسکناس‌ها (آفلاین) ----
        if path == "/api/detect":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            b64 = d.get("image", "")
            if not b64:
                raise ValueError("تصویری ارسال نشده")
            import base64
            _hdr, _, b64data = b64.partition(",")
            raw = base64.b64decode(b64data)
            if not vision_mod.available():
                return {"available": False, "message":
                        "کتابخانه‌های تشخیص تصویر (OpenCV) نصب نیستند — سریال را دستی وارد کنید."}
            # الگو و ارقام مجاز بر اساس ارز انتخابی
            currency = None
            if d.get("currency_id"):
                currency = conn.execute("SELECT * FROM currencies WHERE id=?",
                                        (int(d["currency_id"]),)).fetchone()
            pattern = currency["serial_pattern"] if currency else None
            faces = None
            if currency:
                faces = vision_mod.DEFAULT_FACES.get(currency["code"])
            if faces is None:
                faces = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000, 2000,
                         5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000]
            try:
                res = vision_mod.process_photo(raw, pattern=pattern, faces=faces)
            except Exception as e:
                return {"available": True, "error": f"خطای تشخیص: {e}"}
            # برش هر اسکناس به‌صورت data-url برای نمایش در رابط کاربر
            for it in res["items"]:
                crop = vision_mod.crop_rect(raw, it["quad"])
                if crop:
                    it["crop"] = "data:image/jpeg;base64," + base64.b64encode(crop).decode()
                else:
                    it["crop"] = None
            return {"available": True, "count": res["count"], "quality": res["quality"],
                    "items": res["items"],
                    "currency": {"code": currency["code"], "symbol": currency["symbol"],
                                 "decimals": currency["decimals"],
                                 "unit_ratio": currency["unit_ratio"],
                                 "serial_zone": currency["serial_zone"],
                                 "color_hex": currency["color_hex"]} if currency else None}

        # ---- ثبت اسکناس‌های تأییدشده از روی عکس ----
        if path == "/api/detect/register":
            if not _can(user, "banknote"):
                return {"error": "دسترسی ندارید"}, 403
            import base64
            currency_id = int(d["currency_id"])
            denomination = int(d["denomination"])
            count_only = int(d.get("count_only") or 0)
            items = d.get("items") or []
            if not items and not count_only:
                raise ValueError("هیچ اسکناسی برای ثبت ارسال نشده")
            status = d.get("status", "in_vault")
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            # ذخیره عکس مبدأ (برای سوابق)
            source_path = None
            if d.get("source_image"):
                _h, _, _b = d["source_image"].partition(",")
                ext = ".png" if "png" in _h else ".jpg"
                fname = f"batch_{int(datetime.datetime.now().timestamp())}{ext}"
                with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
                    f.write(base64.b64decode(_b))
                source_path = f"uploads/{fname}"
            norm = []
            for it in items:
                serial = str(it.get("serial") or "").strip().upper()
                if not serial:
                    continue
                imgs = []
                crop_b64 = it.get("crop") or it.get("image")
                if crop_b64:
                    _h, _, _b = crop_b64.partition(",")
                    ext = ".png" if "png" in _h else ".jpg"
                    fname = f"bn_{serial}_{int(datetime.datetime.now().timestamp()*1000)}{ext}"
                    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
                        f.write(base64.b64decode(_b))
                    imgs.append({"file_path": f"uploads/{fname}",
                                 "mime": _h.split(":")[1].split(";")[0] if ":" in _h else "image/jpeg",
                                 "type": "crop",
                                 "confidence": it.get("serial_confidence"),
                                 "meta": json.dumps(it.get("meta") or {}, ensure_ascii=False) if it.get("meta") else None})
                norm.append({"serial": serial, "images": imgs,
                             "note": it.get("note", "")})
            r = finance.register_banknotes(
                conn, currency_id, denomination, norm, status=status,
                cashbox_id=d.get("cashbox_id") or None, party_id=d.get("party_id"),
                journal_id=d.get("journal_id"), invoice_id=d.get("invoice_id"),
                source_image=source_path, note=d.get("note", ""), user_id=user["id"],
                count_only=count_only)
            return {"ok": True, **r}

        # ---- پیکربندی SMTP (سوپرادمین) — برای ارسال واقعی کد بازیابی ----
        if path == "/api/smtp/save":
            if user["role"] != "super_admin":
                return {"error": "دسترسی ندارید"}, 403
            for k in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass",
                      "smtp_from", "smtp_tls"):
                if k in d:
                    conn.execute(
                        """INSERT INTO settings(account_id,key,value) VALUES(0,?,?)
                           ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value""",
                        (k, str(d[k])))
            conn.commit()
            return {"ok": True}

        # ---- صورتحساب اشتراک (SaaS) ----
        if path == "/api/billing/checkout":
            plan_code = d.get("plan_code") or "pro"
            plan = next((p for p in finance.plan_catalog() if p["code"] == plan_code), None)
            if not plan:
                raise ValueError("پلن نامعتبر است")
            # درگاه شبیه‌سازی‌شده: شناسه‌ی ارجاع می‌سازیم؛ در نسخه تولید به PSP واقعی وصل می‌شود
            ref = "sim-" + auth.new_token()[:12]
            conn.execute(
                """INSERT INTO billing(account_id,plan_code,amount_rial,status,gateway,ref_code)
                   VALUES (?,?,?,?,?,?)""",
                (context.get_account(), plan_code, plan["price_rial"],
                 "pending", "simulated", ref))
            conn.commit()
            return {"ok": True, "ref_code": ref, "plan": plan,
                    "pay_url": f"/#/billing/pay/{ref}"}

        if path == "/api/billing/confirm":
            ref = d.get("ref_code") or ""
            bill = conn.execute(
                "SELECT * FROM billing WHERE ref_code=? AND account_id=? AND status='pending'",
                (ref, context.get_account())).fetchone()
            if not bill:
                raise ValueError("صورتحساب یافت نشد یا قبلاً پرداخت شده است")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE billing SET status='paid', paid_at=? WHERE id=?",
                         (now, bill["id"]))
            conn.execute("UPDATE accounts SET plan=?, status='active' WHERE id=?",
                         (bill["plan_code"], bill["account_id"]))
            conn.commit()
            self._audit_add(conn, user["id"], "billing_confirm", "billing", bill["id"],
                            f"پرداخت {bill['plan_code']}")
            return {"ok": True, "plan": bill["plan_code"]}

        return {"error": "not found"}, 404

    # ---------- helpers ----------
    def _get_setting(self, conn, key, default=None):
        r = conn.execute("SELECT value FROM settings WHERE account_id=? AND key=?",
                         (context.get_account(), key)).fetchone()
        return r["value"] if r else default

    def _me(self, conn, user):
        u = {k: user.get(k) for k in ("id", "username", "full_name", "role", "account_id", "is_owner")}
        u["totp_enabled"] = bool(user.get("totp_secret"))
        out = {"user": u, "impersonated_by": user.get("impersonated_by"),
               "viewing_account": context.get_account(),
               "auth_required": AUTH_REQUIRED,
               "google_configured": self._google_configured(conn),
               "modules": user.get("_modules", permissions.effective_modules(conn, user)),
               "perms": sorted(user.get("_perms", permissions.effective_perm_set(conn, user)))}
        # نقش‌های قابل مشاهده برای ساخت/ویرایش کاربر
        out["roles"] = permissions.EDITABLE_ROLES + ["super_admin"]
        if user["role"] == "super_admin":
            out["accounts"] = [dict(r) for r in conn.execute(
                "SELECT * FROM accounts ORDER BY id").fetchall()]
        if user.get("account_id"):
            a = conn.execute("SELECT * FROM accounts WHERE id=?", (user["account_id"],)).fetchone()
            out["account"] = dict(a) if a else None
        return out

    def _accounts(self, conn, user):
        if user["role"] != "super_admin":
            return {"error": "دسترسی ندارید"}
        rows = []
        for a in conn.execute("SELECT * FROM accounts WHERE deleted_at IS NULL ORDER BY id").fetchall():
            aid = a["id"]
            owner = conn.execute(
                "SELECT id, full_name FROM users WHERE account_id=? AND is_owner=1 LIMIT 1",
                (aid,)).fetchone()
            stats = {
                "users": conn.execute("SELECT COUNT(*) c FROM users WHERE account_id=?", (aid,)).fetchone()["c"],
                "parties": conn.execute("SELECT COUNT(*) c FROM parties WHERE account_id=?", (aid,)).fetchone()["c"],
                "invoices": conn.execute("SELECT COUNT(*) c FROM invoices WHERE account_id=?", (aid,)).fetchone()["c"],
                "tx": conn.execute("SELECT COUNT(*) c FROM transactions WHERE account_id=?", (aid,)).fetchone()["c"],
                "last_activity": (conn.execute(
                    "SELECT MAX(created_at) t FROM journal WHERE account_id=?", (aid,)).fetchone() or {"t": None})["t"],
            }
            rows.append({**dict(a), **stats,
                         "owner_id": owner["id"] if owner else None,
                         "owner_name": owner["full_name"] if owner else None})
        return {"items": rows}

    def _users(self, conn, user):
        if user["role"] == "super_admin":
            h = self.headers.get("X-Account-Id")
            if h:
                rows = conn.execute(
                    "SELECT id, account_id, username, full_name, role, is_owner, is_active, created_at "
                    "FROM users WHERE account_id=? AND deleted_at IS NULL ORDER BY id", (int(h),)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, account_id, username, full_name, role, is_owner, is_active, created_at "
                    "FROM users WHERE deleted_at IS NULL ORDER BY account_id, id").fetchall()
        elif user["role"] == "admin":
            rows = conn.execute(
                "SELECT id, account_id, username, full_name, role, is_owner, is_active, created_at "
                "FROM users WHERE account_id=? AND deleted_at IS NULL ORDER BY id", (context.get_account(),)).fetchall()
        else:
            return {"error": "دسترسی ندارید"}
        return {"items": [dict(r) for r in rows]}

    def _dashboard(self, conn, user):
        acct = context.get_account()
        if user["role"] == "super_admin" and not self.headers.get("X-Account-Id"):
            # نمای مدیریت: فهرست مشترکین
            acc = []
            for a in conn.execute("SELECT * FROM accounts ORDER BY id").fetchall():
                aid = a["id"]
                acc.append({
                    "id": aid, "name": a["name"], "plan": a["plan"], "status": a["status"],
                    "users": conn.execute("SELECT COUNT(*) c FROM users WHERE account_id=?", (aid,)).fetchone()["c"],
                    "invoices": conn.execute("SELECT COUNT(*) c FROM invoices WHERE account_id=?", (aid,)).fetchone()["c"],
                    "created_at": a["created_at"],
                })
            return {"super": True, "accounts": acc, "total_accounts": len(acc),
                    "today_fa": util.today_fa()}
        currencies = [dict(r) for r in conn.execute(
            "SELECT * FROM currencies WHERE is_active=1 AND deleted_at IS NULL ORDER BY sort_order,id").fetchall()]
        cashboxes = self._cashboxes(conn)
        totals = {c["code"]: 0 for c in currencies}
        for cb in cashboxes:
            for code, bal in cb["balances"].items():
                totals[code] = totals.get(code, 0) + bal
        party_rows = conn.execute(
            """SELECT p.id, p.full_name, p.type,
                      t.currency_id, c.code, c.symbol, c.decimals, c.unit_ratio,
                      SUM(CASE WHEN t.direction='credit' THEN t.amount ELSE -t.amount END) bal,
                      SUM(CASE WHEN t.direction='credit' THEN t.rial_value ELSE -t.rial_value END) bal_rial
               FROM transactions t JOIN journal j ON j.id=t.journal_id
               JOIN parties p ON p.id=t.party_id JOIN currencies c ON c.id=t.currency_id
               WHERE j.status='posted' AND t.account_id=? AND p.deleted_at IS NULL
               GROUP BY p.id, p.full_name, p.type, t.currency_id,
                        c.code, c.symbol, c.decimals, c.unit_ratio
               ORDER BY ABS(SUM(CASE WHEN t.direction='credit' THEN t.rial_value ELSE -t.rial_value END)) DESC""",
            (acct,)).fetchall()
        debtors, creditors, agg = [], [], {}
        for r in party_rows:
            agg.setdefault(r["id"], {"id": r["id"], "full_name": r["full_name"],
                                     "type": r["type"], "balances": {}, "net_rial": 0})
            agg[r["id"]]["balances"][r["code"]] = {"amount": r["bal"], "decimals": r["decimals"],
                                                   "unit_ratio": r["unit_ratio"], "symbol": r["symbol"]}
            agg[r["id"]]["net_rial"] += r["bal_rial"]
        for pid, info in agg.items():
            if info["net_rial"] < 0:
                debtors.append(info)
            elif info["net_rial"] > 0:
                creditors.append(info)
        debtors.sort(key=lambda x: x["net_rial"])
        creditors.sort(key=lambda x: -x["net_rial"])
        stats = finance.daily_stats(conn, account_id=acct)
        recent = []
        for j in conn.execute("SELECT * FROM journal WHERE account_id=? ORDER BY id DESC LIMIT 10",
                              (acct,)).fetchall():
            legs = conn.execute(
                """SELECT t.amount, t.direction, c.code, c.unit_ratio, c.decimals
                   FROM transactions t JOIN currencies c ON c.id=t.currency_id
                   WHERE t.journal_id=?""", (j["id"],)).fetchall()
            parts = []
            for l in legs:
                v = l["amount"] / (l["unit_ratio"] or 1)
                s = f"{v:,.{l['decimals']}f}".rstrip("0").rstrip(".") if l["decimals"] else f"{v:,.0f}"
                parts.append(f"{l['code']} {s}")
            recent.append({**dict(j), "summary": "، ".join(parts)[:60]})
        credit_alerts = []
        for p in conn.execute(
                """SELECT * FROM parties WHERE account_id=? AND deleted_at IS NULL
                   AND credit_limit IS NOT NULL AND credit_limit > 0""",
                (acct,)).fetchall():
            chk = finance.party_credit_check(conn, p["id"])
            if chk["used_rial"] > chk["credit_limit"]:
                credit_alerts.append({"party": p["full_name"],
                                      "used_rial": chk["used_rial"],
                                      "credit_limit": chk["credit_limit"]})
        credit_alerts.sort(key=lambda c: -c["used_rial"])
        return {"super": False, "currencies": currencies, "cashboxes": cashboxes,
                "totals": totals, "debtors": debtors[:8], "creditors": creditors[:8],
                "stats": stats, "recent": recent, "today_fa": util.today_fa(),
                "alerts": finance.low_stock_alerts(conn, account_id=acct),
                "reminders": finance.loan_reminders(conn, account_id=acct),
                "credit_alerts": credit_alerts}

    def _cashboxes(self, conn, include_inactive=False):
        where = ("account_id=? AND is_active=1 AND deleted_at IS NULL"
                 if not include_inactive else "account_id=? AND deleted_at IS NULL")
        out = []
        for cb in conn.execute(f"SELECT * FROM cashboxes WHERE {where} ORDER BY id",
                               (context.get_account(),)).fetchall():
            parent_name = None
            if cb["parent_id"]:
                p = conn.execute("SELECT name FROM cashboxes WHERE id=?",
                                 (cb["parent_id"],)).fetchone()
                parent_name = p["name"] if p else None
            currency_code = None
            if cb["currency_id"]:
                c = conn.execute("SELECT code FROM currencies WHERE id=?",
                                 (cb["currency_id"],)).fetchone()
                currency_code = c["code"] if c else None
            out.append({"id": cb["id"], "name": cb["name"], "code": cb["code"],
                        "kind": cb["kind"], "description": cb["description"],
                        "parent_id": cb["parent_id"], "parent_name": parent_name,
                        "currency_id": cb["currency_id"], "currency_code": currency_code,
                        "is_active": cb["is_active"],
                        "balances": finance.cashbox_balances(conn, cb["id"])})
        return out

    def _batches(self, conn, qs):
        limit = int(qs.get("limit", [50])[0])
        rows = conn.execute(
            """SELECT b.*, c.code, c.symbol, c.decimals, c.unit_ratio,
                      p.full_name party_name, u.full_name creator
               FROM banknote_batches b
               LEFT JOIN currencies c ON c.id=b.currency_id
               LEFT JOIN parties p ON p.id=b.party_id
               LEFT JOIN users u ON u.id=b.created_by
               WHERE b.account_id=? ORDER BY b.id DESC LIMIT ?""",
            (context.get_account(), limit)).fetchall()
        out = []
        for b in rows:
            b = dict(b)
            b["count"] = conn.execute(
                "SELECT COUNT(*) c FROM banknotes WHERE batch_id=?", (b["id"],)).fetchone()["c"]
            out.append(b)
        return out

    def _party_detail(self, conn, pid):
        p = conn.execute("SELECT * FROM parties WHERE id=? AND account_id=? AND deleted_at IS NULL",
                         (pid, context.get_account())).fetchone()
        if not p:
            raise ValueError("طرف حساب یافت نشد")
        balances = finance.party_balances(conn, pid)
        bal_out = []
        for cid, b in balances.items():
            c = conn.execute("SELECT * FROM currencies WHERE id=?", (cid,)).fetchone()
            bal_out.append({"code": c["code"], "symbol": c["symbol"], "decimals": c["decimals"],
                            "unit_ratio": c["unit_ratio"], "amount": b["amount"], "rial": b["rial"]})
        invoices = [dict(r) for r in conn.execute(
            """SELECT i.*, c.code, c.decimals, c.unit_ratio FROM invoices i
               JOIN currencies c ON c.id=i.currency_id
               WHERE i.party_id=? AND i.deleted_at IS NULL ORDER BY i.id DESC LIMIT 100""", (pid,)).fetchall()]
        tx = [dict(r) for r in conn.execute(
            """SELECT t.*, j.jtype, j.title, c.code, c.decimals, c.unit_ratio
               FROM transactions t JOIN journal j ON j.id=t.journal_id
               JOIN currencies c ON c.id=t.currency_id
               WHERE t.party_id=? AND j.status='posted' ORDER BY t.id DESC LIMIT 100""",
            (pid,)).fetchall()]
        notes = [dict(r) for r in conn.execute(
            """SELECT b.*, c.code, c.decimals, c.unit_ratio FROM banknotes b
               JOIN currencies c ON c.id=b.currency_id
               WHERE b.id IN (SELECT banknote_id FROM banknote_movements WHERE party_id=?)
               ORDER BY b.id DESC LIMIT 100""", (pid,)).fetchall()]
        loans = [dict(r) for r in conn.execute(
            """SELECT l.*, c.code, c.decimals, c.unit_ratio FROM loans l
               JOIN currencies c ON c.id=l.currency_id WHERE l.party_id=? AND l.deleted_at IS NULL ORDER BY l.id DESC""",
            (pid,)).fetchall()]
        return {"party": dict(p), "balances": bal_out, "invoices": invoices,
                "transactions": tx, "banknotes": notes, "loans": loans}

    def _invoice_detail(self, conn, iid):
        inv = conn.execute(
            """SELECT i.*, p.full_name party_name, p.type party_type, c.code, c.decimals,
                      c.unit_ratio, c.symbol, u.full_name creator
               FROM invoices i JOIN parties p ON p.id=i.party_id
               JOIN currencies c ON c.id=i.currency_id
               LEFT JOIN users u ON u.id=i.created_by WHERE i.id=? AND i.account_id=? AND i.deleted_at IS NULL""",
            (iid, context.get_account())).fetchone()
        if not inv:
            raise ValueError("فاکتور یافت نشد")
        legs = [dict(r) for r in conn.execute(
            """SELECT t.*, c.code, c.decimals, c.unit_ratio, c.symbol,
                      cb.name cashbox_name, p.full_name party_name
               FROM transactions t JOIN currencies c ON c.id=t.currency_id
               LEFT JOIN cashboxes cb ON cb.id=t.cashbox_id
               LEFT JOIN parties p ON p.id=t.party_id
               WHERE t.journal_id=? ORDER BY t.id""", (inv["journal_id"],)).fetchall()]
        photos = self._journal_photos(conn, inv["journal_id"])
        banknotes = [dict(r) for r in conn.execute(
            """SELECT b.id, b.serial, b.denomination, b.status, b.note,
                      c.code, c.decimals, c.unit_ratio, m.movement_type, m.id movement_id
               FROM banknote_movements m JOIN banknotes b ON b.id=m.banknote_id
               JOIN currencies c ON c.id=b.currency_id
               WHERE m.journal_id=? AND m.account_id=? ORDER BY m.id""",
            (inv["journal_id"], context.get_account())).fetchall()]
        return {"invoice": dict(inv), "legs": legs, "photos": photos, "banknotes": banknotes}

    def _journal_photos(self, conn, journal_id):
        """عکس‌های اسکناس‌های مرتبط با یک سند (از طریق حرکت اسکناس)"""
        if not journal_id:
            return []
        rows = conn.execute(
            """SELECT i.*, b.serial, b.denomination, c.code
               FROM banknote_images i
               JOIN banknotes b ON b.id=i.banknote_id
               JOIN currencies c ON c.id=b.currency_id
               WHERE i.banknote_id IN (
                     SELECT banknote_id FROM banknote_movements WHERE journal_id=? AND account_id=?)
               ORDER BY i.id""", (journal_id, context.get_account())).fetchall()
        return [dict(r) for r in rows]

    def _debts(self, conn):
        rows = conn.execute(
            """SELECT p.id party_id, p.full_name, p.type,
                      t.currency_id, c.code, c.symbol, c.decimals, c.unit_ratio,
                      SUM(CASE WHEN t.direction='credit' THEN t.amount ELSE -t.amount END) bal,
                      SUM(CASE WHEN t.direction='credit' THEN t.rial_value ELSE -t.rial_value END) bal_rial
               FROM transactions t JOIN journal j ON j.id=t.journal_id
               JOIN parties p ON p.id=t.party_id JOIN currencies c ON c.id=t.currency_id
               WHERE j.status='posted' AND t.account_id=? AND p.deleted_at IS NULL
               GROUP BY p.id, p.full_name, p.type, t.currency_id,
                        c.code, c.symbol, c.decimals, c.unit_ratio, c.sort_order
               ORDER BY p.full_name, c.sort_order""", (context.get_account(),)).fetchall()
        agg = {}
        for r in rows:
            agg.setdefault(r["party_id"], {"party_id": r["party_id"], "full_name": r["full_name"],
                                           "type": r["type"], "rows": []})
            agg[r["party_id"]]["rows"].append(dict(r))
        return {"items": list(agg.values())}

    def _loans(self, conn):
        out = []
        for l in conn.execute(
                """SELECT l.*, p.full_name, c.code, c.decimals, c.unit_ratio FROM loans l
                   JOIN parties p ON p.id=l.party_id JOIN currencies c ON c.id=l.currency_id
                   WHERE l.account_id=? AND l.deleted_at IS NULL ORDER BY l.id DESC""",
                (context.get_account(),)).fetchall():
            l = dict(l)
            repaid = conn.execute(
                """SELECT COALESCE(SUM(t.amount),0) s FROM transactions t
                   JOIN journal j ON j.id=t.journal_id
                   WHERE j.jtype='loan_repay' AND j.status='posted'
                     AND t.account_id=? AND t.account_type='party' AND t.party_id=? AND t.currency_id=?""",
                (context.get_account(), l["party_id"], l["currency_id"])).fetchone()["s"]
            l["repaid"] = repaid
            out.append(l)
        return out

    def _banknotes(self, conn, qs):
        where, args = "b.account_id=? AND b.deleted_at IS NULL", [context.get_account()]
        if qs.get("q"):
            like = f"%{qs['q'][0]}%"
            where += " AND (b.serial LIKE ? OR p.full_name LIKE ? OR c.code LIKE ?)"
            args += [like, like, like]
        if qs.get("status"):
            where += " AND b.status=?"
            args.append(qs["status"][0])
        if qs.get("currency"):
            where += " AND b.currency_id=?"
            args.append(int(qs["currency"][0]))
        limit = int(qs.get("limit", [100])[0])
        page = int(qs.get("page", [1])[0])
        off = max(0, (page - 1) * limit)
        total = conn.execute(f"SELECT COUNT(*) c FROM banknotes b WHERE {where}", args).fetchone()["c"]
        concat = "GROUP_CONCAT(p.full_name)" if schema.engine() == "sqlite" else "STRING_AGG(p.full_name, ',')"
        rows = conn.execute(
            f"""SELECT b.*, c.code, c.decimals, c.unit_ratio, cb.name cashbox_name,
                       (SELECT {concat} FROM banknote_movements m
                        LEFT JOIN parties p ON p.id=m.party_id WHERE m.banknote_id=b.id) parties
                FROM banknotes b JOIN currencies c ON c.id=b.currency_id
                LEFT JOIN cashboxes cb ON cb.id=b.cashbox_id
                WHERE {where} ORDER BY b.id DESC LIMIT ? OFFSET ?""", args + [limit, off]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page, "limit": limit}

    def _banknote_detail(self, conn, bid):
        if not bid:
            raise ValueError("شناسه لازم است")
        b = conn.execute(
            """SELECT b.*, c.code, c.decimals, c.unit_ratio, c.symbol, cb.name cashbox_name
               FROM banknotes b JOIN currencies c ON c.id=b.currency_id
               LEFT JOIN cashboxes cb ON cb.id=b.cashbox_id
               WHERE b.id=? AND b.account_id=? AND b.deleted_at IS NULL""", (int(bid), context.get_account())).fetchone()
        if not b:
            raise ValueError("اسکناس یافت نشد")
        moves = [dict(r) for r in conn.execute(
            """SELECT m.*, p.full_name party_name, cb1.name from_name, cb2.name to_name
               FROM banknote_movements m
               LEFT JOIN parties p ON p.id=m.party_id
               LEFT JOIN cashboxes cb1 ON cb1.id=m.from_cashbox
               LEFT JOIN cashboxes cb2 ON cb2.id=m.to_cashbox
               WHERE m.banknote_id=? ORDER BY m.id""", (int(bid),)).fetchall()]
        imgs = [dict(r) for r in conn.execute(
            "SELECT * FROM banknote_images WHERE banknote_id=? ORDER BY id", (int(bid),)).fetchall()]
        return {"banknote": dict(b), "movements": moves, "images": imgs}

    def _journal_detail(self, conn, jid):
        j = conn.execute("SELECT * FROM journal WHERE id=? AND account_id=?",
                         (jid, context.get_account())).fetchone()
        if not j:
            raise ValueError("سند یافت نشد")
        legs = [dict(r) for r in conn.execute(
            """SELECT t.*, c.code, c.decimals, c.unit_ratio, c.symbol,
                      cb.name cashbox_name, p.full_name party_name
               FROM transactions t JOIN currencies c ON c.id=t.currency_id
               LEFT JOIN cashboxes cb ON cb.id=t.cashbox_id
               LEFT JOIN parties p ON p.id=t.party_id
               WHERE t.journal_id=? ORDER BY t.id""", (jid,)).fetchall()]
        return {"journal": dict(j), "legs": legs}

    def _rates_status(self, conn):
        meta = rates.last_fetch_meta(conn, context.get_account())
        return {"source": self._get_setting(conn, "rate_source", rates.DEFAULT_PROVIDER),
                "auto_refresh": self._get_setting(conn, "rate_auto_refresh", "0"),
                "last_fetch": (meta or {}).get("t"),
                "last_source": (meta or {}).get("source"),
                "navasan_key_set": bool(self._navasan_key(conn)),
                "providers": {k: v["name"] for k, v in rates.PROVIDERS.items()}}

    def _navasan_key(self, conn):
        """کلید API نوسان: اول متغیر محیطی، بعد تنظیمات حساب جاری."""
        key = os.environ.get("SARRAFI_NAVASAN_KEY", "").strip()
        if key:
            return key
        r = conn.execute("SELECT value FROM settings WHERE account_id=? AND key='rate_navasan_key'",
                         (context.get_account(),)).fetchone()
        return (r["value"] if r and r["value"] else "").strip()

    def _cashbox_report(self, conn, cb, day):
        if "/" in day:
            parts = list(map(int, day.split("/")))
            gy, gm, gd = util.jalali_to_gregorian(*parts)
            day = f"{gy:04d}-{gm:02d}-{gd:02d}"
        out = []
        for c in conn.execute("SELECT * FROM currencies WHERE is_active=1 AND deleted_at IS NULL ORDER BY sort_order,id").fetchall():
            out.append(finance.cashbox_report(conn, cb, c["id"], day))
        return {"day": day, "items": out,
                "day_fa": util.fa_date(datetime.datetime.strptime(day, "%Y-%m-%d").date())}

    def _profit_report(self, conn, frm, to):
        if not frm or not to:
            today = datetime.date.today()
            frm = (today.replace(day=1)).strftime("%Y-%m-%d")
            to = today.strftime("%Y-%m-%d")
        pl = finance.profit_loss(conn, frm, to)
        per_currency = []
        for c in conn.execute("SELECT * FROM currencies WHERE code!='IRR' AND is_active=1 AND deleted_at IS NULL").fetchall():
            prof, sold = finance.realized_profit_fifo(conn, c["id"], frm, to)
            per_currency.append({"code": c["code"], "name": c["name"], "profit": prof, "sold": sold})
        return {"from": frm, "to": to, "from_fa": util.fa_date(frm), "to_fa": util.fa_date(to),
                "pl": pl, "per_currency": per_currency}

    def _monthly_report(self, conn, frm, to):
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

        for r in conn.execute("SELECT created_at, rial_value FROM incomes WHERE account_id=? AND deleted_at IS NULL AND created_at>=? AND created_at<=?",
                              (context.get_account(), start, end)).fetchall():
            add(r["created_at"], "income", r["rial_value"])
        for r in conn.execute("SELECT created_at, rial_value FROM expenses WHERE account_id=? AND deleted_at IS NULL AND created_at>=? AND created_at<=?",
                              (context.get_account(), start, end)).fetchall():
            add(r["created_at"], "expense", r["rial_value"])
        for r in conn.execute(
                """SELECT confirmed_at created_at, total_rial FROM invoices
                   WHERE account_id=? AND deleted_at IS NULL AND invoice_type='buy' AND status IN ('confirmed','settled')
                     AND confirmed_at>=? AND confirmed_at<=?""", (context.get_account(), start, end)).fetchall():
            add(r["created_at"], "buy", r["total_rial"])
        for r in conn.execute(
                """SELECT confirmed_at created_at, total_rial FROM invoices
                   WHERE account_id=? AND deleted_at IS NULL AND invoice_type='sell' AND status IN ('confirmed','settled')
                     AND confirmed_at>=? AND confirmed_at<=?""", (context.get_account(), start, end)).fetchall():
            add(r["created_at"], "sell", r["total_rial"])
        items = list(months.values())
        items.sort(key=lambda x: x["month"])
        for it in items:
            it["net"] = it["sell"] - it["buy"] + it["income"] - it["expense"]
        return {"from": frm, "to": to, "from_fa": util.fa_date(frm), "to_fa": util.fa_date(to), "items": items}

    def _charts(self, conn, frm, to):
        today = datetime.date.today()
        if not frm or not to:
            frm = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            to = today.strftime("%Y-%m-%d")
        acct = context.get_account()

        # ۱) ترکیب صندوق به تفکیک ارز (معادل ریالی)
        comp = []
        for c in conn.execute("SELECT * FROM currencies WHERE is_active=1 AND deleted_at IS NULL ORDER BY sort_order,id").fetchall():
            bal = 0
            for cb in conn.execute("SELECT id FROM cashboxes WHERE account_id=? AND deleted_at IS NULL", (acct,)).fetchall():
                bal += finance._cashbox_currency_balance(conn, cb["id"], c["id"], account_id=acct)
            rate = c["unit_ratio"] or 1
            rial = bal if c["code"] == "IRR" else int(bal / rate * self._last_rate(conn, c["id"]))
            if bal != 0:
                comp.append({"code": c["code"], "name": c["name"], "amount": bal,
                             "decimals": c["decimals"], "unit_ratio": c["unit_ratio"], "rial": rial})
        comp.sort(key=lambda x: -x["rial"])

        # ۲) هزینه‌ها به تفکیک دسته
        start, end = frm + " 00:00:00", to + " 23:59:59"
        exp_cat = [dict(r) for r in conn.execute(
            """SELECT COALESCE(ec.name,'سایر') category, SUM(e.rial_value) total
               FROM expenses e LEFT JOIN expense_categories ec ON ec.id=e.category_id
               WHERE e.account_id=? AND e.deleted_at IS NULL AND e.created_at>=? AND e.created_at<=?
               GROUP BY ec.name ORDER BY total DESC""", (acct, start, end)).fetchall()]

        # ۳) خرید/فروش روزانه (خطی)
        daily = [dict(r) for r in conn.execute(
            """SELECT substr(COALESCE(confirmed_at, created_at),1,10) d,
                      SUM(CASE WHEN invoice_type='buy' THEN total_rial ELSE 0 END) buy,
                      SUM(CASE WHEN invoice_type='sell' THEN total_rial ELSE 0 END) sell
               FROM invoices WHERE account_id=? AND deleted_at IS NULL AND status IN ('confirmed','settled')
                 AND COALESCE(confirmed_at,created_at)>=? AND COALESCE(confirmed_at,created_at)<=?
               GROUP BY d ORDER BY d LIMIT 90""", (acct, start, end)).fetchall()]

        # ۴) طرف حساب‌های برتر (میله‌ای)
        top_parties = [dict(r) for r in conn.execute(
            """SELECT p.full_name, SUM(i.total_rial) volume, COUNT(*) c
               FROM invoices i JOIN parties p ON p.id=i.party_id
               WHERE i.account_id=? AND i.deleted_at IS NULL AND i.status IN ('confirmed','settled')
                 AND COALESCE(i.confirmed_at,i.created_at)>=? AND COALESCE(i.confirmed_at,i.created_at)<=?
               GROUP BY p.id, p.full_name ORDER BY volume DESC LIMIT 8""", (acct, start, end)).fetchall()]

        # ۵) مقایسه ماهانه درآمد/هزینه/سود
        monthly = self._monthly_report(conn, frm, to)["items"]

        # ۶) روند نرخ ارز (خطی) — آخرین نقاط ثبت‌شده برای هر ارز
        rate_trend = []
        for c in conn.execute("SELECT * FROM currencies WHERE is_active=1 AND code!='IRR' AND deleted_at IS NULL ORDER BY sort_order,id").fetchall():
            pts = [dict(r) for r in conn.execute(
                """SELECT rate, rate_date FROM exchange_rates
                   WHERE account_id=? AND currency_id=? ORDER BY rate_date ASC LIMIT 60""",
                (acct, c["id"])).fetchall()]
            if pts:
                rate_trend.append({"code": c["code"], "name": c["name"],
                                   "decimals": c["decimals"], "points": pts})

        # ۶٫۵) روند سود تحقق‌یافته (ماهانه، جمع ارزها)
        profit_trend = []
        for c in conn.execute("SELECT id, code FROM currencies WHERE code!='IRR' AND is_active=1 AND deleted_at IS NULL").fetchall():
            rows = conn.execute(
                """SELECT substr(j.created_at,1,7) ym,
                          SUM(CASE WHEN t.direction='debit' THEN t.rial_value ELSE -t.rial_value END) pl
                   FROM transactions t JOIN journal j ON j.id=t.journal_id
                   WHERE t.account_id=? AND t.currency_id=? AND j.status='posted'
                     AND j.jtype IN ('buy','sell')
                   GROUP BY ym ORDER BY ym""", (acct, c["id"])).fetchall()
            if any(r["pl"] for r in rows):
                profit_trend.append({"code": c["code"], "points": [dict(r) for r in rows]})

        # ۶٫۶) گردش هر ارز (حجم خرید+فروش ریالی در دوره)
        turnover = [dict(r) for r in conn.execute(
            """SELECT c.code, c.name, SUM(i.total_rial) volume, COUNT(*) c
               FROM invoices i JOIN currencies c ON c.id=i.currency_id
               WHERE i.account_id=? AND i.deleted_at IS NULL AND i.status IN ('confirmed','settled')
                 AND COALESCE(i.confirmed_at,i.created_at)>=? AND COALESCE(i.confirmed_at,i.created_at)<=?
               GROUP BY c.id, c.code, c.name ORDER BY volume DESC""",
            (acct, start, end)).fetchall()]

        # ۷) مقایسه با دوره مشابه سال قبل
        def _period_totals(a, b):
            return {
                "buy": conn.execute(
                    """SELECT COALESCE(SUM(total_rial),0) v FROM invoices
                       WHERE account_id=? AND deleted_at IS NULL AND invoice_type='buy' AND status IN ('confirmed','settled')
                       AND COALESCE(confirmed_at,created_at)>=? AND COALESCE(confirmed_at,created_at)<=?""",
                    (acct, a, b)).fetchone()["v"],
                "sell": conn.execute(
                    """SELECT COALESCE(SUM(total_rial),0) v FROM invoices
                       WHERE account_id=? AND deleted_at IS NULL AND invoice_type='sell' AND status IN ('confirmed','settled')
                       AND COALESCE(confirmed_at,created_at)>=? AND COALESCE(confirmed_at,created_at)<=?""",
                    (acct, a, b)).fetchone()["v"],
                "income": conn.execute(
                    """SELECT COALESCE(SUM(rial_value),0) v FROM incomes
                       WHERE account_id=? AND deleted_at IS NULL AND created_at>=? AND created_at<=?""",
                    (acct, a, b)).fetchone()["v"],
                "expense": conn.execute(
                    """SELECT COALESCE(SUM(rial_value),0) v FROM expenses
                       WHERE account_id=? AND deleted_at IS NULL AND created_at>=? AND created_at<=?""",
                    (acct, a, b)).fetchone()["v"],
            }
        try:
            d0 = datetime.date.fromisoformat(frm); d1 = datetime.date.fromisoformat(to)
            prev_a = (d0.replace(year=d0.year - 1)).strftime("%Y-%m-%d")
            prev_b = (d1.replace(year=d1.year - 1)).strftime("%Y-%m-%d")
            cur_t = _period_totals(start, end)
            prev_t = _period_totals(prev_a + " 00:00:00", prev_b + " 23:59:59")
            for k in prev_t:
                prev_t[k] = prev_t[k] or 0
                cur_t[k] = cur_t[k] or 0
            prev_t["net"] = prev_t["sell"] - prev_t["buy"] + prev_t["income"] - prev_t["expense"]
            cur_t["net"] = cur_t["sell"] - cur_t["buy"] + cur_t["income"] - cur_t["expense"]
            year_compare = {"current": cur_t, "previous": prev_t,
                            "prev_from_fa": util.fa_date(prev_a), "prev_to_fa": util.fa_date(prev_b)}
        except ValueError:
            year_compare = None

        return {"from": frm, "to": to, "from_fa": util.fa_date(frm), "to_fa": util.fa_date(to),
                "cashbox_composition": comp, "expense_by_category": exp_cat,
                "buy_sell_daily": daily, "top_parties": top_parties, "monthly": monthly,
                "rate_trend": rate_trend, "profit_trend": profit_trend,
                "turnover": turnover, "year_compare": year_compare}

    def _last_rate(self, conn, currency_id):
        r = conn.execute(
            """SELECT rate FROM exchange_rates WHERE account_id=? AND currency_id=?
               ORDER BY rate_date DESC LIMIT 1""", (context.get_account(), currency_id)).fetchone()
        return r["rate"] if r else 0

    def _csv(self, conn, typ):
        def to_csv(headers, rows):
            import csv, io as _io
            buf = _io.StringIO()
            w = csv.writer(buf)
            w.writerow(headers)
            for r in rows:
                d = dict(r)
                w.writerow(["" if d.get(h) is None else str(d.get(h)) for h in headers])
            return buf.getvalue().encode("utf-8-sig")

        acct = context.get_account()
        if typ == "transactions":
            rows = conn.execute(
                """SELECT t.id, t.created_at, j.jtype, t.direction, t.account_type,
                          c.code, t.amount, t.rate, t.rial_value, cb.name cashbox, p.full_name party
                   FROM transactions t JOIN journal j ON j.id=t.journal_id
                   JOIN currencies c ON c.id=t.currency_id
                   LEFT JOIN cashboxes cb ON cb.id=t.cashbox_id
                   LEFT JOIN parties p ON p.id=t.party_id
                   WHERE t.account_id=? ORDER BY t.id DESC LIMIT 10000""", (acct,)).fetchall()
            data = to_csv(["id", "created_at", "jtype", "direction", "account_type",
                           "currency", "amount", "rate", "rial_value", "cashbox", "party"], rows)
            self._send(200, data, "text/csv; charset=utf-8")
        elif typ == "invoices":
            rows = conn.execute(
                """SELECT i.invoice_no, i.created_at, i.invoice_type, p.full_name party,
                          c.code, i.amount, i.rate, i.total_rial, i.status
                   FROM invoices i JOIN parties p ON p.id=i.party_id
                   JOIN currencies c ON c.id=i.currency_id
                   WHERE i.account_id=? AND i.deleted_at IS NULL ORDER BY i.id DESC LIMIT 10000""", (acct,)).fetchall()
            data = to_csv(["invoice_no", "created_at", "type", "party", "currency",
                           "amount", "rate", "total_rial", "status"], rows)
            self._send(200, data, "text/csv; charset=utf-8")
        elif typ == "banknotes":
            rows = conn.execute(
                """SELECT b.serial, c.code, b.denomination, b.status, cb.name cashbox, b.created_at
                   FROM banknotes b JOIN currencies c ON c.id=b.currency_id
                   LEFT JOIN cashboxes cb ON cb.id=b.cashbox_id
                   WHERE b.account_id=? AND b.deleted_at IS NULL ORDER BY b.id DESC LIMIT 10000""", (acct,)).fetchall()
            data = to_csv(["serial", "currency", "denomination", "status", "cashbox", "created_at"], rows)
            self._send(200, data, "text/csv; charset=utf-8")
        elif typ == "parties":
            rows = conn.execute("SELECT * FROM parties WHERE account_id=? AND deleted_at IS NULL ORDER BY id", (acct,)).fetchall()
            data = to_csv(["id", "type", "full_name", "phone", "mobile", "national_id",
                           "address", "notes", "is_active", "created_at"], rows)
            self._send(200, data, "text/csv; charset=utf-8")
        else:
            self._json({"error": "نوع خروجی نامعتبر"}, 400)

    def _search(self, conn, q):
        """جستجوی سراسری (مشتریان، فاکتورها، اسناد، اسکناس‌ها، قرض‌ها)"""
        q = (q or "").strip()
        if not q:
            return {"q": "", "items": []}
        like = f"%{q}%"
        acct = context.get_account()
        out = []
        # مشتریان
        for p in conn.execute(
                """SELECT id, full_name, type, phone, national_id FROM parties
                   WHERE account_id=? AND deleted_at IS NULL AND (full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? OR mobile LIKE ?)
                   ORDER BY id DESC LIMIT 10""",
                (acct, like, like, like, like)).fetchall():
            out.append({"type": "party", "id": p["id"], "title": p["full_name"],
                        "subtitle": f"{p['type']} • {p['phone'] or p['national_id'] or ''}",
                        "link": "#/parties"})
        # فاکتورها
        for i in conn.execute(
                """SELECT i.id, i.invoice_no, p.full_name, i.status FROM invoices i
                   JOIN parties p ON p.id=i.party_id
                   WHERE i.account_id=? AND i.deleted_at IS NULL AND (i.invoice_no LIKE ? OR p.full_name LIKE ?)
                   ORDER BY i.id DESC LIMIT 10""",
                (acct, like, like)).fetchall():
            out.append({"type": "invoice", "id": i["id"], "title": i["invoice_no"],
                        "subtitle": f"{i['full_name']} • {i['status']}",
                        "link": f"#/invoice/{i['id']}"})
        # اسناد
        for j in conn.execute(
                """SELECT id, jtype, title, ref_no FROM journal
                   WHERE account_id=? AND (title LIKE ? OR ref_no LIKE ?)
                   ORDER BY id DESC LIMIT 10""",
                (acct, like, like)).fetchall():
            out.append({"type": "journal", "id": j["id"], "title": j["title"],
                        "subtitle": f"{j['jtype']} • {j['ref_no'] or ''}",
                        "link": f"#/journal/{j['id']}"})
        # اسکناس‌ها
        for b in conn.execute(
                """SELECT b.id, b.serial, c.code, b.denomination FROM banknotes b
                   JOIN currencies c ON c.id=b.currency_id
                   WHERE b.account_id=? AND b.deleted_at IS NULL AND b.serial LIKE ? ORDER BY b.id DESC LIMIT 10""",
                (acct, like)).fetchall():
            out.append({"type": "banknote", "id": b["id"], "title": b["serial"],
                        "subtitle": f"{b['code']} • {b['denomination']}",
                        "link": "#/banknotes"})
        return {"q": q, "items": out}

    def _xlsx(self, conn, typ):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
            from openpyxl.utils import get_column_letter
        except Exception:
            self._json({"error": "کتابخانه openpyxl نصب نیست — از خروجی CSV استفاده کنید"}, 500)
            return
        acct = context.get_account()
        wb = Workbook()
        ws = wb.active
        ws.sheet_view.rightToLeft = True
        ws.title = "گزارش"

        def sheet(headers_fa, headers_key, rows):
            ws.append(headers_fa)
            head_font = Font(bold=True)
            for cell in ws[1]:
                cell.font = head_font
            for r in rows:
                d = dict(r)
                ws.append([d.get(k) for k in headers_key])
            for i in range(1, len(headers_key) + 1):
                ws.column_dimensions[get_column_letter(i)].width = 18

        if typ == "transactions":
            rows = conn.execute(
                """SELECT t.id, t.created_at, j.jtype, t.direction, t.account_type,
                          c.code, t.amount, t.rate, t.rial_value, cb.name cashbox, p.full_name party
                   FROM transactions t JOIN journal j ON j.id=t.journal_id
                   JOIN currencies c ON c.id=t.currency_id
                   LEFT JOIN cashboxes cb ON cb.id=t.cashbox_id
                   LEFT JOIN parties p ON p.id=t.party_id
                   WHERE t.account_id=? ORDER BY t.id DESC LIMIT 50000""", (acct,)).fetchall()
            sheet(["ردیف", "تاریخ", "نوع سند", "جهت", "حساب", "ارز", "مبلغ", "نرخ", "معادل ریالی", "صندوق", "طرف حساب"],
                  ["id", "created_at", "jtype", "direction", "account_type",
                   "code", "amount", "rate", "rial_value", "cashbox", "party"], rows)
        elif typ == "invoices":
            rows = conn.execute(
                """SELECT i.invoice_no, i.created_at, i.invoice_type, p.full_name party,
                          c.code, i.amount, i.rate, i.total_rial, i.status
                   FROM invoices i JOIN parties p ON p.id=i.party_id
                   JOIN currencies c ON c.id=i.currency_id
                   WHERE i.account_id=? AND i.deleted_at IS NULL ORDER BY i.id DESC LIMIT 50000""", (acct,)).fetchall()
            sheet(["شماره فاکتور", "تاریخ", "نوع", "طرف حساب", "ارز", "مبلغ", "نرخ", "معادل ریالی", "وضعیت"],
                  ["invoice_no", "created_at", "invoice_type", "party", "code",
                   "amount", "rate", "total_rial", "status"], rows)
        elif typ == "banknotes":
            rows = conn.execute(
                """SELECT b.serial, c.code, b.denomination, b.status, cb.name cashbox, b.created_at
                   FROM banknotes b JOIN currencies c ON c.id=b.currency_id
                   LEFT JOIN cashboxes cb ON cb.id=b.cashbox_id
                   WHERE b.account_id=? AND b.deleted_at IS NULL ORDER BY b.id DESC LIMIT 50000""", (acct,)).fetchall()
            sheet(["سریال", "ارز", "مبلغ", "وضعیت", "صندوق", "تاریخ ثبت"],
                  ["serial", "code", "denomination", "status", "cashbox", "created_at"], rows)
        elif typ == "parties":
            rows = conn.execute(
                "SELECT * FROM parties WHERE account_id=? AND deleted_at IS NULL ORDER BY id", (acct,)).fetchall()
            sheet(["ردیف", "نوع", "نام", "تلفن", "موبایل", "کد ملی", "آدرس", "یادداشت", "سقف اعتبار", "فعال"],
                  ["id", "type", "full_name", "phone", "mobile", "national_id",
                   "address", "notes", "credit_limit", "is_active"], rows)
        elif typ == "loans":
            rows = conn.execute(
                """SELECT l.id, p.full_name party, l.direction, c.code, l.amount, l.rate,
                          l.status, l.due_date, l.created_at
                   FROM loans l JOIN parties p ON p.id=l.party_id
                   JOIN currencies c ON c.id=l.currency_id
                   WHERE l.account_id=? AND l.deleted_at IS NULL ORDER BY l.id DESC LIMIT 50000""", (acct,)).fetchall()
            sheet(["ردیف", "طرف حساب", "جهت", "ارز", "مبلغ", "نرخ", "وضعیت", "سررسید", "تاریخ"],
                  ["id", "party", "direction", "code", "amount", "rate",
                   "status", "due_date", "created_at"], rows)
        else:
            self._json({"error": "نوع خروجی نامعتبر"}, 400)
            return
        import io as _io
        buf = _io.BytesIO()
        wb.save(buf)
        fname = f"sarrafi-{typ}-{datetime.date.today()}.xlsx"
        self._send(200, buf.getvalue(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   extra_headers={"Content-Disposition":
                                  f'attachment; filename="{fname}"'})

    def _import_all(self, conn, data):
        tables = data.get("tables", {})
        order = ["accounts", "settings", "currencies", "exchange_rates", "parties", "cashboxes",
                 "cashbox_opening", "users", "expense_categories", "journal", "transactions",
                 "invoices", "payments", "payment_allocations", "loans", "expenses", "incomes",
                 "banknotes", "banknote_images", "banknote_batches", "banknote_movements",
                 "plans", "billing", "audit_log",
                 "account_modules", "user_modules", "role_permissions"]
        for t in order:
            if t not in tables:
                continue
            rows = tables[t]
            if not rows:
                continue
            conn.execute(f"DELETE FROM {t}")
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            colsql = ", ".join(cols)
            for r in rows:
                vals = [r.get(c) for c in cols]
                try:
                    conn.execute(f"INSERT INTO {t}({colsql}) VALUES ({placeholders})", vals)
                except Exception:
                    pass
        conn.commit()


def run(port=8000, db_path=None):
    if db_path:
        schema.DB_PATH = db_path
    schema.init_db()
    conn = schema.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM currencies").fetchone()["c"]
    finally:
        conn.close()
    if n == 0:
        seed.reset_and_seed()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    hours = int(os.environ.get("SARRAFI_BACKUP_HOURS", "24") or 0)
    if hours > 0:
        import threading
        threading.Thread(target=_auto_backup_loop, args=(hours,), daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"✅ صرافی در حال اجرا روی http://0.0.0.0:{port}")
    return server
