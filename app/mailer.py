# -*- coding: utf-8 -*-
"""
ارسال ایمیل واقعی (کد بازیابی رمز، اعلان‌ها) با smtplib استاندارد.

تنظیمات از جدول settings (سطح حساب 0 = سراسری) خوانده می‌شود:
    smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, smtp_tls
اگر پیکربندی نشده باشد → None (برمی‌گردد تا رابط کاربری کد را نمایش دهد).
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr


def _cfg(conn):
    keys = ["smtp_host", "smtp_port", "smtp_user", "smtp_pass", "smtp_from", "smtp_tls"]
    vals = {}
    for k in keys:
        r = conn.execute("SELECT value FROM settings WHERE account_id=0 AND key=?",
                         (k,)).fetchone()
        vals[k] = (r["value"] if r else None)
    return vals


def configured(conn):
    c = _cfg(conn)
    return bool(c["smtp_host"] and c["smtp_from"])


def send(conn, to_email, subject, body_html):
    """ارسال ایمیل؛ در صورت موفقیت True و در غیر این صورت خطا را بالا می‌اندازد."""
    c = _cfg(conn)
    if not c["smtp_host"]:
        raise RuntimeError("SMTP پیکربندی نشده است")
    port = int(c["smtp_port"] or 587)
    use_tls = str(c["smtp_tls"] or "1") == "1"
    user = c["smtp_user"] or None
    pwd = c["smtp_pass"] or None
    sender = c["smtp_from"]

    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("صرافی", sender))
    msg["To"] = to_email

    if use_tls:
        ctx = ssl.create_default_context()
        srv = smtplib.SMTP(c["smtp_host"], port, timeout=20)
        srv.ehlo()
        srv.starttls(context=ctx)
        srv.ehlo()
    else:
        srv = smtplib.SMTP(c["smtp_host"], port, timeout=20)
    try:
        if user:
            srv.login(user, pwd)
        srv.sendmail(sender, [to_email], msg.as_string())
    finally:
        srv.quit()
    return True
