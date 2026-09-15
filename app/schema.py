# -*- coding: utf-8 -*-
"""
لایه‌ی دیتابیس — پشتیبانی همزمان از SQLite و PostgreSQL + چندمشترکی (tenants)

مدل چندمشترکی:
    accounts  = هر «مشترک» (سازمان/صرافی) یک حساب دارد.
    users     = کاربران؛ account_id=NULL یعنی سوپرادمین (کل سیستم).
                نقش‌ها: super_admin / admin / cashier / accountant / operator
    سایر جدول‌های تجاری یک ستون account_id دارند و همه‌ی کوئری‌ها با آن
    ایزوله می‌شوند تا داده‌ی مشترکین جدا بماند.

انتخاب موتور:
    SARRAFI_DATABASE_URL = postgresql://... → PostgreSQL
    در غیر این صورت SQLite (SARRAFI_DB یا data/sarrafi.db)
"""

import os
import re
import sqlite3
import threading

DB_PATH = os.environ.get("SARRAFI_DB", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sarrafi.db"))

PG_URL = os.environ.get("SARRAFI_DATABASE_URL", "")

SCHEMA_VERSION = 7

_pg_pool = None
_pg_lock = threading.Lock()


# وقتی مسیر دیتابیس به‌صورت صریح داده می‌شود (تست‌ها، اجرای چند نمونه‌ای)،
# حتی اگر SARRAFI_DATABASE_URL تنظیم باشد همان فایل SQLite استفاده می‌شود.
_INSTANCE_SQLITE = False


_DEFAULT_DB_PATH = DB_PATH


def use_sqlite(path=None):
    """اجبار این نمونه به SQLite (با اولویت بر SARRAFI_DATABASE_URL).

    ``path=None`` یعنی برداشتن اجبار و بازگشت به تنظیمات محیطی؛ برای پایان
    یافتن تست‌هایی که روی فایل موقت اجرا می‌شوند لازم است.
    """
    global DB_PATH, _INSTANCE_SQLITE
    if path is None:
        _INSTANCE_SQLITE = False
        DB_PATH = _DEFAULT_DB_PATH
        return
    DB_PATH = path
    _INSTANCE_SQLITE = True


def engine(db_path=None):
    if db_path:
        return "sqlite"
    if _INSTANCE_SQLITE:
        return "sqlite"
    if PG_URL and PG_URL.startswith(("postgres://", "postgresql://")):
        return "postgres"
    return "sqlite"


def conn_engine(conn):
    """نوع موتور بر اساس خودِ اتصال — مرجع مطمئن برای انتخاب SQL.

    تفاوت با engine(): آن تابع «تنظیمات نمونه» را می‌گوید، این تابع «اتصالی که
    همین حالا در دست است». اگر این دو یکی فرض شوند، هنگام اجرای هم‌زمان SQLite و
    PostgreSQL (مثلاً تست‌ها با فایل موقت در کنار PG_URL) SQL اشتباه انتخاب می‌شود.
    """
    return "postgres" if getattr(conn, "is_postgres", False) else "sqlite"


# ---------------------------------------------------------------------------
# DDL (مرجع SQLite؛ برای PostgreSQL به‌صورت خودکار تبدیل می‌شود)
# ---------------------------------------------------------------------------
SCHEMA_STATEMENTS = [
    # ---------------- حساب‌ها (مشترکین) ----------------
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        phone       TEXT,
        plan        TEXT NOT NULL DEFAULT 'free',
        status      TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended')),
        logo        TEXT,
        deleted_at  TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ---------------- کاربران / نشست‌ها ----------------
    # ---------------- پلن‌ها و صورتحساب (SaaS) ----------------
    """
    CREATE TABLE IF NOT EXISTS plans (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        code          TEXT NOT NULL UNIQUE,
        name          TEXT NOT NULL,
        price_rial    INTEGER NOT NULL DEFAULT 0,
        period_months INTEGER NOT NULL DEFAULT 1,
        limits_json   TEXT,
        features      TEXT,
        is_active     INTEGER NOT NULL DEFAULT 1,
        sort_order    INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS billing (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL,
        plan_code    TEXT NOT NULL,
        amount_rial  INTEGER NOT NULL DEFAULT 0,
        status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK(status IN ('pending','paid','failed','refunded')),
        gateway      TEXT,
        ref_code     TEXT,
        paid_at      TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_billing_account ON billing(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_billing_acct_created ON billing(account_id, created_at)",

    # ---------------- ماژول‌ها و مجوزها (v0.7) ----------------
    """
    CREATE TABLE IF NOT EXISTS account_modules (
        account_id INTEGER NOT NULL,
        module     TEXT NOT NULL,
        enabled    INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (account_id, module)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_modules (
        user_id    INTEGER NOT NULL,
        module     TEXT NOT NULL,
        enabled    INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, module)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS role_permissions (
        account_id INTEGER NOT NULL,
        role       TEXT NOT NULL,
        perm       TEXT NOT NULL,
        allowed    INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (account_id, role, perm)
    )
    """,

    # ---------------- کاربران / نشست‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id    INTEGER,
        username      TEXT NOT NULL UNIQUE,
        full_name     TEXT NOT NULL,
        email         TEXT,
        password_hash TEXT,
        google_sub    TEXT,
        totp_secret   TEXT,
        role          TEXT NOT NULL DEFAULT 'operator',
        is_owner      INTEGER NOT NULL DEFAULT 0,
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token           TEXT PRIMARY KEY,
        user_id         INTEGER NOT NULL,
        impersonated_by INTEGER,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at      TEXT NOT NULL,
        last_seen       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS login_attempts (
        username     TEXT PRIMARY KEY,
        attempts     INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT,
        updated_at   TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_resets (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT NOT NULL,
        code       TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used       INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        account_id INTEGER NOT NULL,
        key        TEXT NOT NULL,
        value      TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (account_id, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        user_id     INTEGER,
        action      TEXT NOT NULL,
        entity      TEXT,
        entity_id   TEXT,
        detail      TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ---------------- ارزها (سراسری) ----------------
    """
    CREATE TABLE IF NOT EXISTS currencies (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        code          TEXT NOT NULL UNIQUE,
        name          TEXT NOT NULL,
        symbol        TEXT NOT NULL DEFAULT '',
        minor_name    TEXT,
        decimals      INTEGER NOT NULL DEFAULT 2,
        unit_ratio    INTEGER NOT NULL DEFAULT 100,
        is_active     INTEGER NOT NULL DEFAULT 1,
        sort_order    INTEGER NOT NULL DEFAULT 0,
        serial_pattern TEXT,
        serial_zone   TEXT,
        color_hex     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exchange_rates (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        currency_id INTEGER NOT NULL,
        rate        INTEGER NOT NULL,
        rate_date   TEXT NOT NULL,
        rate_type   TEXT NOT NULL DEFAULT 'market'
                    CHECK(rate_type IN ('market','buy','sell','sana')),
        source      TEXT DEFAULT 'manual',
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(account_id, currency_id, rate_date, rate_type)
    )
    """,

    # ---------------- طرف حساب ----------------
    """
    CREATE TABLE IF NOT EXISTS parties (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        type        TEXT NOT NULL DEFAULT 'customer'
                    CHECK(type IN ('customer','company','supplier','partner','employee')),
        full_name   TEXT NOT NULL,
        phone       TEXT,
        mobile      TEXT,
        national_id TEXT,
        address     TEXT,
        notes       TEXT,
        credit_limit INTEGER,
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ---------------- صندوق‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS cashboxes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        name        TEXT NOT NULL,
        code        TEXT,
        kind        TEXT NOT NULL DEFAULT 'physical' CHECK(kind IN ('physical','bank')),
        description TEXT,
        parent_id   INTEGER,
        currency_id INTEGER,
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(account_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cashbox_opening (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        cashbox_id  INTEGER NOT NULL,
        currency_id INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        as_of_date  TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(cashbox_id, currency_id, as_of_date)
    )
    """,

    # ---------------- گروه عملیات و تراکنش‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS journal (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        jtype        TEXT NOT NULL,
        title        TEXT,
        ref_no       TEXT,
        status       TEXT NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','voided')),
        voided_by    INTEGER,
        voided_at    TEXT,
        void_reason  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        journal_id   INTEGER NOT NULL,
        direction    TEXT NOT NULL CHECK(direction IN ('debit','credit')),
        account_type TEXT NOT NULL CHECK(account_type IN ('cashbox','party','expense','income')),
        cashbox_id   INTEGER,
        party_id     INTEGER,
        expense_id   INTEGER,
        income_id    INTEGER,
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL DEFAULT 0,
        rial_value   INTEGER NOT NULL DEFAULT 0,
        description  TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tx_cashbox ON transactions(cashbox_id, currency_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_party   ON transactions(party_id, currency_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_journal ON transactions(journal_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_acct    ON transactions(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_journal_acct ON journal(account_id, created_at)",

    # ---------------- فاکتورها ----------------
    """
    CREATE TABLE IF NOT EXISTS invoices (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        invoice_no   TEXT NOT NULL,
        invoice_type TEXT NOT NULL CHECK(invoice_type IN ('buy','sell')),
        party_id     INTEGER NOT NULL,
        journal_id   INTEGER,
        status       TEXT NOT NULL DEFAULT 'draft'
                     CHECK(status IN ('draft','confirmed','settled','unsettled','voided')),
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL,
        rate_type    TEXT NOT NULL DEFAULT 'market',
        total_rial   INTEGER NOT NULL,
        fee_minor    INTEGER NOT NULL DEFAULT 0,
        tax_minor    INTEGER NOT NULL DEFAULT 0,
        paid_rial    INTEGER NOT NULL DEFAULT 0,
        description  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        confirmed_at TEXT,
        voided_at    TEXT,
        void_reason  TEXT,
        UNIQUE(account_id, invoice_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inv_party ON invoices(party_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_acct  ON invoices(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_created ON invoices(account_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_party_acct ON parties(account_id, created_at)",

    # ---------------- پرداخت‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS payments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        party_id     INTEGER NOT NULL,
        direction    TEXT NOT NULL CHECK(direction IN ('receive','pay')),
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL DEFAULT 0,
        rial_value   INTEGER NOT NULL DEFAULT 0,
        method       TEXT NOT NULL DEFAULT 'cash',
        journal_id   INTEGER,
        description  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_allocations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL DEFAULT 0,
        payment_id  INTEGER NOT NULL,
        invoice_id  INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ---------------- قرض‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS loans (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        party_id     INTEGER NOT NULL,
        direction    TEXT NOT NULL CHECK(direction IN ('receive','give')),
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL DEFAULT 0,
        due_date     TEXT,
        status       TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','partial','settled','voided')),
        journal_id   INTEGER,
        description  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loan_party ON loans(party_id)",
    "CREATE INDEX IF NOT EXISTS idx_loan_due ON loans(due_date)",
    "CREATE INDEX IF NOT EXISTS idx_rate_cur_date ON exchange_rates(currency_id, rate_date)",

    # ---------------- هزینه و درآمد ----------------
    """
    CREATE TABLE IF NOT EXISTS expense_categories (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name  TEXT NOT NULL UNIQUE,
        kind  TEXT NOT NULL CHECK(kind IN ('expense','income')),
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        category_id  INTEGER,
        title        TEXT NOT NULL,
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL DEFAULT 0,
        rial_value   INTEGER NOT NULL DEFAULT 0,
        method       TEXT DEFAULT 'cash',
        journal_id   INTEGER,
        description  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incomes (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        category_id  INTEGER,
        title        TEXT NOT NULL,
        currency_id  INTEGER NOT NULL,
        amount       INTEGER NOT NULL,
        rate         INTEGER NOT NULL DEFAULT 0,
        rial_value   INTEGER NOT NULL DEFAULT 0,
        method       TEXT DEFAULT 'cash',
        journal_id   INTEGER,
        description  TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ---------------- اسکناس‌ها ----------------
    """
    CREATE TABLE IF NOT EXISTS banknotes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id    INTEGER NOT NULL DEFAULT 0,
        currency_id   INTEGER NOT NULL,
        denomination  INTEGER NOT NULL,
        serial        TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'in_vault'
                      CHECK(status IN ('in_vault','sold','withdrawn','voided')),
        cashbox_id    INTEGER,
        batch_id      INTEGER,
        last_journal_id INTEGER,
        note          TEXT,
        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(account_id, currency_id, denomination, serial)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bn_serial ON banknotes(serial)",
    "CREATE INDEX IF NOT EXISTS idx_bn_account ON banknotes(account_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_bn_batch ON banknotes(batch_id)",
    """
    CREATE TABLE IF NOT EXISTS banknote_images (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        banknote_id  INTEGER NOT NULL,
        file_path    TEXT NOT NULL,
        mime         TEXT,
        type         TEXT NOT NULL DEFAULT 'photo',
        confidence   REAL,
        meta         TEXT,
        note         TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS banknote_batches (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        journal_id   INTEGER,
        invoice_id   INTEGER,
        party_id     INTEGER,
        currency_id  INTEGER,
        source_image TEXT,
        note         TEXT,
        created_by   INTEGER,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS banknote_movements (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL DEFAULT 0,
        banknote_id  INTEGER NOT NULL,
        journal_id   INTEGER,
        movement_type TEXT NOT NULL,
        party_id     INTEGER,
        from_cashbox INTEGER,
        to_cashbox   INTEGER,
        note         TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bnm_banknote ON banknote_movements(banknote_id)",
    "CREATE INDEX IF NOT EXISTS idx_bnm_party ON banknote_movements(party_id)",
    "CREATE INDEX IF NOT EXISTS idx_bnm_journal ON banknote_movements(journal_id)",
    "CREATE INDEX IF NOT EXISTS idx_bni_banknote ON banknote_images(banknote_id)",
]


# ---------------------------------------------------------------------------
# مهاجرت ستون‌های جدید (برای دیتابیس‌های ساخته‌شده با نسخه‌های قبلی)
# ---------------------------------------------------------------------------
_MIGRATIONS = {
    "accounts": [("logo", "TEXT"), ("deleted_at", "TEXT")],
    "users": [("account_id", "INTEGER"), ("google_sub", "TEXT"), ("is_owner", "INTEGER"),
              ("totp_secret", "TEXT"), ("email", "TEXT")],
    "sessions": [("impersonated_by", "INTEGER")],
    "exchange_rates": [("account_id", "INTEGER"), ("rate_type", "TEXT")],
    "parties": [("account_id", "INTEGER"), ("credit_limit", "INTEGER")],
    "cashboxes": [("account_id", "INTEGER"), ("kind", "TEXT"),
                  ("parent_id", "INTEGER"), ("currency_id", "INTEGER")],
    "cashbox_opening": [("account_id", "INTEGER")],
    "journal": [("account_id", "INTEGER")],
    "transactions": [("account_id", "INTEGER")],
    "invoices": [("account_id", "INTEGER"), ("rate_type", "TEXT"),
                 ("fee_minor", "INTEGER"), ("tax_minor", "INTEGER")],
    "payments": [("account_id", "INTEGER")],
    "payment_allocations": [("account_id", "INTEGER")],
    "loans": [("account_id", "INTEGER")],
    "expenses": [("account_id", "INTEGER")],
    "incomes": [("account_id", "INTEGER")],
    "banknotes": [("account_id", "INTEGER"), ("batch_id", "INTEGER")],
    "banknote_images": [("account_id", "INTEGER"), ("type", "TEXT"), ("confidence", "REAL"),
                        ("meta", "TEXT")],
    "banknote_movements": [("account_id", "INTEGER")],
    "audit_log": [("account_id", "INTEGER")],
    "currencies": [("serial_pattern", "TEXT"), ("serial_zone", "TEXT"), ("color_hex", "TEXT"),
                   ("deleted_at", "TEXT"), ("minor_name", "TEXT")],
    "parties": [("account_id", "INTEGER"), ("credit_limit", "INTEGER"), ("deleted_at", "TEXT")],
    "cashboxes": [("account_id", "INTEGER"), ("kind", "TEXT"),
                  ("parent_id", "INTEGER"), ("currency_id", "INTEGER"), ("deleted_at", "TEXT")],
    "users": [("account_id", "INTEGER"), ("google_sub", "TEXT"), ("is_owner", "INTEGER"),
              ("totp_secret", "TEXT"), ("email", "TEXT"), ("deleted_at", "TEXT")],
    "invoices": [("account_id", "INTEGER"), ("rate_type", "TEXT"),
                 ("fee_minor", "INTEGER"), ("tax_minor", "INTEGER"), ("deleted_at", "TEXT")],
    "payments": [("account_id", "INTEGER"), ("deleted_at", "TEXT")],
    "loans": [("account_id", "INTEGER"), ("deleted_at", "TEXT")],
    "expenses": [("account_id", "INTEGER"), ("deleted_at", "TEXT")],
    "incomes": [("account_id", "INTEGER"), ("deleted_at", "TEXT")],
    "banknotes": [("account_id", "INTEGER"), ("batch_id", "INTEGER"), ("deleted_at", "TEXT")],
    "expense_categories": [("deleted_at", "TEXT")],
}


def _to_postgres(stmt):
    s = stmt
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    s = s.replace("DEFAULT (datetime('now'))", "DEFAULT now()")
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    return s


def _add_column(conn, table, col, typ):
    """افزودن ستون در صورت نبود (SQLite و PG)"""
    try:
        if conn_engine(conn) == "postgres":
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
        else:
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    except Exception:
        pass


def _migrate_exchange_rates(conn):
    """چندنرخی: افزودن rate_type و تغییر قید یکتا به (account, currency, date, type)"""
    if conn_engine(conn) == "postgres":
        _add_column(conn, "exchange_rates", "rate_type", "TEXT")
        try:
            conn.execute("ALTER TABLE exchange_rates "
                         "DROP CONSTRAINT IF EXISTS exchange_rates_account_id_currency_id_rate_date_key")
        except Exception:
            pass
        try:
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_er_acc_cur_date_type
                            ON exchange_rates(account_id, currency_id, rate_date, rate_type)""")
        except Exception:
            pass
        return
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(exchange_rates)").fetchall()]
    # اطمینان از وجود قید یکتا برای upsert نرخ‌ها (روی دیتابیس‌های قدیمی)
    try:
        conn.execute("""DELETE FROM exchange_rates WHERE id NOT IN (
            SELECT MIN(id) FROM exchange_rates
            GROUP BY account_id, currency_id, rate_date, rate_type)""")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_er_acc_cur_date_type "
                     "ON exchange_rates(account_id, currency_id, rate_date, rate_type)")
    except Exception:
        pass
    if "rate_type" in cols:
        return
    # بازسازی جدول برای اعمال قید یکتای جدید
    conn.execute("ALTER TABLE exchange_rates RENAME TO exchange_rates_old")
    conn.execute(
        """CREATE TABLE exchange_rates (
               id          INTEGER PRIMARY KEY AUTOINCREMENT,
               account_id  INTEGER NOT NULL DEFAULT 0,
               currency_id INTEGER NOT NULL,
               rate        INTEGER NOT NULL,
               rate_date   TEXT NOT NULL,
               rate_type   TEXT NOT NULL DEFAULT 'market',
               source      TEXT DEFAULT 'manual',
               created_at  TEXT NOT NULL DEFAULT (datetime('now')),
               UNIQUE(account_id, currency_id, rate_date, rate_type))""")
    conn.execute(
        """INSERT INTO exchange_rates(account_id,currency_id,rate,rate_date,rate_type,source,created_at)
           SELECT account_id,currency_id,rate,rate_date,'market',source,created_at FROM exchange_rates_old""")
    conn.execute("DROP TABLE exchange_rates_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_cur_date ON exchange_rates(currency_id, rate_date)")


# ---------------------------------------------------------------------------
# اتصال
# ---------------------------------------------------------------------------
class _PGConn:
    """پوشش اتصال PostgreSQL با رفتار مشابه sqlite3.Connection"""

    is_postgres = True

    def __init__(self, raw):
        self.raw = raw
        self._cur = raw.cursor()

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        self._cur.execute(sql, params)
        return self._cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        try:
            self.raw.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self.raw.rollback()
        except Exception:
            pass
        global _pg_pool
        if _pg_pool is not None:
            _pg_pool.putconn(self.raw)


_int8_registered = False


def _pg_connect():
    global _pg_pool, _int8_registered
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    from psycopg2.extensions import new_type, register_type
    if not _int8_registered:
        from decimal import Decimal

        def _as_int(v):
            if v is None:
                return None
            if isinstance(v, int):
                return v
            if isinstance(v, Decimal):
                return int(v)
            return int(Decimal(str(v)))

        register_type(new_type((20,), "INT8_AS_INT", lambda v, cur: _as_int(v)))
        register_type(new_type((1700,), "NUMERIC_AS_INT", lambda v, cur: _as_int(v)))
        _int8_registered = True
    with _pg_lock:
        if _pg_pool is None:
            _pg_pool = pool.ThreadedConnectionPool(
                2, 12, PG_URL, cursor_factory=RealDictCursor)
    raw = _pg_pool.getconn()
    return _PGConn(raw)


def get_connection(db_path=None):
    if engine(db_path) == "postgres":
        return _pg_connect()
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path=None):
    """اجرای اسکیما + مهاجرت‌ها"""
    conn = get_connection(db_path)
    try:
        if engine(db_path) == "postgres":
            stmts = [_to_postgres(s) for s in SCHEMA_STATEMENTS]
        else:
            stmts = SCHEMA_STATEMENTS
        for stmt in stmts:
            conn.execute(stmt)
        # مهاجرت چندنرخی نرخ‌ها (بازسازی جدول در صورت نیاز)
        _migrate_exchange_rates(conn)
        # مهاجرت ستون‌های جدید
        for table, cols in _MIGRATIONS.items():
            for col, typ in cols:
                _add_column(conn, table, col, typ)
        conn.execute(
            "INSERT INTO settings(account_id,key,value) VALUES(0,'schema_version',?) "
            "ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),))
        conn.commit()
    finally:
        conn.close()


def db_info():
    if engine() == "postgres":
        return {"engine": "postgresql", "url": _mask(PG_URL)}
    return {"engine": "sqlite", "path": DB_PATH}


def _mask(url):
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)
