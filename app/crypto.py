# -*- coding: utf-8 -*-
"""
رمزنگاری سبک بدون وابستگی خارجی — برای بکاپ‌های خودکار رمزنگاری‌شده.

ساختار: PBKDF2-HMAC-SHA256 برای استخراج کلید از عبارت عبور + جریان XOR با
keystream حاصل از HMAC (شبیه رمز جریانی) + امضای HMAC برای یکپارچگی داده.

قالب خروجی: magic(8) | salt(16) | nonce(16) | ciphertext | hmac(32)
"""

import hashlib
import hmac
import os

MAGIC = b"SRFENC01"
SALT_LEN = 16
NONCE_LEN = 16
HMAC_LEN = 32


def _derive(password: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password, salt, 200_000, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out += block
        counter += 1
    return bytes(out[:length])


def encrypt(data: bytes, password: str) -> bytes:
    if isinstance(password, str):
        password = password.encode("utf-8")
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive(password, salt)
    stream = _keystream(key, nonce, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, stream))
    body = salt + nonce + ciphertext
    sig = hmac.new(key, body, hashlib.sha256).digest()
    return MAGIC + body + sig


def decrypt(data: bytes, password: str) -> bytes:
    if isinstance(password, str):
        password = password.encode("utf-8")
    if not data.startswith(MAGIC):
        raise ValueError("این فایل رمزنگاری‌شده نیست یا قالب آن ناشناخته است")
    body = data[len(MAGIC):]
    if len(body) < SALT_LEN + NONCE_LEN + HMAC_LEN:
        raise ValueError("داده‌ی رمزنگاری‌شده ناقص است")
    salt = body[:SALT_LEN]
    nonce = body[SALT_LEN:SALT_LEN + NONCE_LEN]
    ciphertext = body[SALT_LEN + NONCE_LEN:-HMAC_LEN]
    sig = body[-HMAC_LEN:]
    key = _derive(password, salt)
    expect = hmac.new(key, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expect):
        raise ValueError("عبارت عبور اشتباه است یا داده دستکاری شده است")
    stream = _keystream(key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))
