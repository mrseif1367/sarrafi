# -*- coding: utf-8 -*-
"""تنظیمات مشترک تست‌ها"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_db_engine():
    """پس از هر تست، اجبار «نمونه روی فایل SQLite» برداشته می‌شود.

    تست‌هایی که ``web.run(db_path=...)`` می‌کنند، موتور نمونه را به SQLite
    قفل می‌کنند؛ بدون این پاک‌سازی، تست یکپارچه‌سازی PostgreSQL (که عمداً
    بدون db_path اجرا می‌شود) به‌جای PostgreSQL روی SQLite اجرا می‌شد.
    """
    yield
    try:
        from app import schema
        schema.use_sqlite(None)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    """پنجره‌ی محدودیت نرخ بین تست‌ها پاک می‌شود.

    محدودیت نرخ (۲۰ درخواست ورود در ۶۰ ثانیه به‌ازای هر IP) در محیط واقعی
    درست است، اما چون تست‌ها در یک پروسه و پشت‌سرهم اجرا می‌شوند، شمارش
    درخواست‌ها روی هم انبار می‌شد و تست‌های بعدی خطای ۴۲۹ می‌گرفتند.
    """
    try:
        from app import web
        web.reset_rate_limits()
    except Exception:
        pass
    yield
    try:
        from app import web
        web.reset_rate_limits()
    except Exception:
        pass
