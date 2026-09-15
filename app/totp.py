# -*- coding: utf-8 -*-
"""احراز هویت دومرحله‌ای (TOTP — RFC 6238) فقط با کتابخانه استاندارد.

بدون وابستگی خارجی: HMAC-SHA1 + Base32 + زمان یونیکس.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

WINDOW = 30       # ثانیه — گام زمانی استاندارد
TOLERANCE = 1     # پذیرش ±۱ گام (برای اختلاف ساعت)
DIGITS = 6


def _b32decode(s: str) -> bytes:
    s = s.upper().replace(" ", "").replace("=", "")
    padding = "=" * ((8 - len(s) % 8) % 8)
    try:
        return base64.b32decode(s + padding)
    except Exception:
        raise ValueError("کلید TOTP نامعتبر است")


def generate_secret(length: int = 20) -> str:
    """ساخت کلید مخفی Base32 (بدون padding)"""
    return base64.b32encode(secrets.token_bytes(length)).decode().rstrip("=")


def totp_at(secret: str, counter: int, digits: int = DIGITS) -> str:
    key = _b32decode(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def current_code(secret: str, digits: int = DIGITS) -> str:
    return totp_at(secret, int(time.time()) // WINDOW, digits)


def verify(secret: str, code: str, digits: int = DIGITS, tolerance: int = TOLERANCE) -> bool:
    code = str(code or "").strip()
    if not code.isdigit():
        return False
    counter = int(time.time()) // WINDOW
    for delta in range(-tolerance, tolerance + 1):
        if hmac.compare_digest(totp_at(secret, counter + delta, digits), code):
            return True
    return False


def otpauth_url(secret: str, label: str, issuer: str = "Sarrafi") -> str:
    """لینک otpauth:// برای برنامه‌های Authenticator"""
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(label)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={WINDOW}"
