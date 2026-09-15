# -*- coding: utf-8 -*-
"""
داده‌ی نمونه (چندمشترکی):
    - سوپرادمین: root / root123  (همه‌ی حساب‌ها)
    - حساب ۱ «صرافی مرکزی»: admin/admin123 (مالک)، ali/1234 (صندوق‌دار)، sara/1234 (حسابدار)
    - حساب ۲ «صرافی پارس»: parsadmin/pars123 (مالک) + یک صندوق‌دار
"""

import datetime
import json

from . import schema
from . import finance
from . import auth
from . import context


def _days_ago(n, hour=10, minute=0):
    d = datetime.datetime.now() - datetime.timedelta(days=n)
    return d.replace(hour=hour, minute=minute, second=0).strftime("%Y-%m-%d %H:%M:%S")


def _seed_currencies(conn):
    currencies = [
        # (کد، نام، نماد، نام واحد خُرد، اعشار، ضریب، ترتیب، الگوی سریال، ناحیه سریال، رنگ)
        ("IRR", "ریال ایران", "﷼", "", 0, 1, 0, None, None, None),
        ("USD", "دلار آمریکا", "$", "سنت", 2, 100, 1, r"[A-Za-z]\d{8}[A-Za-z]?", "right", "#85bb65"),
        ("EUR", "یورو", "€", "سنت", 2, 100, 2, r"[A-Za-z]\d{10}[A-Za-z]?", "right", "#9ab0c0"),
        ("AED", "درهم امارات", "د.إ", "فلس", 2, 100, 3, r"\d{7,9}", "right", "#c9a46a"),
        ("TRY", "لیر ترکیه", "₺", "کوروش", 2, 100, 4, r"[A-Za-z]\d{8,9}", "right", "#c05a4a"),
        ("GBP", "پوند انگلیس", "£", "پنی", 2, 100, 5, r"[A-Za-z]{2}\d{8}", "right", "#b08d57"),
        ("IQD", "دینار عراق", "ع.د", "", 0, 1, 6, r"\d{7,10}", "right", "#7f8fa6"),
    ]
    for c in currencies:
        conn.execute(
            "INSERT INTO currencies(code,name,symbol,minor_name,decimals,unit_ratio,sort_order,serial_pattern,serial_zone,color_hex) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", c)
    # نرخ‌های پایه (برای هر دو حساب) — بعداً با نرخ آنلاین قابل به‌روزرسانی است
    today = datetime.date.today()
    base = {"USD": 121000, "EUR": 135000, "AED": 33000, "TRY": 3700, "GBP": 155000, "IQD": 92}
    cids = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM currencies").fetchall()}
    for acct in (1, 2):
        for code, r in base.items():
            for d in range(7, -1, -1):
                dt = (today - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
                drift = r + (7 - d) * 120
                if schema.conn_engine(conn) == "postgres":
                    # در PostgreSQL هدف ON CONFLICT باید دقیقاً با ایندکس یکتا بخواند؛
                    # ایندکس نرخ‌ها چهارستونی است (account, currency, date, rate_type).
                    conn.execute(
                        "INSERT INTO exchange_rates"
                        "(account_id,currency_id,rate,rate_date,rate_type,source) "
                        "VALUES (?,?,?,?,'market','seed') "
                        "ON CONFLICT(account_id,currency_id,rate_date,rate_type) DO NOTHING",
                        (acct, cids[code], drift, dt))
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO exchange_rates"
                        "(account_id,currency_id,rate,rate_date,source) "
                        "VALUES (?,?,?,?,'seed')", (acct, cids[code], drift, dt))
    return cids


def _seed_categories(conn):
    cats = [
        ("اجاره دفتر", "expense"), ("حقوق", "expense"), ("حمل‌ونقل", "expense"),
        ("اینترنت", "expense"), ("هزینه بانکی", "expense"), ("سایر هزینه‌ها", "expense"),
        ("کارمزد", "income"), ("سود معامله", "income"), ("درآمد خدمات", "income"),
    ]
    for name, kind in cats:
        conn.execute("INSERT INTO expense_categories(name,kind) VALUES (?,?)", (name, kind))


