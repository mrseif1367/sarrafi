# -*- coding: utf-8 -*-
"""
احراز هویت: هش رمز عبور (PBKDF2-HMAC-SHA256) + مدیریت نشست (توکن در دیتابیس)
"""

import hashlib
import secrets
import datetime

ITERATIONS = 120_000
SESSION_HOURS = 12


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2$sha256${ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] == "pbkdf2" and len(parts) == 5:
            _, _algo, iters, salt, hx = parts
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     bytes.fromhex(salt), int(iters))
            return secrets.compare_digest(dk.hex(), hx)
    except Exception:
        return False
    # سازگاری با هش‌های قدیمی (sha256 ساده)
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return secrets.compare_digest(legacy, stored)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def expires_at() -> str:
    return (datetime.datetime.now() + datetime.timedelta(hours=SESSION_HOURS)) \
        .strftime("%Y-%m-%d %H:%M:%S")


def is_expired(exp):
    if not exp:
        return True
    try:
        d = datetime.datetime.strptime(str(exp)[:19], "%Y-%m-%d %H:%M:%S")
        return d < datetime.datetime.now()
    except Exception:
        return True


# ---------------------------------------------------------------------------
# قفل ورود (ضد brute-force): بعد از چند تلاش ناموفق، نام کاربری موقتاً قفل می‌شود
# ---------------------------------------------------------------------------
MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def lockout_status(conn, username):
    """بررسی وضعیت قفل؛ اگر قفل فعال باشد (locked_until, seconds) برمی‌گرداند وگرنه None"""
    row = conn.execute(
        "SELECT attempts, locked_until FROM login_attempts WHERE username=?", (username,)).fetchone()
    if not row or not row["locked_until"]:
        return None
    locked = datetime.datetime.strptime(str(row["locked_until"])[:19], "%Y-%m-%d %H:%M:%S")
    remain = (locked - datetime.datetime.now()).total_seconds()
    if remain <= 0:
        # قفل منقضی شده — پاک‌سازی
        conn.execute("DELETE FROM login_attempts WHERE username=?", (username,))
        conn.commit()
        return None
    return int(remain) + 1


def register_failed_attempt(conn, username):
    """ثبت تلاش ناموفق؛ بعد از MAX_ATTEMPTS قفل می‌شود"""
    row = conn.execute(
        "SELECT attempts FROM login_attempts WHERE username=?", (username,)).fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    if attempts >= MAX_ATTEMPTS:
        until = (datetime.datetime.now() + datetime.timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO login_attempts(username, attempts, locked_until, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(username) DO UPDATE SET attempts=excluded.attempts,
                 locked_until=excluded.locked_until, updated_at=excluded.updated_at""",
            (username, attempts, until, _now()))
        conn.commit()
        return True, LOCK_MINUTES * 60
    conn.execute(
        """INSERT INTO login_attempts(username, attempts, locked_until, updated_at) VALUES (?,?,NULL,?)
           ON CONFLICT(username) DO UPDATE SET attempts=excluded.attempts,
             locked_until=NULL, updated_at=excluded.updated_at""",
        (username, attempts, _now()))
    conn.commit()
    return False, MAX_ATTEMPTS - attempts


def clear_attempts(conn, username):
    """پاک‌سازی تلاش‌ها بعد از ورود موفق"""
    conn.execute("DELETE FROM login_attempts WHERE username=?", (username,))
    conn.commit()


# ---------------- فراموشی / بازنشانی رمز عبور ----------------

RESET_TTL_MINUTES = 30


def create_reset_code(conn, username):
    """ساخت کد یک‌بارمصرف بازنشانی؛ کد قبلی‌های منقضی می‌شوند"""
    code = "%06d" % secrets.randbelow(1000000)
    expires = (datetime.datetime.now() + datetime.timedelta(minutes=RESET_TTL_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE password_resets SET used=1 WHERE username=? AND used=0", (username,))
    conn.execute(
        "INSERT INTO password_resets(username, code, expires_at) VALUES (?,?,?)",
        (username, code, expires))
    conn.commit()
    return code, RESET_TTL_MINUTES


def consume_reset_code(conn, username, code):
    """بررسی و مصرف کد بازنشانی؛ True یعنی معتبر بود"""
    row = conn.execute(
        "SELECT * FROM password_resets WHERE username=? AND code=? AND used=0 ORDER BY id DESC LIMIT 1",
        (username, code)).fetchone()
    if not row:
        return False
    exp = datetime.datetime.strptime(str(row["expires_at"])[:19], "%Y-%m-%d %H:%M:%S")
    if exp < datetime.datetime.now():
        return False
    conn.execute("UPDATE password_resets SET used=1 WHERE id=?", (row["id"],))
    conn.commit()
    return True


def set_password(conn, user_id, new_password):
    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                 (hash_password(new_password), user_id))
    conn.commit()
