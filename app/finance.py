# -*- coding: utf-8 -*-
"""
هسته‌ی مالی — موتور تراکنش دوپایه‌ی ساده (چندمشترکی)

قاعده‌ی علامت:
    debit  = ورود به صندوق / افزایش دارایی
    credit = خروج از صندوق / کاهش دارایی

مانده‌ی صندوق   = جمع(debit) - جمع(credit)
مانده‌ی طرف‌حساب = جمع(credit) - جمع(debit)  → مثبت یعنی ما بدهکاریم

همه‌ی عملیات در «حساب» جاری (context.get_account) ایزوله می‌شوند.
"""

from decimal import Decimal, ROUND_HALF_UP
import json
from datetime import datetime, date, timedelta

from . import schema
from . import util
from . import context


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return date.today().strftime("%Y-%m-%d")


def _acct(account_id=None):
    return context.get_account() if account_id is None else int(account_id)


def to_major(amount, currency):
    if amount is None:
        return "0"
    ratio = currency["unit_ratio"] or 1
    d = Decimal(amount) / Decimal(ratio)
    return str(d.quantize(Decimal(1).scaleb(-currency["decimals"]), rounding=ROUND_HALF_UP))


def to_minor(amount, currency):
    ratio = currency["unit_ratio"] or 1
    d = Decimal(str(amount)) * Decimal(ratio)
    return int(d.to_integral_value(rounding=ROUND_HALF_UP))


def fmt(amount, currency):
    ratio = currency["unit_ratio"] or 1
    d = Decimal(amount) / Decimal(ratio)
    d = d.quantize(Decimal(1).scaleb(-currency["decimals"]), rounding=ROUND_HALF_UP)
    return f"{d:,.{currency['decimals']}f}"