def seed(db_path=None, reset=True):
    conn = schema.get_connection(db_path)
    if reset:
        tables = ["payment_allocations", "payments", "banknote_movements", "banknote_images",
                  "banknotes", "incomes", "expenses", "loans", "invoices",
                  "transactions", "journal", "cashbox_opening", "cashboxes", "parties",
                  "exchange_rates", "currencies", "expense_categories", "sessions",
                  "audit_log", "settings", "billing", "plans", "users", "accounts"]
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
        if schema.conn_engine(conn) == "sqlite":
            conn.execute("DELETE FROM sqlite_sequence")
        else:
            # ریست سیکوئنس‌ها در PostgreSQL تا شناسه‌ها از ۱ شروع شوند
            # (فقط جدول‌هایی که ستون سریال id دارند)
            seq_tables = [r["table_name"] for r in conn.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='id' "
                "AND table_name IN (" + ",".join(f"'{t}'" for t in tables) + ")"
            ).fetchall()]
            for t in seq_tables:
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1), (SELECT MAX(id) FROM {t}) IS NOT NULL)")

    cids = _seed_currencies(conn)
    _seed_categories(conn)
    usd_id, eur_id, irr_id = cids["USD"], cids["EUR"], cids["IRR"]

    # ---------------- حساب‌ها ----------------
    conn.execute("INSERT INTO accounts(id,name,phone,plan) VALUES (1,'صرافی مرکزی','02112345678','pro')")
    conn.execute("INSERT INTO accounts(id,name,phone,plan) VALUES (2,'صرافی پارس (شعبه)','02187654321','free')")

    # ---------------- پلن‌های SaaS ----------------
    for p in finance.plan_catalog():
        conn.execute(
            """INSERT INTO plans(code,name,price_rial,period_months,limits_json,features,is_active,sort_order)
               VALUES (?,?,?,?,?,?,1,?)""",
            (p["code"], p["name"], p["price_rial"], p["period_months"],
             json.dumps(p["limits"], ensure_ascii=False), p["features"],
             {"free": 0, "pro": 1, "enterprise": 2}.get(p["code"], 3)))

    # ---------------- کاربران ----------------
    users = [
        # (account_id, username, full_name, role, password, is_owner, email)
        (None, "root", "مدیر کل سیستم", "super_admin", "root123", 0, "root@sarrafi.local"),
        (1, "admin", "مدیر سیستم", "admin", "admin123", 1, "admin@sarrafi.local"),
        (1, "ali", "علی رضایی (صندوق‌دار)", "cashier", "1234", 0, None),
        (1, "sara", "سارا محمدی (حسابدار)", "accountant", "1234", 0, None),
        (2, "parsadmin", "مدیر شعبه پارس", "admin", "pars123", 1, None),
        (2, "parscash", "صندوق‌دار پارس", "cashier", "1234", 0, None),
    ]
    for acct, uname, full, role, pw, owner, email in users:
        conn.execute(
            """INSERT INTO users(account_id,username,full_name,email,password_hash,role,is_owner)
               VALUES (?,?,?,?,?,?,?)""",
            (acct, uname, full, email, auth.hash_password(pw), role, owner))

    # ---------------- صندوق‌ها ----------------
    conn.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (1,'صندوق اصلی','MAIN','physical')")
    conn.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (1,'گاوصندوق','SAFE','physical')")
    conn.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (1,'حساب بانکی ملت','BANK1','bank')")
    conn.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (1,'صندوق شعبه','BRANCH','physical')")
    conn.execute("INSERT INTO cashboxes(account_id,name,code,kind) VALUES (2,'صندوق پارس','PARS','physical')")
    main_cb = conn.execute("SELECT id FROM cashboxes WHERE code='MAIN' AND account_id=1").fetchone()["id"]
    safe_cb = conn.execute("SELECT id FROM cashboxes WHERE code='SAFE' AND account_id=1").fetchone()["id"]
    pars_cb = conn.execute("SELECT id FROM cashboxes WHERE code='PARS' AND account_id=2").fetchone()["id"]

    # ---------------- طرف حساب‌ها (حساب ۱) ----------------
    parties1 = [
        ("customer", "علی محمدی", "09121234567", "0011223344", "تهران، خیابان ولیعصر"),
        ("customer", "رضا کریمی", "09131234568", "0011223345", "تهران، سعادت‌آباد"),
        ("customer", "مریم احمدی", "09141234569", "0011223346", "تهران، نیاوران"),
        ("company", "صرافی پارس", "02188776655", "1010101010", "تهران، فردوسی"),
        ("company", "شرکت بازرگانی آریا", "02188776656", "1010101011", "تهران، مطهری"),
        ("supplier", "تأمین‌کننده ارز کیش", "07644443333", "2020202020", "کیش"),
        ("partner", "همکار مشهد", "05133332222", "3030303030", "مشهد"),
    ]
    for t, name, phone, nid, addr in parties1:
        conn.execute(
            "INSERT INTO parties(account_id,type,full_name,phone,national_id,address) VALUES (1,?,?,?,?,?)",
            (t, name, phone, nid, addr))
    # حساب ۲: دو طرف حساب
    conn.execute("INSERT INTO parties(account_id,type,full_name,phone) VALUES (2,'customer','مشتری پارس','09901111111')")
    conn.execute("INSERT INTO parties(account_id,type,full_name,phone) VALUES (2,'company','همکار پارس','09902222222')")

    ali = conn.execute("SELECT id FROM parties WHERE full_name='علی محمدی' AND account_id=1").fetchone()["id"]
    reza = conn.execute("SELECT id FROM parties WHERE full_name='رضا کریمی' AND account_id=1").fetchone()["id"]
    maryam = conn.execute("SELECT id FROM parties WHERE full_name='مریم احمدی' AND account_id=1").fetchone()["id"]
    pars = conn.execute("SELECT id FROM parties WHERE full_name='صرافی پارس' AND account_id=1").fetchone()["id"]
    arya = conn.execute("SELECT id FROM parties WHERE full_name='شرکت بازرگانی آریا' AND account_id=1").fetchone()["id"]

    # ==================== حساب ۱: عملیات ====================
    context.set_account(1)
    opening_day = _days_ago(7, 9, 0)[:10]

    def opening_tx(cb, cid, amount, label):
        finance.adjust_cashbox(conn, cb, cid, amount, 0, reason=f"موجودی اولیه {label}",
                               user_id=2, account_id=1)

    opening_tx(main_cb, irr_id, 1_000_000_000, "ریال")
    opening_tx(main_cb, usd_id, 10_000 * 100, "دلار")
    opening_tx(safe_cb, usd_id, 5_000 * 100, "دلار (گاوصندوق)")
    opening_tx(main_cb, cids["EUR"], 3_000 * 100, "یورو")
    opening_tx(main_cb, cids["AED"], 25_000 * 100, "درهم")
    opening_tx(main_cb, cids["TRY"], 12_000 * 100, "لیر")

    finance.buy_currency(conn, ali, usd_id, 2_000 * 100, 120_000, main_cb, main_cb,
                         "خرید دلار از علی", user_id=2, account_id=1)
    finance.buy_currency(conn, reza, usd_id, 1_000 * 100, 121_000, main_cb, main_cb,
                         "خرید دلار از رضا", user_id=2, account_id=1)
    finance.sell_currency(conn, arya, usd_id, 800 * 100, 123_000, main_cb, main_cb,
                          "فروش دلار به آریا", user_id=2, account_id=1)
    finance.sell_currency(conn, maryam, usd_id, 500 * 100, 124_000, main_cb, main_cb,
                          "فروش دلار به مریم (نسیه)", user_id=2, payment_method="later", account_id=1)
    finance.register_payment(conn, maryam, "receive", usd_id, 200 * 100, 124_000, main_cb,
                             method="card", description="دریافت بخشی از بدهی مریم",
                             user_id=2, account_id=1)
    finance.buy_currency(conn, pars, eur_id, 2_000 * 100, 134_000, main_cb, main_cb,
                         "خرید یورو از صرافی پارس (نسیه)", user_id=2, payment_method="later", account_id=1)

    finance.loan_receive(conn, arya, usd_id, 5_000 * 100, 122_000, main_cb,
                         "قرض از شرکت آریا", user_id=2, account_id=1)
    arya_loan_id = conn.execute(
        "SELECT id FROM loans WHERE party_id=? AND direction='receive' AND account_id=1 ORDER BY id DESC LIMIT 1",
        (arya,)).fetchone()["id"]
    finance.loan_repay(conn, arya_loan_id, usd_id, 2_000 * 100, 122_500, main_cb,
                       "بازپرداخت بخشی از قرض آریا", user_id=2, account_id=1)

    finance.transfer(conn, main_cb, safe_cb, usd_id, 3_000 * 100, 122_000,
                     "انتقال به گاوصندوق", user_id=1, account_id=1)

    finance.add_expense(conn, "اجاره دفتر — شهریور", irr_id, 80_000_000, 1, main_cb,
                        category_id=1, user_id=1, account_id=1)
    finance.add_expense(conn, "کارمزد بانکی", usd_id, 50 * 100, 122_000, main_cb,
                        category_id=5, user_id=1, account_id=1)
    finance.add_income(conn, "کارمزد خدمات حواله", irr_id, 12_000_000, 1, main_cb,
                       category_id=7, user_id=1, account_id=1)

    finance.buy_currency(conn, ali, usd_id, 1_000 * 100, 121_500, main_cb, main_cb,
                         "خرید دلار از علی", user_id=2, account_id=1)
    finance.sell_currency(conn, arya, usd_id, 700 * 100, 123_500, main_cb, main_cb,
                          "فروش دلار به آریا", user_id=2, account_id=1)
    finance.buy_currency(conn, reza, eur_id, 500 * 100, 134_500, main_cb, main_cb,
                         "خرید یورو از رضا", user_id=2, account_id=1)

    # اسکناس‌ها
    notes = [
        (usd_id, 100 * 100, "AB12345678", "in_vault", main_cb, "خرید از علی محمدی"),
        (usd_id, 100 * 100, "AB12345679", "in_vault", main_cb, "خرید از علی محمدی"),
        (usd_id, 50 * 100, "CD98765432", "sold", None, "فروش به مریم احمدی"),
        (usd_id, 100 * 100, "EF11223344", "in_vault", safe_cb, "انتقال به گاوصندوق"),
        (eur_id, 100 * 100, "XZ55667788", "in_vault", main_cb, "خرید از صرافی پارس"),
        (eur_id, 50 * 100, "XZ55667789", "in_vault", main_cb, "خرید از صرافی پارس"),
    ]
    for cid, denom, serial, status, cb, note in notes:
        conn.execute(
            "INSERT INTO banknotes(account_id,currency_id,denomination,serial,status,cashbox_id,note) "
            "VALUES (1,?,?,?,?,?,?)", (cid, denom, serial, status, cb, note))

    def note_move(serial, mtype, party_id, from_cb, to_cb, day, note):
        bn = conn.execute("SELECT id FROM banknotes WHERE serial=? AND account_id=1", (serial,)).fetchone()
        if not bn:
            return
        conn.execute(
            """INSERT INTO banknote_movements(account_id,banknote_id,movement_type,party_id,
                                              from_cashbox,to_cashbox,note,created_at)
               VALUES (1,?,?,?,?,?,?,?)""",
            (bn["id"], mtype, party_id, from_cb, to_cb, note, day))

    note_move("AB12345678", "purchase", ali, None, main_cb, _days_ago(6, 11), "خرید از علی")
    note_move("CD98765432", "purchase", reza, None, main_cb, _days_ago(5, 12), "خرید از رضا")
    note_move("CD98765432", "sale", maryam, main_cb, None, _days_ago(3, 15), "فروش به مریم")
    note_move("EF11223344", "transfer", None, main_cb, safe_cb, _days_ago(1, 10), "انتقال به گاوصندوق")

    # ==================== حساب ۲: داده‌ی کوچک ====================
    context.set_account(2)
    p2 = conn.execute("SELECT id FROM parties WHERE account_id=2 LIMIT 1").fetchone()["id"]
    finance.adjust_cashbox(conn, pars_cb, usd_id, 2_000 * 100, 0, reason="موجودی اولیه دلار",
                           user_id=5, account_id=2)
    finance.adjust_cashbox(conn, pars_cb, irr_id, 500_000_000, 0, reason="موجودی اولیه ریال",
                           user_id=5, account_id=2)
    finance.buy_currency(conn, p2, usd_id, 500 * 100, 120_500, pars_cb, pars_cb,
                         "خرید دلار از مشتری پارس", user_id=5, account_id=2)

    # ==================== پخش تاریخی معاملات حساب ۱ (برای نمودارهای بهتر) ====================
    # اسناد اصلاح (موجودی اولیه) → ۸ روز قبل
    conn.execute("UPDATE journal SET created_at=? WHERE account_id=1 AND jtype='cash_adjust'",
                 (_days_ago(8, 9, 0),))
    conn.execute(
        "UPDATE transactions SET created_at=? WHERE account_id=1 AND journal_id IN "
        "(SELECT id FROM journal WHERE account_id=1 AND jtype='cash_adjust')",
        (_days_ago(8, 9, 0),))
    # سایر اسناد → به ترتیب از ۷ روز قبل تا امروز (ترتیب حفظ می‌شود تا FIFO دست‌نخورده بماند)
    js = conn.execute(
        "SELECT id FROM journal WHERE account_id=1 AND jtype!='cash_adjust' ORDER BY id").fetchall()
    n = max(1, len(js) - 1)
    for i, r in enumerate(js):
        off = 7 - int(round(7 * i / n))
        ts = _days_ago(off, hour=10 + (i % 8), minute=(i * 7) % 60)
        conn.execute("UPDATE journal SET created_at=? WHERE id=?", (ts, r["id"]))
        conn.execute("UPDATE transactions SET created_at=? WHERE journal_id=?", (ts, r["id"]))
    # همگام‌سازی زمان فاکتورها و هزینه/درآمد/پرداخت/قرض با سندشان
    for inv in conn.execute("SELECT id, journal_id FROM invoices WHERE account_id=1").fetchall():
        ts = conn.execute("SELECT created_at FROM journal WHERE id=?",
                          (inv["journal_id"],)).fetchone()["created_at"]
        conn.execute("UPDATE invoices SET created_at=?, confirmed_at=? WHERE id=?",
                     (ts, ts, inv["id"]))
    for tbl in ("expenses", "incomes", "payments", "loans"):
        for row in conn.execute(
                f"SELECT id, journal_id FROM {tbl} WHERE account_id=1 AND journal_id IS NOT NULL").fetchall():
            ts = conn.execute("SELECT created_at FROM journal WHERE id=?",
                              (row["journal_id"],)).fetchone()["created_at"]
            conn.execute(f"UPDATE {tbl} SET created_at=? WHERE id=?", (ts, row["id"]))

    conn.commit()
    conn.close()
    context.set_account(0)
    return {"ok": True}


def reset_and_seed(db_path=None):
    schema.init_db(db_path)
    return seed(db_path, reset=True)
