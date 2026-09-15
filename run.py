# -*- coding: utf-8 -*-
"""
نقطه‌ی ورود اجرای سیستم صرافی

    python run.py                 # پورت 8000
    SARRAFI_PORT=9000 python run.py
    python run.py --reset         # بازسازی کامل دیتابیس با داده‌ی نمونه
    python run.py --reset --seed  # مشابه بالا

متغیرهای محیطی:
    SARRAFI_PORT            : پورت (پیش‌فرض 8000)
    SARRAFI_DB              : مسیر فایل دیتابیس SQLite
    SARRAFI_DATABASE_URL    : آدرس PostgreSQL (postgresql://user:pass@host/db)
    SARRAFI_AUTH_REQUIRED   : 1 = احراز هویت اجباری (بدون حالت دمو)
    SARRAFI_BACKUP_PASSPHRASE : عبارت عبور رمزنگاری بکاپ‌های خودکار
    SARRAFI_BACKUP_HOURS    : فاصله‌ی بکاپ خودکار (ساعت؛ پیش‌فرض ۲۴)
"""

import os
import sys
import argparse

from app import web, schema, seed


def main():
    parser = argparse.ArgumentParser(description="سیستم مدیریت صرافی")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SARRAFI_PORT", 8000)))
    parser.add_argument("--reset", action="store_true", help="بازسازی دیتابیس")
    parser.add_argument("--seed", action="store_true", help="بارگذاری داده‌ی نمونه")
    args = parser.parse_args()

    if args.reset or args.seed:
        print("در حال بازسازی دیتابیس و بارگذاری داده‌ی نمونه ...")
        seed.reset_and_seed()
        print("✅ دیتابیس بازسازی شد.")

    info = schema.db_info()
    if info["engine"] == "postgresql":
        print(f"🗄 موتور دیتابیس: PostgreSQL ({info['url']})")
    else:
        print(f"🗄 موتور دیتابیس: SQLite ({info['path']})")

    srv = web.run(port=args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ توقف سرور")
        srv.server_close()


if __name__ == "__main__":
    main()
