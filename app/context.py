# -*- coding: utf-8 -*-
"""زمینه‌ی درخواست جاری: حساب (tenant) و کاربر — برای ایزوله‌کردن داده‌ی مشترکین"""

import threading

_tl = threading.local()


def set_account(account_id):
    _tl.account_id = int(account_id) if account_id else 0


def get_account():
    return getattr(_tl, "account_id", 0)


def set_user(user_id):
    _tl.user_id = int(user_id) if user_id else 0


def get_user():
    return getattr(_tl, "user_id", 0)