# ---------------------------------------------------------------------------
def _add_leg(conn, journal_id, direction, account_type, currency_id, amount,
             rate, rial_value, cashbox_id=None, party_id=None,
             expense_id=None, income_id=None, description="", account_id=None):
    conn.execute(
        """INSERT INTO transactions
           (account_id, journal_id, direction, account_type, cashbox_id, party_id,
            expense_id, income_id, currency_id, amount, rate, rial_value, description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), journal_id, direction, account_type, cashbox_id, party_id,
         expense_id, income_id, currency_id, int(amount), int(rate),
         int(rial_value), description))


def _new_journal(conn, jtype, title, ref_no=None, created_by=None, account_id=None):
    cur = conn.execute(
        "INSERT INTO journal(account_id,jtype,title,ref_no,created_by) VALUES (?,?,?,?,?) RETURNING id",
        (_acct(account_id), jtype, title, ref_no, created_by))
    return cur.fetchone()["id"]


def _audit(conn, user_id, action, entity, entity_id, detail, account_id=None):
    conn.execute(
        "INSERT INTO audit_log(account_id,user_id,action,entity,entity_id,detail) VALUES (?,?,?,?,?,?)",
        (_acct(account_id), user_id, action, entity, entity_id, detail))


def _next_invoice_no(conn, itype, account_id=None):
    prefix = "B" if itype == "buy" else "S"
    year = util.fa_year()
    acct = _acct(account_id)
    cur = conn.execute(
        "SELECT COUNT(*) c FROM invoices WHERE account_id=? AND invoice_no LIKE ?",
        (acct, f"{prefix}{year}-%"))
    n = cur.fetchone()["c"] + 1
    return f"{prefix}{year}-{n:05d}"


def _currency(conn, currency_id):
    return conn.execute("SELECT * FROM currencies WHERE id=?", (currency_id,)).fetchone()


def _irr(conn):
    return conn.execute("SELECT * FROM currencies WHERE code='IRR'").fetchone()


def _cashbox_currency_balance(conn, cashbox_id, currency_id, as_of=None, account_id=None):
    sql = """SELECT COALESCE(SUM(CASE WHEN direction='debit' THEN amount ELSE -amount END),0) b
             FROM transactions t JOIN journal j ON j.id=t.journal_id
             WHERE t.account_id=? AND t.cashbox_id=? AND t.currency_id=? AND j.status='posted'"""
    args = [_acct(account_id), cashbox_id, currency_id]
    if as_of:
        sql += " AND t.created_at <= ?"
        args.append(as_of)
    row = conn.execute(sql, args).fetchone()
    return row["b"]


def cashbox_balances(conn, cashbox_id, as_of=None, account_id=None):
    out = {}
    rows = conn.execute("SELECT * FROM currencies WHERE is_active=1 ORDER BY sort_order, id").fetchall()
    for c in rows:
        out[c["code"]] = _cashbox_currency_balance(conn, cashbox_id, c["id"], as_of, account_id)
    return out


def party_balances(conn, party_id, account_id=None):
    out = {}
    rows = conn.execute(
        """SELECT t.currency_id, SUM(CASE WHEN t.direction='credit' THEN t.amount ELSE -t.amount END) bal,
                  SUM(CASE WHEN t.direction='credit' THEN t.rial_value ELSE -t.rial_value END) bal_rial
           FROM transactions t JOIN journal j ON j.id=t.journal_id
           WHERE t.account_id=? AND t.party_id=? AND j.status='posted'
           GROUP BY t.currency_id""", (_acct(account_id), party_id)).fetchall()
    for r in rows:
        out[r["currency_id"]] = {"amount": r["bal"], "rial": r["bal_rial"]}
    return out


def all_party_balances(conn, account_id=None):
    return conn.execute(
        """SELECT p.id party_id, p.full_name, p.type,
                  t.currency_id, c.code, c.symbol, c.sort_order,
                  SUM(CASE WHEN t.direction='credit' THEN t.amount ELSE -t.amount END) bal
           FROM transactions t
           JOIN journal j ON j.id=t.journal_id
           JOIN parties p ON p.id=t.party_id
           JOIN currencies c ON c.id=t.currency_id
           WHERE j.status='posted' AND t.account_id=?
           GROUP BY p.id, p.full_name, p.type, t.currency_id,
                    c.code, c.symbol, c.sort_order
           ORDER BY p.full_name, c.sort_order""", (_acct(account_id),)).fetchall()


# ---------------------------------------------------------------------------
# خرید ارز
# ---------------------------------------------------------------------------
def buy_currency(conn, party_id, currency_id, amount_minor, rate,
                 cashbox_foreign_id, cashbox_rial_id, description="",
                 user_id=None, confirm=True, payment_method="cash",
                 fee_minor=0, tax_minor=0, rate_type="market", account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    fee_rial = int(Decimal(fee_minor or 0) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    tax_rial = int(Decimal(tax_minor or 0) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    total_rial = rial_value + fee_rial + tax_rial
    jid = _new_journal(conn, "buy", f"خرید ارز — {cur['code']}", created_by=user_id, account_id=account_id)

    _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_foreign_id, description=description, account_id=account_id)
    if payment_method == "later":
        _add_leg(conn, jid, "credit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=party_id, description=description, account_id=account_id)
    else:
        irr = _irr(conn)
        _add_leg(conn, jid, "credit", "cashbox", irr["id"], total_rial, 1, total_rial,
                 cashbox_id=cashbox_rial_id, description=description, account_id=account_id)

    inv_no = _next_invoice_no(conn, "buy", account_id)
    icur = conn.execute(
        """INSERT INTO invoices(account_id,invoice_no,invoice_type,party_id,journal_id,status,
                                currency_id,amount,rate,rate_type,total_rial,fee_minor,tax_minor,
                                paid_rial,description,created_by,confirmed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (_acct(account_id), inv_no, "buy", party_id, jid,
         "confirmed" if confirm else "draft",
         currency_id, int(amount_minor), int(rate), rate_type, total_rial,
         int(fee_minor or 0), int(tax_minor or 0),
         0 if payment_method == "later" else total_rial,
         description, user_id, _now() if confirm else None))
    invoice_id = icur.fetchone()["id"]
    _audit(conn, user_id, "buy", "invoice", inv_no, json.dumps(
        {"party": party_id, "currency": currency_id, "amount": amount_minor, "rate": rate,
         "fee": fee_minor, "tax": tax_minor, "rate_type": rate_type},
        ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid, "invoice_id": invoice_id, "invoice_no": inv_no,
            "rial_value": rial_value, "total_rial": total_rial,
            "fee_rial": fee_rial, "tax_rial": tax_rial}


# ---------------------------------------------------------------------------
# فروش ارز
# ---------------------------------------------------------------------------
def sell_currency(conn, party_id, currency_id, amount_minor, rate,
                  cashbox_foreign_id, cashbox_rial_id, description="",
                  user_id=None, confirm=True, payment_method="cash",
                  allow_negative=False, fee_minor=0, tax_minor=0,
                  rate_type="market", account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    fee_rial = int(Decimal(fee_minor or 0) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    tax_rial = int(Decimal(tax_minor or 0) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    total_rial = rial_value + fee_rial + tax_rial

    if not allow_negative:
        bal = _cashbox_currency_balance(conn, cashbox_foreign_id, currency_id, account_id=account_id)
        if bal < amount_minor:
            raise ValueError(
                f"موجودی کافی نیست: موجودی {cur['code']} برابر {to_major(bal, cur)} است.")

    jid = _new_journal(conn, "sell", f"فروش ارز — {cur['code']}", created_by=user_id, account_id=account_id)

    _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_foreign_id, description=description, account_id=account_id)
    if payment_method == "later":
        _add_leg(conn, jid, "debit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=party_id, description=description, account_id=account_id)
    else:
        irr = _irr(conn)
        _add_leg(conn, jid, "debit", "cashbox", irr["id"], total_rial, 1, total_rial,
                 cashbox_id=cashbox_rial_id, description=description, account_id=account_id)

    inv_no = _next_invoice_no(conn, "sell", account_id)
    icur = conn.execute(
        """INSERT INTO invoices(account_id,invoice_no,invoice_type,party_id,journal_id,status,
                                currency_id,amount,rate,rate_type,total_rial,fee_minor,tax_minor,
                                paid_rial,description,created_by,confirmed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (_acct(account_id), inv_no, "sell", party_id, jid,
         "confirmed" if confirm else "draft",
         currency_id, int(amount_minor), int(rate), rate_type, total_rial,
         int(fee_minor or 0), int(tax_minor or 0),
         0 if payment_method == "later" else total_rial,
         description, user_id, _now() if confirm else None))
    invoice_id = icur.fetchone()["id"]
    _audit(conn, user_id, "sell", "invoice", inv_no, json.dumps(
        {"party": party_id, "currency": currency_id, "amount": amount_minor, "rate": rate,
         "fee": fee_minor, "tax": tax_minor, "rate_type": rate_type},
        ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid, "invoice_id": invoice_id, "invoice_no": inv_no,
            "rial_value": rial_value, "total_rial": total_rial,
            "fee_rial": fee_rial, "tax_rial": tax_rial}


# ---------------------------------------------------------------------------
# قرض
# ---------------------------------------------------------------------------
def loan_receive(conn, party_id, currency_id, amount_minor, rate,
                 cashbox_id, description="", user_id=None, due_date=None, account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "loan_receive", f"دریافت قرض — {cur['code']}", created_by=user_id, account_id=account_id)
    _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_id, description=description, account_id=account_id)
    _add_leg(conn, jid, "credit", "party", currency_id, amount_minor, rate, rial_value,
             party_id=party_id, description=description, account_id=account_id)
    conn.execute(
        """INSERT INTO loans(account_id,party_id,direction,currency_id,amount,rate,status,due_date,journal_id,description,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), party_id, "receive", currency_id, int(amount_minor), int(rate),
         "open", due_date, jid, description, user_id))
    _audit(conn, user_id, "loan_receive", "loan", None, json.dumps(
        {"party": party_id, "currency": currency_id, "amount": amount_minor}, ensure_ascii=False),
        account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


def loan_give(conn, party_id, currency_id, amount_minor, rate,
              cashbox_id, description="", user_id=None, allow_negative=False,
              due_date=None, account_id=None):
    cur = _currency(conn, currency_id)
    if not allow_negative:
        bal = _cashbox_currency_balance(conn, cashbox_id, currency_id, account_id=account_id)
        if bal < amount_minor:
            raise ValueError("موجودی کافی برای قرض دادن نیست.")
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "loan_give", f"قرض دادن — {cur['code']}", created_by=user_id, account_id=account_id)
    _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_id, description=description, account_id=account_id)
    _add_leg(conn, jid, "debit", "party", currency_id, amount_minor, rate, rial_value,
             party_id=party_id, description=description, account_id=account_id)
    conn.execute(
        """INSERT INTO loans(account_id,party_id,direction,currency_id,amount,rate,status,due_date,journal_id,description,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), party_id, "give", currency_id, int(amount_minor), int(rate),
         "open", due_date, jid, description, user_id))
    _audit(conn, user_id, "loan_give", "loan", None, json.dumps(
        {"party": party_id, "currency": currency_id, "amount": amount_minor}, ensure_ascii=False),
        account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


def loan_repay(conn, loan_id, currency_id, amount_minor, rate,
               cashbox_id, description="", user_id=None, allow_negative=False, account_id=None):
    loan = conn.execute("SELECT * FROM loans WHERE id=? AND account_id=?",
                        (loan_id, _acct(account_id))).fetchone()
    if not loan:
        raise ValueError("قرض یافت نشد")
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "loan_repay", f"بازپرداخت قرض — {cur['code']}", created_by=user_id, account_id=account_id)
    if loan["direction"] == "receive":
        if not allow_negative:
            bal = _cashbox_currency_balance(conn, cashbox_id, currency_id, account_id=account_id)
            if bal < amount_minor:
                raise ValueError("موجودی کافی برای بازپرداخت نیست.")
        _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
                 cashbox_id=cashbox_id, description=description, account_id=account_id)
        _add_leg(conn, jid, "debit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=loan["party_id"], description=description, account_id=account_id)
    else:
        _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
                 cashbox_id=cashbox_id, description=description, account_id=account_id)
        _add_leg(conn, jid, "credit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=loan["party_id"], description=description, account_id=account_id)
    # به‌روزرسانی وضعیت قرض بر اساس بازپرداخت‌ها
    repaid = conn.execute(
        """SELECT COALESCE(SUM(t.amount),0) s FROM transactions t
           JOIN journal j ON j.id=t.journal_id
           WHERE j.jtype='loan_repay' AND j.status='posted'
             AND t.account_id=? AND t.account_type='party'
             AND t.party_id=? AND t.currency_id=?""",
        (_acct(account_id), loan["party_id"], currency_id)).fetchone()["s"]
    repaid = int(repaid or 0)
    new_status = "settled" if repaid >= int(loan["amount"]) else "partial"
    conn.execute("UPDATE loans SET status=? WHERE id=?", (new_status, loan_id))
    _audit(conn, user_id, "loan_repay", "loan", loan_id, json.dumps(
        {"amount": amount_minor, "currency": currency_id}, ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


# ---------------------------------------------------------------------------
# انتقال بین صندوق
# ---------------------------------------------------------------------------
def transfer(conn, from_cashbox, to_cashbox, currency_id, amount_minor, rate,
             description="", user_id=None, allow_negative=False, account_id=None):
    if from_cashbox == to_cashbox:
        raise ValueError("صندوق مبدأ و مقصد یکسان است.")
    cur = _currency(conn, currency_id)
    if not allow_negative:
        bal = _cashbox_currency_balance(conn, from_cashbox, currency_id, account_id=account_id)
        if bal < amount_minor:
            raise ValueError("موجودی صندوق مبدأ کافی نیست.")
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "transfer", f"انتقال بین صندوق — {cur['code']}", created_by=user_id, account_id=account_id)
    _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=from_cashbox, description=description, account_id=account_id)
    _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=to_cashbox, description=description, account_id=account_id)
    _audit(conn, user_id, "transfer", "cashbox", from_cashbox, json.dumps(
        {"to": to_cashbox, "currency": currency_id, "amount": amount_minor}, ensure_ascii=False),
        account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


# ---------------------------------------------------------------------------
# پرداخت / تسویه
# ---------------------------------------------------------------------------
def register_payment(conn, party_id, direction, currency_id, amount_minor, rate,
                     cashbox_id, method="cash", description="", user_id=None, account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "payment",
                       f"{'دریافت' if direction == 'receive' else 'پرداخت'} — {cur['code']}",
                       created_by=user_id, account_id=account_id)
    if direction == "receive":
        _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
                 cashbox_id=cashbox_id, description=description, account_id=account_id)
        _add_leg(conn, jid, "credit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=party_id, description=description, account_id=account_id)
    else:
        _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
                 cashbox_id=cashbox_id, description=description, account_id=account_id)
        _add_leg(conn, jid, "debit", "party", currency_id, amount_minor, rate, rial_value,
                 party_id=party_id, description=description, account_id=account_id)
    conn.execute(
        """INSERT INTO payments(account_id,party_id,direction,currency_id,amount,rate,rial_value,method,journal_id,description,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), party_id, direction, currency_id, int(amount_minor), int(rate),
         rial_value, method, jid, description, user_id))
    _audit(conn, user_id, "payment", "payment", None, json.dumps(
        {"party": party_id, "direction": direction, "currency": currency_id,
         "amount": amount_minor}, ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


# ---------------------------------------------------------------------------
# هزینه و درآمد
# ---------------------------------------------------------------------------
def add_expense(conn, title, currency_id, amount_minor, rate, cashbox_id,
                category_id=None, description="", user_id=None, account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "expense", f"هزینه — {title}", created_by=user_id, account_id=account_id)
    _add_leg(conn, jid, "credit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_id, description=description, account_id=account_id)
    _add_leg(conn, jid, "debit", "expense", currency_id, amount_minor, rate, rial_value,
             expense_id=category_id or 0, description=title, account_id=account_id)
    conn.execute(
        """INSERT INTO expenses(account_id,category_id,title,currency_id,amount,rate,rial_value,journal_id,description,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), category_id, title, currency_id, int(amount_minor), int(rate),
         rial_value, jid, description, user_id))
    _audit(conn, user_id, "expense", "expense", None, json.dumps(
        {"title": title, "amount": amount_minor}, ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


def add_income(conn, title, currency_id, amount_minor, rate, cashbox_id,
               category_id=None, description="", user_id=None, account_id=None):
    cur = _currency(conn, currency_id)
    rial_value = int(Decimal(amount_minor) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "income", f"درآمد — {title}", created_by=user_id, account_id=account_id)
    _add_leg(conn, jid, "debit", "cashbox", currency_id, amount_minor, rate, rial_value,
             cashbox_id=cashbox_id, description=description, account_id=account_id)
    _add_leg(conn, jid, "credit", "income", currency_id, amount_minor, rate, rial_value,
             income_id=category_id or 0, description=title, account_id=account_id)
    conn.execute(
        """INSERT INTO incomes(account_id,category_id,title,currency_id,amount,rate,rial_value,journal_id,description,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (_acct(account_id), category_id, title, currency_id, int(amount_minor), int(rate),
         rial_value, jid, description, user_id))
    _audit(conn, user_id, "income", "income", None, json.dumps(
        {"title": title, "amount": amount_minor}, ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


# ---------------------------------------------------------------------------
# اصلاح صندوق
# ---------------------------------------------------------------------------
def adjust_cashbox(conn, cashbox_id, currency_id, amount_minor, rate,
                   reason="", user_id=None, allow_negative=False, account_id=None):
    cur = _currency(conn, currency_id)
    abs_amount = abs(amount_minor)
    if amount_minor < 0 and not allow_negative:
        bal = _cashbox_currency_balance(conn, cashbox_id, currency_id, account_id=account_id)
        if bal < abs_amount:
            raise ValueError("موجودی کافی برای کسر نیست.")
    rial_value = int(Decimal(abs_amount) * Decimal(rate) / Decimal(cur["unit_ratio"]))
    jid = _new_journal(conn, "cash_adjust", f"اصلاح صندوق — {reason or cur['code']}",
                       created_by=user_id, account_id=account_id)
    if amount_minor > 0:
        _add_leg(conn, jid, "debit", "cashbox", currency_id, abs_amount, rate, rial_value,
                 cashbox_id=cashbox_id, description=reason, account_id=account_id)
    else:
        _add_leg(conn, jid, "credit", "cashbox", currency_id, abs_amount, rate, rial_value,
                 cashbox_id=cashbox_id, description=reason, account_id=account_id)
    _audit(conn, user_id, "cash_adjust", "cashbox", cashbox_id, json.dumps(
        {"currency": currency_id, "amount": amount_minor, "reason": reason}, ensure_ascii=False),
        account_id=account_id)
    conn.commit()
    return {"journal_id": jid}


# ---------------------------------------------------------------------------
# لغو سند
# ---------------------------------------------------------------------------
def void_journal(conn, journal_id, reason, user_id=None, account_id=None):
    j = conn.execute("SELECT * FROM journal WHERE id=? AND account_id=?",
                     (journal_id, _acct(account_id))).fetchone()
    if not j:
        raise ValueError("سند یافت نشد.")
    if j["status"] == "voided":
        raise ValueError("سند قبلاً لغو شده است.")
    conn.execute(
        "UPDATE journal SET status='voided', voided_by=?, voided_at=?, void_reason=? WHERE id=?",
        (user_id, _now(), reason, journal_id))
    conn.execute(
        "UPDATE invoices SET status='voided', voided_at=?, void_reason=? WHERE journal_id=?",
        (_now(), reason, journal_id))
    conn.execute(
        "UPDATE banknotes SET status='in_vault' WHERE last_journal_id=? AND status='sold'",
        (journal_id,))
    _audit(conn, user_id, "void", "journal", journal_id, json.dumps(
        {"reason": reason}, ensure_ascii=False), account_id=account_id)
    conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# حذف نرم (v0.8) — همه‌ی موجودیت‌ها + هشدار قبل از حذف
# ---------------------------------------------------------------------------
TYPE_FA = {
    "party": "طرف حساب", "cashbox": "صندوق", "currency": "ارز", "user": "کاربر",
    "invoice": "فاکتور", "banknote": "اسکناس", "expense": "هزینه", "income": "درآمد",
    "loan": "قرض", "payment": "پرداخت / تسویه", "category": "دسته‌ی هزینه/درآمد",
    "account": "حساب (مشترک)",
}

# انواعی که حذف آن‌ها صرفاً «پنهان‌کردن» است و اثر مالی ندارد
REVERSIBLE_TYPES = {"party", "cashbox", "currency", "user", "banknote", "category", "account"}


def delete_preview(conn, typ, eid, account_id=None, actor=None):
    """آنچه حذف می‌شود + هشدارها، برای نمایش در پنجره‌ی تأیید."""
    acct = _acct(account_id)
    eid = int(eid)
    out = {"type": typ, "id": eid, "label": TYPE_FA.get(typ, typ),
           "name": "", "warnings": [], "reversible": typ in REVERSIBLE_TYPES,
           "blocked": False, "blocked_reason": None}

    if typ == "party":
        p = conn.execute("SELECT * FROM parties WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not p:
            raise ValueError("طرف حساب یافت نشد")
        out["name"] = p["full_name"]
        n_inv = conn.execute("SELECT COUNT(*) c FROM invoices WHERE party_id=? AND deleted_at IS NULL",
                             (eid,)).fetchone()["c"]
        if n_inv:
            out["warnings"].append(f"این {TYPE_FA['party']} {n_inv} فاکتور ثبت‌شده دارد.")
        for cid, b in party_balances(conn, eid).items():
            if b["amount"]:
                cur = conn.execute("SELECT * FROM currencies WHERE id=?", (cid,)).fetchone()
                sign = "به شما بدهکار است" if b["amount"] < 0 else "شما به او بدهکارید"
                out["warnings"].append(
                    f"مانده‌ی حساب: {fmt(abs(b['amount']), cur)} {cur['code']} ({sign}).")
        n_loan = conn.execute("SELECT COUNT(*) c FROM loans WHERE party_id=? AND status IN ('open','partial') AND deleted_at IS NULL",
                              (eid,)).fetchone()["c"]
        if n_loan:
            out["warnings"].append(f"{n_loan} قرض باز/نیمه‌باز دارد.")
        if not out["warnings"]:
            out["warnings"].append("گردش مالی ندارد.")
        out["warnings"].append("با حذف، از فهرست مشتریان و فرم‌ها پنهان می‌شود؛ داده‌ها حفظ و قابل بازیابی است.")

    elif typ == "cashbox":
        cb = conn.execute("SELECT * FROM cashboxes WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not cb:
            raise ValueError("صندوق یافت نشد")
        out["name"] = cb["name"]
        n_active = conn.execute("SELECT COUNT(*) c FROM cashboxes WHERE account_id=? AND deleted_at IS NULL",
                                (acct,)).fetchone()["c"]
        if n_active <= 1:
            out["blocked"] = True
            out["blocked_reason"] = "این آخرین صندوق فعال حساب است و قابل حذف نیست."
        kids = conn.execute("SELECT COUNT(*) c FROM cashboxes WHERE parent_id=? AND deleted_at IS NULL",
                            (eid,)).fetchone()["c"]
        if kids:
            out["warnings"].append(f"{kids} زیرشاخه دارد که آن‌ها هم پنهان می‌شوند.")
        for code, b in cashbox_balances(conn, eid).items():
            if b:
                cur = conn.execute("SELECT * FROM currencies WHERE code=?", (code,)).fetchone()
                if cur:
                    out["warnings"].append(f"موجودی فعلی: {fmt(b, cur)} {cur['code']}.")
        if not out["warnings"]:
            out["warnings"].append("صندوق خالی است.")
        out["warnings"].append("تراکنش‌های قبلی این صندوق در گزارش‌ها می‌مانند؛ فقط از فهرست صندوق‌ها پنهان می‌شود.")

    elif typ == "currency":
        c = conn.execute("SELECT * FROM currencies WHERE id=?", (eid,)).fetchone()
        if not c:
            raise ValueError("ارز یافت نشد")
        out["name"] = f"{c['name']} ({c['code']})"
        n_active = conn.execute("SELECT COUNT(*) c FROM currencies WHERE is_active=1 AND deleted_at IS NULL").fetchone()["c"]
        if n_active <= 1:
            out["blocked"] = True
            out["blocked_reason"] = "این آخرین ارز فعال سیستم است و قابل حذف نیست."
        n_inv = conn.execute("SELECT COUNT(*) c FROM invoices WHERE currency_id=? AND deleted_at IS NULL", (eid,)).fetchone()["c"]
        n_bn = conn.execute("SELECT COUNT(*) c FROM banknotes WHERE currency_id=? AND deleted_at IS NULL", (eid,)).fetchone()["c"]
        if n_inv or n_bn:
            out["warnings"].append(f"{n_inv} فاکتور و {n_bn} اسکناس با این ارز ثبت شده است.")
        out["warnings"].append("این ارز سراسری است؛ با حذف، از همه‌ی حساب‌ها پنهان می‌شود (قابل بازیابی).")

    elif typ == "user":
        u = conn.execute("SELECT * FROM users WHERE id=?", (eid,)).fetchone()
        if not u:
            raise ValueError("کاربر یافت نشد")
        out["name"] = u["full_name"] or u["username"]
        out["warnings"].append(f"نقش: {u['role']} — نام کاربری: {u['username']}")
        if u["role"] == "super_admin":
            n_sa = conn.execute(
                "SELECT COUNT(*) c FROM users WHERE role='super_admin' AND is_active=1 AND deleted_at IS NULL"
            ).fetchone()["c"]
            if n_sa <= 1:
                out["blocked"] = True
                out["blocked_reason"] = "این آخرین سوپرادمین فعال سیستم است و قابل حذف نیست."
            elif actor and actor.get("role") != "super_admin":
                out["blocked"] = True
                out["blocked_reason"] = "فقط سوپرادمین می‌تواند کاربر سوپرادمین را حذف کند."
        out["warnings"].append("کاربر دیگر نمی‌تواند وارد شود؛ سوابق و لاگ‌هایش حفظ می‌شود (قابل بازیابی).")

    elif typ == "invoice":
        inv = conn.execute("SELECT * FROM invoices WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not inv:
            raise ValueError("فاکتور یافت نشد")
        cur = conn.execute("SELECT * FROM currencies WHERE id=?", (inv["currency_id"],)).fetchone()
        out["name"] = inv["invoice_no"]
        out["warnings"].append(f"مبلغ: {fmt(inv['amount'], cur)} {cur['code']} — "
                               f"معادل {inv['total_rial']:,} ریال")
        if inv["status"] != "voided":
            out["warnings"].append("با حذف، سند مالی فاکتور نیز لغو می‌شود و اثر آن از مانده‌ها حذف می‌گردد.")
        else:
            out["warnings"].append("این فاکتور قبلاً لغو شده است؛ فقط از فهرست پنهان می‌شود.")

    elif typ == "banknote":
        b = conn.execute("SELECT * FROM banknotes WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not b:
            raise ValueError("اسکناس یافت نشد")
        cur = conn.execute("SELECT * FROM currencies WHERE id=?", (b["currency_id"],)).fetchone()
        out["name"] = b["serial"]
        out["warnings"].append(f"ارزش: {fmt(b['denomination'], cur)} {cur['code']}")
        n_mv = conn.execute("SELECT COUNT(*) c FROM banknote_movements WHERE banknote_id=?", (eid,)).fetchone()["c"]
        if n_mv:
            out["warnings"].append(f"{n_mv} رکورد در تاریخچه‌ی مالکیت دارد (حفظ می‌شود).")
        out["warnings"].append("اسکناس از فهرست‌ها پنهان می‌شود (قابل بازیابی).")

    elif typ in ("expense", "income"):
        tbl = "expenses" if typ == "expense" else "incomes"
        e = conn.execute(f"SELECT * FROM {tbl} WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not e:
            raise ValueError(TYPE_FA[typ] + " یافت نشد")
        cur = conn.execute("SELECT * FROM currencies WHERE id=?", (e["currency_id"],)).fetchone()
        out["name"] = e["title"]
        out["warnings"].append(f"مبلغ: {fmt(e['amount'], cur)} {cur['code']}")
        out["warnings"].append("با حذف، سند مالی لغو و اثر آن از مانده‌ها حذف می‌شود.")

    elif typ == "loan":
        l = conn.execute("SELECT * FROM loans WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not l:
            raise ValueError("قرض یافت نشد")
        cur = conn.execute("SELECT * FROM currencies WHERE id=?", (l["currency_id"],)).fetchone()
        p = conn.execute("SELECT full_name FROM parties WHERE id=?", (l["party_id"],)).fetchone()
        out["name"] = f"{p['full_name'] if p else '؟'} — {fmt(l['amount'], cur)} {cur['code']}"
        if l["status"] in ("open", "partial"):
            out["warnings"].append("این قرض هنوز تسویه نشده است؛ با حذف، سند آن لغو می‌شود.")
        else:
            out["warnings"].append("سند این قرض لغو و از فهرست پنهان می‌شود.")

    elif typ == "payment":
        pm = conn.execute("SELECT * FROM payments WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if not pm:
            raise ValueError("پرداخت یافت نشد")
        cur = conn.execute("SELECT * FROM currencies WHERE id=?", (pm["currency_id"],)).fetchone()
        out["name"] = f"{TYPE_FA['payment']} — {fmt(pm['amount'], cur)} {cur['code']}"
        out["warnings"].append("با حذف، سند مالی لغو و اثر آن از مانده‌ها حذف می‌شود.")

    elif typ == "category":
        c = conn.execute("SELECT * FROM expense_categories WHERE id=?", (eid,)).fetchone()
        if not c:
            raise ValueError("دسته یافت نشد")
        out["name"] = c["name"]
        out["warnings"].append("با حذف، از فهرست دسته‌ها پنهان می‌شود (قابل بازیابی).")

    elif typ == "account":
        a = conn.execute("SELECT * FROM accounts WHERE id=?", (eid,)).fetchone()
        if not a:
            raise ValueError("حساب (مشترک) یافت نشد")
        out["name"] = a["name"]
        n_users = conn.execute("SELECT COUNT(*) c FROM users WHERE account_id=? AND deleted_at IS NULL",
                               (eid,)).fetchone()["c"]
        n_inv = conn.execute("SELECT COUNT(*) c FROM invoices WHERE account_id=? AND deleted_at IS NULL",
                             (eid,)).fetchone()["c"]
        n_bn = conn.execute("SELECT COUNT(*) c FROM banknotes WHERE account_id=? AND deleted_at IS NULL",
                            (eid,)).fetchone()["c"]
        n_tx = conn.execute("SELECT COUNT(*) c FROM transactions WHERE account_id=?", (eid,)).fetchone()["c"]
        if n_users:
            out["warnings"].append(f"{n_users} کاربر دارد که پس از حذف امکان ورود نخواهند داشت.")
        out["warnings"].append(
            f"{n_inv} فاکتور، {n_bn} اسکناس و {n_tx} تراکنش در این حساب ثبت شده است.")
        if a["status"] != "suspended":
            out["warnings"].append("این حساب در حال حاضر فعال است؛ با حذف، دسترسی همه‌ی کاربرانش قطع می‌شود.")
        out["warnings"].append("داده‌های حساب حفظ و قابل بازیابی است (حذف نرم).")

    else:
        raise ValueError("نوع نامعتبر است")

    return out


def delete_entity(conn, typ, eid, user_id, account_id=None, self_id=None):
    """حذف نرم: پنهان‌کردن + (برای اسناد مالی) لغو سند. همه‌چیز در لاگ ثبت می‌شود."""
    acct = _acct(account_id)
    eid = int(eid)
    prev = delete_preview(conn, typ, eid, account_id=acct)
    if prev["blocked"]:
        raise ValueError(prev["blocked_reason"])

    voided_journal = None

    if typ == "party":
        if self_id and int(self_id) == eid:
            raise ValueError("نمی‌توانید خودتان را حذف کنید")
        conn.execute("UPDATE parties SET deleted_at=?, is_active=0 WHERE id=? AND account_id=?",
                     (_now(), eid, acct))
    elif typ == "cashbox":
        conn.execute("UPDATE cashboxes SET deleted_at=?, is_active=0 WHERE id=? AND account_id=?",
                     (_now(), eid, acct))
        conn.execute("UPDATE cashboxes SET deleted_at=?, is_active=0 WHERE parent_id=? AND deleted_at IS NULL",
                     (_now(), eid))
    elif typ == "currency":
        conn.execute("UPDATE currencies SET deleted_at=?, is_active=0 WHERE id=?", (_now(), eid))
    elif typ == "user":
        if self_id and int(self_id) == eid:
            raise ValueError("نمی‌توانید حساب کاربری خودتان را حذف کنید")
        row = conn.execute("SELECT * FROM users WHERE id=?", (eid,)).fetchone()
        if not row:
            raise ValueError("کاربر یافت نشد")
        actor = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        actor_role = actor["role"] if actor else None
        if row["role"] == "super_admin":
            n_sa = conn.execute(
                "SELECT COUNT(*) c FROM users WHERE role='super_admin' AND is_active=1 AND deleted_at IS NULL"
            ).fetchone()["c"]
            if n_sa <= 1:
                raise ValueError("این آخرین سوپرادمین فعال سیستم است و قابل حذف نیست.")
            if actor_role != "super_admin":
                raise ValueError("فقط سوپرادمین می‌تواند کاربر سوپرادمین را حذف کند.")
        if row["is_owner"]:
            n_owner = conn.execute(
                "SELECT COUNT(*) c FROM users WHERE account_id=? AND is_owner=1 AND is_active=1 AND deleted_at IS NULL",
                (row["account_id"],)).fetchone()["c"]
            if n_owner <= 1:
                raise ValueError("این آخرین مدیر/مالک فعال حساب است و قابل حذف نیست.")
        conn.execute("UPDATE users SET deleted_at=?, is_active=0 WHERE id=?", (_now(), eid))
    elif typ == "invoice":
        inv = conn.execute("SELECT * FROM invoices WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if inv and inv["journal_id"]:
            try:
                void_journal(conn, inv["journal_id"], "حذف فاکتور توسط کاربر", user_id=user_id,
                             account_id=acct)
                voided_journal = inv["journal_id"]
            except ValueError:
                pass
        conn.execute("UPDATE invoices SET deleted_at=? WHERE id=? AND account_id=?", (_now(), eid, acct))
    elif typ == "banknote":
        conn.execute("UPDATE banknotes SET deleted_at=? WHERE id=? AND account_id=?", (_now(), eid, acct))
    elif typ in ("expense", "income"):
        tbl = "expenses" if typ == "expense" else "incomes"
        row = conn.execute(f"SELECT * FROM {tbl} WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if row and row["journal_id"]:
            try:
                void_journal(conn, row["journal_id"], f"حذف {TYPE_FA[typ]} توسط کاربر",
                             user_id=user_id, account_id=acct)
                voided_journal = row["journal_id"]
            except ValueError:
                pass
        conn.execute(f"UPDATE {tbl} SET deleted_at=? WHERE id=? AND account_id=?", (_now(), eid, acct))
    elif typ == "loan":
        row = conn.execute("SELECT * FROM loans WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if row:
            if row["journal_id"]:
                try:
                    void_journal(conn, row["journal_id"], "حذف قرض توسط کاربر",
                                 user_id=user_id, account_id=acct)
                    voided_journal = row["journal_id"]
                except ValueError:
                    pass
            conn.execute("UPDATE loans SET deleted_at=?, status='voided' WHERE id=? AND account_id=?",
                         (_now(), eid, acct))
    elif typ == "payment":
        row = conn.execute("SELECT * FROM payments WHERE id=? AND account_id=?", (eid, acct)).fetchone()
        if row and row["journal_id"]:
            try:
                void_journal(conn, row["journal_id"], "حذف پرداخت توسط کاربر",
                             user_id=user_id, account_id=acct)
                voided_journal = row["journal_id"]
            except ValueError:
                pass
        conn.execute("UPDATE payments SET deleted_at=? WHERE id=? AND account_id=?", (_now(), eid, acct))
    elif typ == "category":
        conn.execute("UPDATE expense_categories SET deleted_at=? WHERE id=?", (_now(), eid))
    elif typ == "account":
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (eid,)).fetchone()
        if not row:
            raise ValueError("حساب (مشترک) یافت نشد")
        conn.execute("UPDATE accounts SET deleted_at=? WHERE id=?", (_now(), eid))

    _audit(conn, user_id, "delete", typ, eid, json.dumps(
        {"name": prev["name"], "label": prev["label"], "voided_journal": voided_journal},
        ensure_ascii=False), account_id=acct)
    conn.commit()
    return {"ok": True, "type": typ, "id": eid, "name": prev["name"],
            "voided_journal": voided_journal}


def restore_entity(conn, typ, eid, user_id, account_id=None):
    """بازیابی یک رکورد حذف‌شده (پنهان‌زدایی). اثر مالیِ لغو‌شده برنمی‌گردد."""
    acct = _acct(account_id)
    eid = int(eid)
    if typ == "party":
        conn.execute("UPDATE parties SET deleted_at=NULL, is_active=1 WHERE id=? AND account_id=?",
                     (eid, acct))
    elif typ == "cashbox":
        conn.execute("UPDATE cashboxes SET deleted_at=NULL, is_active=1 WHERE id=? AND account_id=?",
                     (eid, acct))
        conn.execute("UPDATE cashboxes SET deleted_at=NULL, is_active=1 WHERE parent_id=? AND deleted_at IS NOT NULL",
                     (eid,))
    elif typ == "currency":
        conn.execute("UPDATE currencies SET deleted_at=NULL, is_active=1 WHERE id=?", (eid,))
    elif typ == "user":
        conn.execute("UPDATE users SET deleted_at=NULL, is_active=1 WHERE id=?", (eid,))
    elif typ == "banknote":
        conn.execute("UPDATE banknotes SET deleted_at=NULL WHERE id=? AND account_id=?", (eid, acct))
    elif typ == "invoice":
        conn.execute("UPDATE invoices SET deleted_at=NULL WHERE id=? AND account_id=?", (eid, acct))
    elif typ in ("expense", "income"):
        tbl = "expenses" if typ == "expense" else "incomes"
        conn.execute(f"UPDATE {tbl} SET deleted_at=NULL WHERE id=? AND account_id=?", (eid, acct))
    elif typ == "loan":
        conn.execute("UPDATE loans SET deleted_at=NULL WHERE id=? AND account_id=?", (eid, acct))
    elif typ == "payment":
        conn.execute("UPDATE payments SET deleted_at=NULL WHERE id=? AND account_id=?", (eid, acct))
    elif typ == "category":
        conn.execute("UPDATE expense_categories SET deleted_at=NULL WHERE id=?", (eid,))
    elif typ == "account":
        conn.execute("UPDATE accounts SET deleted_at=NULL WHERE id=?", (eid,))
    else:
        raise ValueError("نوع نامعتبر است")
    _audit(conn, user_id, "restore", typ, eid, None, account_id=acct)
    conn.commit()
    return {"ok": True, "type": typ, "id": eid}


def list_deleted(conn, account_id=None):
    """سطل بازیافت: همه‌ی رکوردهای حذف‌شده‌ی حساب (و برای سوپرادمین: کاربران/ارزها)."""
    acct = _acct(account_id)
    out = []
    for r in conn.execute(
            "SELECT id, full_name, deleted_at FROM parties WHERE account_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (acct,)).fetchall():
        out.append({"type": "party", "id": r["id"], "name": r["full_name"],
                    "label": TYPE_FA["party"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute(
            "SELECT id, name, deleted_at FROM cashboxes WHERE account_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (acct,)).fetchall():
        out.append({"type": "cashbox", "id": r["id"], "name": r["name"],
                    "label": TYPE_FA["cashbox"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute(
            "SELECT id, serial, deleted_at FROM banknotes WHERE account_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (acct,)).fetchall():
        out.append({"type": "banknote", "id": r["id"], "name": r["serial"],
                    "label": TYPE_FA["banknote"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute(
            "SELECT id, invoice_no, deleted_at FROM invoices WHERE account_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (acct,)).fetchall():
        out.append({"type": "invoice", "id": r["id"], "name": r["invoice_no"],
                    "label": TYPE_FA["invoice"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for tbl, typ in (("expenses", "expense"), ("incomes", "income"), ("loans", "loan"),
                     ("payments", "payment")):
        for r in conn.execute(
                f"SELECT id, deleted_at FROM {tbl} WHERE account_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
                (acct,)).fetchall():
            out.append({"type": typ, "id": r["id"], "name": f"{TYPE_FA[typ]} #{r['id']}",
                        "label": TYPE_FA[typ], "deleted_at": r["deleted_at"],
                        "reversible": True})
    # دسته‌ها و ارزها (سراسری)
    for r in conn.execute("SELECT id, name, deleted_at FROM expense_categories WHERE deleted_at IS NOT NULL").fetchall():
        out.append({"type": "category", "id": r["id"], "name": r["name"],
                    "label": TYPE_FA["category"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute("SELECT id, name, code, deleted_at FROM currencies WHERE deleted_at IS NOT NULL").fetchall():
        out.append({"type": "currency", "id": r["id"], "name": f"{r['name']} ({r['code']})",
                    "label": TYPE_FA["currency"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute("SELECT id, full_name, username, deleted_at FROM users WHERE deleted_at IS NOT NULL").fetchall():
        out.append({"type": "user", "id": r["id"], "name": r["full_name"] or r["username"],
                    "label": TYPE_FA["user"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    for r in conn.execute("SELECT id, name, deleted_at FROM accounts WHERE deleted_at IS NOT NULL").fetchall():
        out.append({"type": "account", "id": r["id"], "name": r["name"],
                    "label": TYPE_FA["account"], "deleted_at": r["deleted_at"],
                    "reversible": True})
    out.sort(key=lambda x: x["deleted_at"] or "", reverse=True)
    return {"items": out}


# ---------------------------------------------------------------------------
# سود محقق FIFO
# ---------------------------------------------------------------------------
def realized_profit_fifo(conn, currency_id, from_date=None, to_date=None, account_id=None):
    cur = _currency(conn, currency_id)
    ratio = cur["unit_ratio"]
    lots = []
    profit = Decimal(0)
    sold_total = 0

    sql = """
        SELECT t.id, j.jtype, t.direction, t.amount, t.rate, t.created_at
        FROM transactions t JOIN journal j ON j.id=t.journal_id
        WHERE t.account_id=? AND t.currency_id=? AND j.status='posted'
          AND t.account_type='cashbox'
    """
    args = [_acct(account_id), currency_id]
    if from_date:
        sql += " AND t.created_at >= ?"
        args.append(from_date + " 00:00:00")
    if to_date:
        sql += " AND t.created_at <= ?"
        args.append(to_date + " 23:59:59")
    sql += " ORDER BY t.created_at, t.id"
    rows = conn.execute(sql, args).fetchall()

    for r in rows:
        amt = Decimal(r["amount"])
        if r["jtype"] in ("buy",) and r["direction"] == "debit":
            lots.append({"amount": amt, "rate": Decimal(r["rate"])})
        elif r["jtype"] == "sell" and r["direction"] == "credit":
            remaining = amt
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(lot["amount"], remaining)
                profit += (Decimal(r["rate"]) - lot["rate"]) * take / Decimal(ratio)
                lot["amount"] -= take
                remaining -= take
                if lot["amount"] == 0:
                    lots.pop(0)
            sold_total += amt
    return int(profit.to_integral_value(rounding=ROUND_HALF_UP)), sold_total


# ---------------------------------------------------------------------------
# گزارش‌ها
# ---------------------------------------------------------------------------
def cashbox_report(conn, cashbox_id, currency_id, day=None, account_id=None):
    day = day or _today()
    start = day + " 00:00:00"
    end = day + " 23:59:59"
    opening = _cashbox_currency_balance(conn, cashbox_id, currency_id, start, account_id)

    def _sum(direction):
        row = conn.execute(
            """SELECT COALESCE(SUM(t.amount),0) s FROM transactions t JOIN journal j ON j.id=t.journal_id
               WHERE t.account_id=? AND t.cashbox_id=? AND t.currency_id=? AND t.direction=? AND j.status='posted'
                 AND t.created_at>=? AND t.created_at<=?""",
            (_acct(account_id), cashbox_id, currency_id, direction, start, end)).fetchone()
        return row["s"]

    inflow = _sum("debit")
    outflow = _sum("credit")
    closing = opening + inflow - outflow
    return {"currency": conn.execute(
        "SELECT code FROM currencies WHERE id=?", (currency_id,)).fetchone()["code"],
        "opening": opening, "inflow": inflow, "outflow": outflow, "closing": closing}


def daily_stats(conn, day=None, account_id=None):
    day = day or _today()
    start, end = day + " 00:00:00", day + " 23:59:59"
    acct = _acct(account_id)
    buy = conn.execute(
        """SELECT COALESCE(SUM(total_rial),0) s, COUNT(*) c FROM invoices
           WHERE account_id=? AND invoice_type='buy' AND status IN ('confirmed','settled')
             AND confirmed_at>=? AND confirmed_at<=?""", (acct, start, end)).fetchone()
    sell = conn.execute(
        """SELECT COALESCE(SUM(total_rial),0) s, COUNT(*) c FROM invoices
           WHERE account_id=? AND invoice_type='sell' AND status IN ('confirmed','settled')
             AND confirmed_at>=? AND confirmed_at<=?""", (acct, start, end)).fetchone()
    income = conn.execute(
        "SELECT COALESCE(SUM(rial_value),0) s FROM incomes WHERE account_id=? AND created_at>=? AND created_at<=?",
        (acct, start, end)).fetchone()["s"]
    expense = conn.execute(
        "SELECT COALESCE(SUM(rial_value),0) s FROM expenses WHERE account_id=? AND created_at>=? AND created_at<=?",
        (acct, start, end)).fetchone()["s"]
    return {"buy_total": buy["s"], "buy_count": buy["c"],
            "sell_total": sell["s"], "sell_count": sell["c"],
            "income": income, "expense": expense,
            "profit": (sell["s"] - buy["s"]) + income - expense}


def profit_loss(conn, from_date, to_date, account_id=None):
    start, end = from_date + " 00:00:00", to_date + " 23:59:59"
    acct = _acct(account_id)
    income = conn.execute(
        "SELECT COALESCE(SUM(rial_value),0) s FROM incomes WHERE account_id=? AND created_at>=? AND created_at<=?",
        (acct, start, end)).fetchone()["s"]
    expense = conn.execute(
        "SELECT COALESCE(SUM(rial_value),0) s FROM expenses WHERE account_id=? AND created_at>=? AND created_at<=?",
        (acct, start, end)).fetchone()["s"]
    sell = conn.execute(
        """SELECT COALESCE(SUM(total_rial),0) s FROM invoices
           WHERE account_id=? AND invoice_type='sell' AND status IN ('confirmed','settled')
             AND confirmed_at>=? AND confirmed_at<=?""", (acct, start, end)).fetchone()["s"]
    buy = conn.execute(
        """SELECT COALESCE(SUM(total_rial),0) s FROM invoices
           WHERE account_id=? AND invoice_type='buy' AND status IN ('confirmed','settled')
             AND confirmed_at>=? AND confirmed_at<=?""", (acct, start, end)).fetchone()["s"]
    return {"income": income, "expense": expense, "sell": sell, "buy": buy,
            "net": sell - buy + income - expense}


# ---------------------------------------------------------------------------
# امکانات نسخه ۰.۴ — ثبت گروهی اسکناس، هشدار کف موجودی، مدیریت ارز، محدودیت پلن
# ---------------------------------------------------------------------------
PLAN_LIMITS = {
    "free": {"users": 5, "cashboxes": 5, "invoices": 2000},
    "pro":  {"users": None, "cashboxes": None, "invoices": None},
}


def plan_limits(plan):
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def upsert_currency(conn, data):
    """ایجاد/ویرایش ارز (سراسری — فقط سوپرادمین). کد ارز باید یکتا باشد."""
    code = str(data.get("code", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    if not code or not name:
        raise ValueError("کد و نام ارز الزامی است")
    if not code.isalnum() or len(code) > 8:
        raise ValueError("کد ارز باید حروف/اعداد انگلیسی و حداکثر ۸ کاراکتر باشد")
    decimals = int(data.get("decimals", 2))
    unit_ratio = int(data.get("unit_ratio", 10 ** decimals))
    sort_order = int(data.get("sort_order", 0))
    is_active = int(data.get("is_active", 1))
    cid = data.get("id")
    dup = conn.execute("SELECT id FROM currencies WHERE code=? AND id!=?",
                       (code, int(cid) if cid else -1)).fetchone()
    if dup:
        raise ValueError("این کد ارز قبلاً ثبت شده است")
    if cid:
        conn.execute(
            "UPDATE currencies SET code=?,name=?,symbol=?,minor_name=?,decimals=?,unit_ratio=?,sort_order=?,is_active=?,serial_pattern=?,serial_zone=?,color_hex=? WHERE id=?",
            (code, name, data.get("symbol", code), data.get("minor_name") or "", decimals, unit_ratio,
             sort_order, is_active, data.get("serial_pattern") or None,
             data.get("serial_zone") or None, data.get("color_hex") or None, int(cid)))
        conn.commit()
        return int(cid)
    cur = conn.execute(
        "INSERT INTO currencies(code,name,symbol,minor_name,decimals,unit_ratio,sort_order,is_active,serial_pattern,serial_zone,color_hex) VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
        (code, name, data.get("symbol", code), data.get("minor_name") or "", decimals, unit_ratio,
         sort_order, is_active, data.get("serial_pattern") or None,
         data.get("serial_zone") or None, data.get("color_hex") or None))
    new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


def bulk_banknotes(conn, currency_id, denomination, serials, status="in_vault",
                   cashbox_id=None, note="", user_id=None, account_id=None,
                   party_id=None, movement_type=None):
    """ثبت گروهی اسکناس‌ها؛ سریال‌های تکراری گزارش می‌شوند و وارد نمی‌شوند.

    v0.7: در صورت داده‌شدن party_id، حرکت (purchase/sale/deposit) برای هر
    اسکناس ثبت می‌شود تا اسکناس به همان طرفِ حساب معامله پیوند بخورد.
    """
    acct = _acct(account_id)
    cur = conn.execute("SELECT * FROM currencies WHERE id=?", (currency_id,)).fetchone()
    if not cur:
        raise ValueError("ارز نامعتبر است")

    if party_id:
        party = conn.execute("SELECT id FROM parties WHERE id=? AND account_id=?",
                             (int(party_id), acct)).fetchone()
        if not party:
            raise ValueError("طرف حساب یافت نشد")
        party_id = int(party_id)

    seen, inserted, duplicates, skipped, ids = set(), 0, [], [], []
    for raw in serials:
        s = str(raw or "").strip().upper()
        if not s:
            continue
        if s in seen:
            skipped.append(s)
            continue
        seen.add(s)
        dup = conn.execute(
            "SELECT id,serial FROM banknotes WHERE account_id=? AND currency_id=? AND denomination=? AND serial=?",
            (acct, currency_id, int(denomination), s)).fetchone()
        if dup:
            duplicates.append(s)
            continue
        bcur = conn.execute(
            "INSERT INTO banknotes(account_id,currency_id,denomination,serial,status,cashbox_id,note)"
            " VALUES (?,?,?,?,?,?,?) RETURNING id",
            (acct, currency_id, int(denomination), s, status, cashbox_id, note))
        bid = bcur.fetchone()["id"]
        ids.append(bid)
        if party_id:
            mtype = movement_type or ("sale" if status == "sold" else "purchase")
            frm, to = (cashbox_id, None) if mtype == "sale" else (None, cashbox_id)
            conn.execute(
                """INSERT INTO banknote_movements(account_id,banknote_id,movement_type,
                                                  party_id,from_cashbox,to_cashbox,note)
                   VALUES (?,?,?,?,?,?,?)""",
                (acct, bid, mtype, party_id, frm, to, note))
        inserted += 1
    _audit(conn, user_id, "bulk_banknotes", "banknotes", None,
           json.dumps({"currency": currency_id, "inserted": inserted,
                       "duplicates": len(duplicates), "skipped": len(skipped),
                       "party": party_id}, ensure_ascii=False))
    conn.commit()
    return {"inserted": inserted, "duplicates": duplicates, "skipped": skipped, "ids": ids}


def register_banknotes(conn, currency_id, denomination, items, status="in_vault",
                       cashbox_id=None, party_id=None, journal_id=None, invoice_id=None,
                       source_image=None, note="", user_id=None, count_only=0,
                       account_id=None):
    """ثبت گروهی اسکناس‌ها همراه با دسته‌بندی (batch) و حرکت، با پشتیبانی از فروش.

    items: لیستی از dict ها با کلیدهای:
        serial  (اجباری، مگر در حالت شمارشی)
        images  (لیست dict: file_path, mime, type, confidence, meta)
        note

    count_only: اگر > ۰ باشد، به همین تعداد اسکناس «شمارشی» (بدون سریال) با
    شناسه‌ی موقت NB{batch}-NNN ساخته می‌شود تا معامله مسدود نشود.

    حالت‌ها:
        status='sold'  → اسکناس از صندوق به مشتری می‌رود (حرکت sale از cashbox)
        status='in_vault' و party_id → خرید از مشتری (حرکت purchase به cashbox)
        غیر اینها → واریز ساده (حرکت deposit به cashbox)

    در حالت فروش، اگر سریال قبلاً در خزانه ثبت شده باشد، به‌جای درج تکراری،
    وضعیتش «فروخته‌شده» می‌شود و حرکت فروش ثبت می‌گردد.

    اگر invoice_id داده شود، تطبیق با مبلغ فاکتور (reconciliation) هم در پاسخ
    برمی‌گردد: expected_minor، registered_minor، matched و diff_minor.
    """
    acct = _acct(account_id)
    cur = conn.execute("SELECT * FROM currencies WHERE id=?", (currency_id,)).fetchone()
    if not cur:
        raise ValueError("ارز نامعتبر است")

    bcur = conn.execute(
        """INSERT INTO banknote_batches(account_id,journal_id,invoice_id,party_id,
                                       currency_id,source_image,note,created_by)
           VALUES (?,?,?,?,?,?,?,?) RETURNING id""",
        (acct, journal_id, invoice_id, party_id, currency_id, source_image, note, user_id))
    batch_id = bcur.fetchone()["id"]

    sale_mode = status == "sold"
    inserted, duplicates, skipped, sold_existing, ids = 0, [], [], 0, []

    if count_only and count_only > 0:
        # حالت «فقط شمارش»: اسکناس‌های بدون سریال با شناسه‌ی موقت
        for i in range(int(count_only)):
            gen = f"NB{batch_id:05d}-{i + 1:03d}"
            bcur2 = conn.execute(
                """INSERT INTO banknotes(account_id,currency_id,denomination,serial,status,
                                         cashbox_id,batch_id,last_journal_id,note)
                   VALUES (?,?,?,?,?,?,?,?,?) RETURNING id""",
                (acct, currency_id, int(denomination), gen, status,
                 cashbox_id if status == "in_vault" else None,
                 batch_id, journal_id, "ثبت شمارشی (بدون سریال)"))
            bid = bcur2.fetchone()["id"]
            inserted += 1
            ids.append(bid)
            if sale_mode:
                mtype, frm, to = "sale", cashbox_id, None
            elif party_id and status == "in_vault":
                mtype, frm, to = "purchase", None, cashbox_id
            else:
                mtype, frm, to = "deposit", None, cashbox_id
            conn.execute(
                """INSERT INTO banknote_movements(account_id,banknote_id,journal_id,movement_type,
                                                  party_id,from_cashbox,to_cashbox,note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (acct, bid, journal_id, mtype, party_id, frm, to, "ثبت شمارشی"))
        items = []

    seen = set()
    for it in items:
        s = str((it.get("serial") or "")).strip().upper()
        if not s:
            skipped.append(s)
            continue
        if s in seen:
            skipped.append(s)
            continue
        seen.add(s)
        existing = conn.execute(
            "SELECT * FROM banknotes WHERE account_id=? AND currency_id=? AND denomination=? AND serial=?",
            (acct, currency_id, int(denomination), s)).fetchone()
        if sale_mode and existing and existing["status"] == "in_vault":
            # فروش اسکناسِ ثبت‌شده‌ی قبلی
            conn.execute(
                "UPDATE banknotes SET status='sold', last_journal_id=?, cashbox_id=NULL WHERE id=?",
                (journal_id, existing["id"]))
            bid = existing["id"]
            sold_existing += 1
        elif sale_mode and existing and existing["status"] == "sold":
            duplicates.append(s)
            continue
        elif existing:
            duplicates.append(s)
            continue
        else:
            bcur2 = conn.execute(
                """INSERT INTO banknotes(account_id,currency_id,denomination,serial,status,
                                         cashbox_id,batch_id,last_journal_id,note)
                   VALUES (?,?,?,?,?,?,?,?,?) RETURNING id""",
                (acct, currency_id, int(denomination), s, status,
                 cashbox_id if status == "in_vault" else None,
                 batch_id, journal_id, it.get("note") or note))
            bid = bcur2.fetchone()["id"]
            inserted += 1
        ids.append(bid)

        # حرکت
        if sale_mode:
            mtype, frm, to = "sale", cashbox_id, None
        elif party_id and status == "in_vault":
            mtype, frm, to = "purchase", None, cashbox_id
        else:
            mtype, frm, to = "deposit", None, cashbox_id
        conn.execute(
            """INSERT INTO banknote_movements(account_id,banknote_id,journal_id,movement_type,
                                              party_id,from_cashbox,to_cashbox,note)
               VALUES (?,?,?,?,?,?,?,?)""",
            (acct, bid, journal_id, mtype, party_id, frm, to, it.get("note") or note))

        # تصاویر
        for img in (it.get("images") or []):
            if not img.get("file_path"):
                continue
            conn.execute(
                """INSERT INTO banknote_images(account_id,banknote_id,file_path,mime,type,confidence,meta,note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (acct, bid, img["file_path"], img.get("mime", "image/jpeg"),
                 img.get("type", "photo"), img.get("confidence"),
                 img.get("meta"), img.get("note", "")))

    # در حالت شمارشی، اسکناس‌های موقت در «inserted» شمرده می‌شوند
    registered = inserted + sold_existing
    recon = None
    if invoice_id:
        inv = conn.execute("SELECT * FROM invoices WHERE id=? AND account_id=?",
                           (invoice_id, acct)).fetchone()
        if inv:
            expected_minor = int(inv["amount"])
            # مبلغ اسکناس: denomination به واحد کسری (minor) ذخیره می‌شود؛ ضرب در تعداد
            registered_minor = int(denomination) * registered
            recon = {"expected_minor": expected_minor, "registered_minor": registered_minor,
                     "matched": expected_minor == registered_minor,
                     "diff_minor": expected_minor - registered_minor}

    _audit(conn, user_id, "register_banknotes", "banknotes", None,
           json.dumps({"batch": batch_id, "currency": currency_id,
                       "inserted": inserted, "sold_existing": sold_existing,
                       "count_only": count_only,
                       "duplicates": len(duplicates)}, ensure_ascii=False))
    conn.commit()
    return {"batch_id": batch_id, "inserted": inserted, "sold_existing": sold_existing,
            "count_only": count_only, "duplicates": duplicates, "skipped": skipped,
            "banknote_ids": ids, "reconciliation": recon}


def list_available_banknotes(conn, currency_id=None, denomination=None, q=None,
                             account_id=None, limit=200):
    """اسکناس‌های «در دسترس» برای انتخاب/الصاق به فاکتور.

    در دسترس یعنی: حذف‌نشده و در خزانه (status='in_vault'). اسکناس‌هایی که
    فروخته/برداشت شده‌اند (یا به فاکتور فروشِ باز الصاق شده‌اند) اینجا نمی‌آیند.
    """
    acct = _acct(account_id)
    where = "b.account_id=? AND b.deleted_at IS NULL AND b.status='in_vault'"
    args = [acct]
    if currency_id:
        where += " AND b.currency_id=?"
        args.append(int(currency_id))
    if denomination:
        where += " AND b.denomination=?"
        args.append(int(denomination))
    if q:
        like = f"%{q}%"
        where += " AND (b.serial LIKE ? OR c.code LIKE ? OR cb.name LIKE ?)"
        args += [like, like, like]
    rows = conn.execute(
        f"""SELECT b.id, b.currency_id, b.denomination, b.serial, b.status,
                   b.cashbox_id, b.note, b.created_at,
                   c.code, c.decimals, c.unit_ratio, cb.name cashbox_name,
                   (SELECT COUNT(*) FROM banknote_images i WHERE i.banknote_id=b.id) img_count
            FROM banknotes b JOIN currencies c ON c.id=b.currency_id
            LEFT JOIN cashboxes cb ON cb.id=b.cashbox_id
            WHERE {where} ORDER BY b.id DESC LIMIT ?""",
        args + [int(limit)]).fetchall()
    return [dict(r) for r in rows]


def attach_banknotes(conn, ids, invoice_id=None, journal_id=None, party_id=None,
                     movement_type=None, cashbox_id=None, user_id=None, account_id=None):
    """الصاق اسکناس‌های از قبل ثبت‌شده به یک فاکتور/سند.

    - فروش (movement_type='sale'): اسکناس باید در خزانه باشد → وضعیت sold + حرکت sale.
    - خرید (movement_type='purchase'): اسکناس وارد خزانه می‌ماند + حرکت purchase.
    - تکراری (قبلاً به همان سند الصاق شده) نادیده گرفته می‌شود (idempotent).
    """
    acct = _acct(account_id)
    ids = [int(x) for x in (ids or []) if str(x).strip()]
    if not ids:
        raise ValueError("هیچ اسکناسی انتخاب نشده است")
    mtype = movement_type or "sale"
    if mtype not in ("sale", "purchase", "deposit", "initial"):
        raise ValueError("نوع حرکت نامعتبر است")
    attached, skipped, rejected, warnings = [], [], [], []
    for bid in ids:
        b = conn.execute(
            "SELECT * FROM banknotes WHERE id=? AND account_id=? AND deleted_at IS NULL",
            (bid, acct)).fetchone()
        if not b:
            rejected.append({"id": bid, "reason": "اسکناس یافت نشد"})
            continue
        if journal_id:
            dup = conn.execute(
                "SELECT id FROM banknote_movements WHERE banknote_id=? AND journal_id=?",
                (bid, journal_id)).fetchone()
            if dup:
                skipped.append({"id": bid, "reason": "قبلاً به همین فاکتور الصاق شده است"})
                continue
        if mtype == "sale":
            if b["status"] != "in_vault":
                rejected.append({"id": bid, "reason": "اسکناس در دسترس نیست (قبلاً فروخته/برداشت شده)"})
                continue
            from_cb = b["cashbox_id"]
            if cashbox_id and from_cb and int(from_cb) != int(cashbox_id):
                warnings.append({"id": bid, "reason": "صندوق اسکناس با صندوق فاکتور متفاوت است"})
            conn.execute(
                "UPDATE banknotes SET status='sold', last_journal_id=?, cashbox_id=NULL WHERE id=?",
                (journal_id, bid))
            conn.execute(
                """INSERT INTO banknote_movements(account_id,banknote_id,journal_id,movement_type,
                                                  party_id,from_cashbox,to_cashbox,note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (acct, bid, journal_id, mtype, party_id, from_cb, None, "الصاق به فاکتور"))
        elif mtype == "purchase":
            if b["status"] != "in_vault":
                rejected.append({"id": bid, "reason": "اسکناس در دسترس نیست"})
                continue
            conn.execute(
                "UPDATE banknotes SET status='in_vault', last_journal_id=?, cashbox_id=? WHERE id=?",
                (journal_id, cashbox_id, bid))
            conn.execute(
                """INSERT INTO banknote_movements(account_id,banknote_id,journal_id,movement_type,
                                                  party_id,from_cashbox,to_cashbox,note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (acct, bid, journal_id, mtype, party_id, None, cashbox_id, "الصاق به فاکتور"))
        else:
            conn.execute(
                "UPDATE banknotes SET last_journal_id=?, cashbox_id=? WHERE id=?",
                (journal_id, cashbox_id, bid))
            conn.execute(
                """INSERT INTO banknote_movements(account_id,banknote_id,journal_id,movement_type,
                                                  party_id,from_cashbox,to_cashbox,note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (acct, bid, journal_id, mtype, party_id, None, cashbox_id, "الصاق"))
        attached.append(bid)
    _audit(conn, user_id, "attach_banknotes", "banknotes", None,
           json.dumps({"ids": ids, "attached": attached, "rejected": rejected,
                       "invoice": invoice_id, "journal": journal_id,
                       "movement_type": mtype}, ensure_ascii=False))
    conn.commit()
    return {"attached": attached, "skipped": skipped, "rejected": rejected,
            "warnings": warnings}


def detach_banknote(conn, banknote_id, user_id=None, account_id=None):
    """جداسازی اسکناس از فاکتوری که به آن الصاق شده (بازگشت به حالت در دسترس)."""
    acct = _acct(account_id)
    bid = int(banknote_id)
    b = conn.execute(
        "SELECT * FROM banknotes WHERE id=? AND account_id=? AND deleted_at IS NULL",
        (bid, acct)).fetchone()
    if not b:
        raise ValueError("اسکناس یافت نشد")
    mv = conn.execute(
        """SELECT * FROM banknote_movements WHERE banknote_id=? AND journal_id IS NOT NULL
           ORDER BY id DESC LIMIT 1""", (bid,)).fetchone()
    if not mv:
        raise ValueError("این اسکناس به سندی پیوند ندارد")
    if mv["movement_type"] == "sale":
        conn.execute(
            "UPDATE banknotes SET status='in_vault', last_journal_id=NULL, cashbox_id=? WHERE id=?",
            (mv["from_cashbox"], bid))
    else:
        conn.execute(
            "UPDATE banknotes SET status='in_vault', last_journal_id=NULL, cashbox_id=? WHERE id=?",
            (mv["to_cashbox"], bid))
    conn.execute("DELETE FROM banknote_movements WHERE id=?", (mv["id"],))
    _audit(conn, user_id, "detach_banknote", "banknotes", bid,
           json.dumps({"movement": mv["id"], "journal": mv["journal_id"],
                       "movement_type": mv["movement_type"]}, ensure_ascii=False))
    conn.commit()
    return {"ok": True, "id": bid}


def upsert_cashbox(conn, data, account_id=None):
    """ایجاد/ویرایش صندوق (نقدی یا بانکی). نام در هر حساب یکتا است.

    v0.7:
        parent_id   → صندوق والد (برای زیرشاخه‌های ارزیِ یک صندوق بانکی)
        currency_id → محدودکردن صندوق به یک ارز خاص (خالی = چندارزی)
    """
    acct = _acct(account_id)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("نام صندوق الزامی است")
    kind = data.get("kind", "physical")
    if kind not in ("physical", "bank"):
        kind = "physical"
    cid = data.get("id")

    parent_id = data.get("parent_id") or None
    currency_id = data.get("currency_id") or None

    if parent_id:
        parent_id = int(parent_id)
        parent = conn.execute("SELECT * FROM cashboxes WHERE id=? AND account_id=?",
                              (parent_id, acct)).fetchone()
        if not parent:
            raise ValueError("صندوق والد یافت نشد")
        if parent["parent_id"]:
            raise ValueError("زیرشاخه فقط می‌تواند زیر یک صندوق اصلی (ریشه) تعریف شود")
        if cid and int(cid) == parent_id:
            raise ValueError("یک صندوق نمی‌تواند والد خودش باشد")

    if currency_id:
        cur = conn.execute("SELECT id FROM currencies WHERE id=?", (int(currency_id),)).fetchone()
        if not cur:
            raise ValueError("ارز نامعتبر است")

    dup = conn.execute("SELECT id FROM cashboxes WHERE account_id=? AND name=? AND id!=?",
                       (acct, name, int(cid) if cid else -1)).fetchone()
    if dup:
        raise ValueError("این نام صندوق قبلاً ثبت شده است")
    if cid:
        conn.execute(
            """UPDATE cashboxes SET name=?,kind=?,description=?,parent_id=?,currency_id=?,is_active=?
               WHERE id=? AND account_id=?""",
            (name, kind, data.get("description", ""), parent_id, currency_id,
             int(data.get("is_active", 1)), int(cid), acct))
        conn.commit()
        return int(cid)
    # سقف تعداد صندوق بر اساس پلن
    prow = conn.execute("SELECT plan FROM accounts WHERE id=?", (acct,)).fetchone()
    plan = prow["plan"] if prow else "free"
    lim = plan_limits(plan)["cashboxes"]
    if lim:
        cnt = conn.execute("SELECT COUNT(*) c FROM cashboxes WHERE account_id=? AND is_active=1",
                           (acct,)).fetchone()["c"]
        if cnt >= lim:
            raise ValueError(f"سقف صندوق‌های پلن «{plan}» (حداکثر {lim} صندوق) پر شده است")
    cur = conn.execute(
        """INSERT INTO cashboxes(account_id,name,kind,description,parent_id,currency_id,is_active)
           VALUES (?,?,?,?,?,?,?) RETURNING id""",
        (acct, name, kind, data.get("description", ""), parent_id, currency_id,
         int(data.get("is_active", 1))))
    new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


def loan_reminders(conn, days_ahead=7, account_id=None):
    """یادآور سررسید قرض‌ها: قرض‌های باز/جزئی که سررسیدشان گذشته یا در
    days_ahead روز آینده است. خروجی شامل مبلغ باقی‌مانده و روزهای مانده است."""
    acct = _acct(account_id)
    today = date.today()
    out = []
    rows = conn.execute(
        """SELECT l.*, p.full_name, c.code, c.decimals, c.unit_ratio, c.symbol
           FROM loans l JOIN parties p ON p.id=l.party_id
           JOIN currencies c ON c.id=l.currency_id
           WHERE l.account_id=? AND l.status IN ('open','partial')
           ORDER BY l.due_date IS NULL, l.due_date, l.id""", (acct,)).fetchall()
    for l in rows:
        repaid = conn.execute(
            """SELECT COALESCE(SUM(t.amount),0) s FROM transactions t
               JOIN journal j ON j.id=t.journal_id
               WHERE j.jtype='loan_repay' AND j.status='posted'
                 AND t.account_id=? AND t.account_type='party'
                 AND t.party_id=? AND t.currency_id=?""",
            (acct, l["party_id"], l["currency_id"])).fetchone()["s"]
        repaid = int(repaid or 0)
        remaining = max(0, int(l["amount"]) - repaid)
        if remaining <= 0:
            continue
        days_left = None
        overdue = False
        due = l["due_date"]
        if due:
            try:
                d = date.fromisoformat(str(due)[:10])
                days_left = (d - today).days
                overdue = days_left < 0
            except ValueError:
                due = None
        if due and (overdue or days_left <= days_ahead):
            out.append({
                "loan_id": l["id"], "party_id": l["party_id"], "party": l["full_name"],
                "direction": l["direction"], "code": l["code"], "symbol": l["symbol"],
                "amount": int(l["amount"]), "repaid": repaid, "remaining": remaining,
                "due_date": due, "days_left": days_left, "overdue": overdue,
                "decimals": l["decimals"], "unit_ratio": l["unit_ratio"]})
    return out


def party_credit_check(conn, party_id, extra_rial=0, account_id=None):
    """سقف اعتبار مشتری: بدهی جاریِ نسیه (فروش‌های تسویه‌نشده) بر حسب ریال.

    سقف اعتبار در جدول parties بر حسب ریال ذخیره می‌شود."""
    acct = _acct(account_id)
    p = conn.execute("SELECT * FROM parties WHERE id=? AND account_id=?",
                     (party_id, acct)).fetchone()
    if not p:
        raise ValueError("طرف حساب یافت نشد")
    used = conn.execute(
        """SELECT COALESCE(SUM(total_rial - paid_rial),0) s FROM invoices
           WHERE account_id=? AND party_id=? AND invoice_type='sell'
             AND status IN ('confirmed','unsettled','settled')""",
        (acct, party_id)).fetchone()["s"]
    used = int(used or 0)
    limit = p["credit_limit"]
    out = {"party_id": party_id, "credit_limit": limit, "used_rial": used}
    if limit is None:
        out.update({"ok": True, "available_rial": None, "would_exceed": False})
        return out
    limit = int(limit)
    available = max(0, limit - used)
    out.update({"ok": used + extra_rial <= limit, "available_rial": available,
                "would_exceed": used + extra_rial > limit,
                "used_after": used + extra_rial})
    return out


def cashflow_forecast(conn, days=30, account_id=None):
    """پیش‌بینی ساده‌ی نقدینگی: جمع بدهی/طلب‌های سررسیدشده تا N روز آینده.

    خروجی بر حسب ریال:
        incoming: وصولی‌های مورد انتظار (طلب از مشتریانِ نسیه + قرض‌های بازپرداخت‌نشده‌ی دریافتی)
        outgoing: پرداخت‌های مورد انتظار (بدهی به فروشندگان + قرض‌های داده‌شده‌ی سررسیدشده)
        net: incoming - outgoing
    """
    acct = _acct(account_id)
    today = date.today()
    horizon = today + timedelta(days=days)
    horizon_s = horizon.strftime("%Y-%m-%d")
    today_s = today.strftime("%Y-%m-%d")

    # بدهی‌های نسیه‌ی مشتریان (فروش‌های تسویه‌نشده) → وصولی آینده
    incoming = int((conn.execute(
        """SELECT COALESCE(SUM(total_rial - paid_rial),0) s FROM invoices
           WHERE account_id=? AND invoice_type='sell'
             AND status IN ('confirmed','unsettled')""",
        (acct,)).fetchone()["s"] or 0))
    # بدهی ما به فروشندگان (خریدهای نسیه) → پرداخت آینده
    outgoing = int((conn.execute(
        """SELECT COALESCE(SUM(total_rial - paid_rial),0) s FROM invoices
           WHERE account_id=? AND invoice_type='buy'
             AND status IN ('confirmed','unsettled')""",
        (acct,)).fetchone()["s"] or 0))
    # قرض‌های داده‌شده که سررسیدشان تا افق است → وصولی
    for l in conn.execute(
            """SELECT amount, (SELECT COALESCE(SUM(t.amount),0) FROM transactions t
                               JOIN journal j ON j.id=t.journal_id
                               WHERE j.jtype='loan_repay' AND j.status='posted'
                                 AND t.account_type='party' AND t.party_id=loans.party_id
                                 AND t.currency_id=loans.currency_id) repaid,
                      rate, (SELECT unit_ratio FROM currencies c WHERE c.id=loans.currency_id) ur
               FROM loans WHERE account_id=? AND direction='give' AND status IN ('open','partial')
                 AND due_date IS NOT NULL AND due_date<=?""",
            (acct, horizon_s)).fetchall():
        remaining = int(l["amount"]) - int(l["repaid"] or 0)
        incoming += int(remaining * (l["rate"] or 0) / (l["ur"] or 1))
    # قرض‌های دریافتی که سررسیدشان تا افق است → پرداخت
    for l in conn.execute(
            """SELECT amount, (SELECT COALESCE(SUM(t.amount),0) FROM transactions t
                               JOIN journal j ON j.id=t.journal_id
                               WHERE j.jtype='loan_repay' AND j.status='posted'
                                 AND t.account_type='party' AND t.party_id=loans.party_id
                                 AND t.currency_id=loans.currency_id) repaid,
                      rate, (SELECT unit_ratio FROM currencies c WHERE c.id=loans.currency_id) ur
               FROM loans WHERE account_id=? AND direction='receive' AND status IN ('open','partial')
                 AND due_date IS NOT NULL AND due_date<=?""",
            (acct, horizon_s)).fetchall():
        remaining = int(l["amount"]) - int(l["repaid"] or 0)
        outgoing += int(remaining * (l["rate"] or 0) / (l["ur"] or 1))

    # موجودی ریالی فعلی (جمع صندوق‌ها)
    irr = conn.execute("SELECT * FROM currencies WHERE code='IRR'").fetchone()
    rial_balance = 0
    if irr:
        for cb in conn.execute("SELECT id FROM cashboxes WHERE account_id=?", (acct,)).fetchall():
            rial_balance += int(_cashbox_currency_balance(conn, cb["id"], irr["id"],
                                                          account_id=acct) or 0)

    return {"days": days, "today": today_s, "horizon": horizon_s,
            "incoming_rial": incoming, "outgoing_rial": outgoing,
            "net_rial": incoming - outgoing, "rial_balance": rial_balance,
            "projected_rial": rial_balance + incoming - outgoing}


def plan_catalog():
    """فهرست پلن‌های SaaS (قیمت به ریال — نمونه)"""
    return [
        {"code": "free", "name": "رایگان", "price_rial": 0, "period_months": 0,
         "limits": PLAN_LIMITS["free"],
         "features": "حداکثر ۵ کاربر، ۵ صندوق، ۲۰۰۰ فاکتور — بدون هزینه"},
        {"code": "pro", "name": "حرفه‌ای", "price_rial": 3_500_000, "period_months": 1,
         "limits": PLAN_LIMITS["pro"],
         "features": "کاربر و صندوق و فاکتور نامحدود + پشتیبانی اولویت‌دار + بکاپ رمزنگاری‌شده"},
        {"code": "enterprise", "name": "سازمانی", "price_rial": 12_000_000, "period_months": 1,
         "limits": {"users": None, "cashboxes": None, "invoices": None},
         "features": "چند شعبه + API اختصاصی + سرور مستقل + پشتیبانی ۲۴/۷"},
    ]


def low_stock_alerts(conn, account_id=None):
    """هشدار کف موجودی: برای هر ارز، اگر مجموع موجودی صندوق‌ها از حد تعیین‌شده کمتر باشد."""
    acct = _acct(account_id)
    totals = {}
    for r in conn.execute(
            """SELECT c.id, c.code, c.name, c.decimals, c.unit_ratio,
                      COALESCE(SUM(CASE WHEN j.id IS NULL THEN 0
                                        WHEN t.direction='debit' THEN t.amount
                                        ELSE -t.amount END),0) bal
               FROM currencies c
               LEFT JOIN transactions t ON t.currency_id=c.id AND t.account_id=?
               LEFT JOIN journal j ON j.id=t.journal_id AND j.status='posted'
               WHERE c.is_active=1 AND c.code!='IRR'
               GROUP BY c.id, c.code, c.name, c.decimals, c.unit_ratio""", (acct,)).fetchall():
        totals[r["code"]] = r
    alerts = []
    for code, r in totals.items():
        key = f"min_stock_{code}"
        row = conn.execute("SELECT value FROM settings WHERE account_id=? AND key=?",
                           (acct, key)).fetchone()
        if not row or not str(row["value"] or "").strip():
            continue
        try:
            minimum = int(row["value"])
        except ValueError:
            continue
        if minimum <= 0:
            continue
        if int(r["bal"]) < minimum:
            alerts.append({"code": code, "name": r["name"], "balance": int(r["bal"]),
                           "minimum": minimum, "decimals": r["decimals"],
                           "unit_ratio": r["unit_ratio"]})
    alerts.sort(key=lambda a: (a["balance"] - a["minimum"]))
    return alerts
