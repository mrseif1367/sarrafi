# -*- coding: utf-8 -*-
"""
ورود / ثبت‌نام با حساب گوگل (OAuth 2.0 — Authorization Code Flow)

نیازمند ساخت اعتبار در Google Cloud Console:
    https://console.cloud.google.com/apis/credentials
    - OAuth client ID از نوع Web application
    - Redirect URI:  https://YOUR_DOMAIN/api/auth/google/callback

تنظیم اعتبار:
    - متغیر محیطی:  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
    - یا از طریق تنظیمات (توسط سوپرادمین) در جدول settings(account_id=0):
        google_client_id / google_client_secret

اگر اعتبار تنظیم نشده باشد، `configured()` مقدار False برمی‌گرداند و
رابط کاربری پیام «پیکربندی نشده» را نمایش می‌دهد.
"""

import json
import os
import secrets
import urllib.parse
import urllib.request

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _cfg(conn):
    env_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    env_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if env_id and env_secret:
        return env_id, env_secret
    try:
        row = conn.execute(
            "SELECT key,value FROM settings WHERE account_id=0 AND key IN ('google_client_id','google_client_secret')"
        ).fetchall()
        d = {r["key"]: r["value"] for r in row}
        return d.get("google_client_id", ""), d.get("google_client_secret", "")
    except Exception:
        return "", ""


def configured(conn):
    cid, cs = _cfg(conn)
    return bool(cid and cs)


def auth_url(conn, redirect_uri):
    """ساخت لینک ورود گوگل"""
    cid, _ = _cfg(conn)
    if not cid:
        return None
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params), state


def exchange_code(conn, code, redirect_uri):
    """تبدیل code به اطلاعات کاربر"""
    cid, cs = _cfg(conn)
    if not (cid and cs):
        raise ValueError("Google OAuth پیکربندی نشده است")
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": cid,
        "client_secret": cs,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        tok = json.loads(r.read().decode())
    access = tok.get("access_token")
    if not access:
        raise ValueError("دریافت توکن گوگل ناموفق بود")
    req2 = urllib.request.Request(GOOGLE_USERINFO_URL,
                                  headers={"Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req2, timeout=15) as r:
        info = json.loads(r.read().decode())
    return {
        "sub": info.get("sub"),
        "email": info.get("email"),
        "name": info.get("name") or (info.get("email") or "").split("@")[0],
    }
