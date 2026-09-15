<div dir="rtl">

# مرجع API

پایه: `http://localhost:8000`

- پاسخ‌ها JSON هستند.
- احراز هویت: هدر `X-Token` (توکن دریافتی از `/api/login`). بدون توکن، حالت «مدیر دمو».
- مبالغ همیشه به صورت **عدد صحیح کوچک‌ترین واحد** ارسال/دریافت می‌شوند.
  (دلار: سنت = مقدار × ۱۰۰ ؛ دینار/ریال: بدون ضریب)

## احراز هویت

### `POST /api/login`
```json
{ "username": "admin", "password": "admin123" }
```
پاسخ: `{ "token": "...", "user": { "id": 1, "full_name": "...", "role": "admin" } }`

### `GET /api/me`
کاربر جاری.

---

## داشبورد و مرجع‌ها

| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/dashboard` | موجودی صندوق‌ها، بدهکاران/بستانکاران، آمار امروز، آخرین عملیات |
| GET | `/api/currencies` | فهرست ارزها |
| GET | `/api/parties` | فهرست طرف حساب‌ها |
| GET | `/api/party?id=N` | پروفایل کامل + مانده‌ها + فاکتورها + اسکناس‌ها |
| GET | `/api/cashboxes` | صندوق‌ها با موجودی هر ارز |
| GET | `/api/rates` | آخرین نرخ مرجع هر ارز |
| GET | `/api/rates/status` | منبع پیش‌فرض نرخ + وضعیت تازه‌سازی + منابع در دسترس |

---

## عملیات مالی

### `POST /api/buy` — خرید ارز
```json
{
  "party_id": 1, "currency_id": 2, "amount": 100000, "rate": 121000,
  "method": "cash", "cashbox": 1, "confirm": true, "description": "..."
}
```
- `method`: `cash` | `card` | `transfer` | `mix` | `later` (نسیه)
- `amount` = سنت (مثلاً ۱۰۰۰ دلار = ۱۰۰۰۰۰)

### `POST /api/sell` — فروش ارز
مانند خرید + `allow_negative` (فقط مدیر؛ ثبت موجودی منفی)

### `POST /api/loan/receive` — دریافت قرض
```json
{ "party_id": 1, "currency_id": 2, "amount": 500000, "rate": 122000, "cashbox": 1 }
```

### `POST /api/loan/give` — قرض دادن (همان ساختار)

### `POST /api/loan/repay` — بازپرداخت قرض
```json
{ "loan_id": 1, "amount": 200000, "rate": 122500, "cashbox": 1 }
```

### `POST /api/payment` — تسویه حساب طرف حساب
```json
{ "party_id": 1, "direction": "receive", "currency_id": 2, "amount": 10000, "rate": 123000 }
```
- `direction`: `receive` (او به ما می‌دهد) | `pay` (ما به او می‌دهیم)

### `POST /api/transfer` — انتقال بین صندوق
```json
{ "from": 1, "to": 2, "currency_id": 2, "amount": 300000, "rate": 122000 }
```

### `POST /api/expense` / `POST /api/income`
```json
{ "title": "اجاره دفتر", "currency_id": 1, "amount": 80000000, "rate": 1, "cashbox": 1 }
```

### `POST /api/adjust` — اصلاح صندوق
```json
{ "cashbox": 1, "currency_id": 2, "amount": 5000, "rate": 122000, "reason": "مغایرت‌گیری" }
```
(مقدار منفی = کسر)

### `POST /api/void` — لغو سند
```json
{ "journal_id": 12, "reason": "خطای ثبت" }
```

## حذف نرم (v0.8) — همه‌ی بخش‌ها + سطل بازیافت

همه‌ی این endpoint ها به مجوز `delete` نیاز دارند (پیش‌فرض: سوپرادمین/مدیر).

| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/delete/info?type=&id=` | پیش‌نمایش حذف: نام رکورد + هشدارها + مسدودیت (`blocked`, `blocked_reason`) |
| POST | `/api/delete` | حذف نرم — `{ "type": "...", "id": N }`؛ اسناد مالی (فاکتور/هزینه/درآمد/قرض/پرداخت) همزمان لغو می‌شوند |
| GET | `/api/deleted` | سطل بازیافت (فهرست رکوردهای حذف‌شده) |
| POST | `/api/restore` | بازیابی — `{ "type": "...", "id": N }` |

نوع‌های پشتیبانی‌شده: `party`، `cashbox`، `currency`، `user`، `invoice`، `payment`،
`loan`، `expense`، `income`، `banknote`، `category` و **`account`** (حساب/مشترک — v0.9.1).
حذفِ `account` فقط برای سوپرادمین است؛ با حذف، کاربران آن حساب از ورود منع می‌شوند
(در `_guard_suspended` هم `deleted_at` چک می‌شود) و از سطل بازیافت قابل بازیابی است.

محافظت‌ها: حذفِ خود کاربر، آخرین مالک/مدیر فعال حساب، آخرین سوپرادمین و آخرین
صندوق/ارز فعال مسدود است.

---

## فاکتور، اسکناس، بکاپ

| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/invoices` | فهرست فاکتورها |
| GET | `/api/invoice?id=N` | جزئیات فاکتور + پایه‌های سند |
| GET | `/api/transactions?limit=N` | دفتر تراکنش‌ها |
| GET | `/api/journal?id=N` | جزئیات سند (برای لغو) |
| GET | `/api/debts` | مانده‌ی همه‌ی طرف حساب‌ها به تفکیک ارز |
| GET | `/api/loans` | قرض‌ها با مجموع بازپرداخت‌شده |
| GET | `/api/banknotes?q=&status=&currency=` | جستجوی اسکناس |
| GET | `/api/banknote?id=N` | جزئیات + تاریخچه + تصاویر |
| POST | `/api/banknote/save` | ثبت اسکناس (هشدار تکراری در `duplicate`) |
| POST | `/api/banknote/photo` | ذخیره‌ی عکس (base64) |
| GET | `/api/audit` | لاگ کاربران |
| POST | `/api/backup` | ایجاد بکاپ |
| GET | `/api/backup/list` | فهرست بکاپ‌ها |
| GET | `/api/backup/download?file=` | دانلود بکاپ |

---

## گزارش‌ها

### `GET /api/report/cashbox?cashbox=1&day=YYYY-MM-DD`
گزارش روزانه‌ی صندوق به تفکیک ارز (مانده اول، ورودی، خروجی، مانده پایان).

### `GET /api/report/profit?from=YYYY-MM-DD&to=YYYY-MM-DD`
سود و زیان دوره‌ای + سود محقق FIFO به تفکیک ارز.

### `GET /api/report/party?id=N`
گزارش کامل طرف حساب.

---

## فاز ۵ — احراز هویت، OCR، خروجی، سلامت

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/login` | ورود — توکن در دیتابیس `sessions` (اعتبار ۱۲ ساعت) |
| POST | `/api/logout` | خروج (حذف نشست) |
| GET | `/api/users` | فهرست کاربران (فقط مدیر) |
| POST | `/api/user/save` | ایجاد/ویرایش کاربر + تغییر رمز (فقط مدیر) |
| GET | `/api/health` | سلامت سیستم: موتور دیتابیس، نسخه، OCR، uptime |
| POST | `/api/ocr` | تشخیص سریال از عکس (base64) — فقط پیشنهاد |
| GET | `/api/report/monthly?from=&to=` | گزارش ماهانه (خرید/فروش/درآمد/هزینه/سود خالص) |
| GET | `/api/export/all` | بکاپ کامل JSON (همه جدول‌ها) |
| POST | `/api/import` | بازیابی از JSON |
| GET | `/api/export/csv?type=` | CSV با BOM — `transactions` / `invoices` / `banknotes` / `parties` |

### صفحه‌بندی
`/api/transactions`، `/api/invoices`، `/api/banknotes`، `/api/audit` پارامترهای
`page` و `limit` را می‌پذیرند و `total` را برمی‌گردانند.

### نمونه OCR
```json
POST /api/ocr  { "data": "data:image/png;base64,..." }
→ { "available": true, "suggestions": ["AB12345678"] }
```

### هش رمز عبور
PBKDF2-HMAC-SHA256 با salt تصادفی — قالب ذخیره: `pbkdf2$sha256$120000$<salt>$<hash>`

---

## فاز ۶ — چندمشترکی، گوگل، نرخ آنلاین، نمودار

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/signup` | ثبت‌نام عمومی — ساخت حساب (مشترک) + مالک + نشست |
| GET | `/api/auth/google/url` | ساخت لینک ورود گوگل (در صورت پیکربندی) |
| GET | `/api/auth/google/callback?code=` | بازگشت گوگل — ورود/ساخت حساب بر اساس `google_sub` |
| GET | `/api/accounts` | فهرست مشترکین + آمار (فقط سوپرادمین) |
| POST | `/api/account/save` | ایجاد/ویرایش مشترک (فقط سوپرادمین) |
| POST | `/api/impersonate` | ورود به‌جای کاربر (`{"user_id": N}`) — نشست با `impersonated_by` |
| GET | `/api/users` | فهرست کاربران (سوپرادمین: همه؛ مالک: کارمندان خودش) |
| POST | `/api/user/save` | ایجاد/ویرایش کارمند (مالک) یا هر کاربر (سوپرادمین) |
| POST | `/api/rates/fetch` | دریافت نرخ لحظه‌ای از اینترنت (`{"provider": "navasan"}` پیش‌فرض؛ با fallback خودکار) |
| POST | `/api/rate` | ثبت دستی نرخ مرجع (`{"currency_id": N, "rate": R}`) |
| POST | `/api/settings/save` | ذخیره `rate_source`، `rate_auto_refresh` و `rate_navasan_key` حساب جاری |
| POST | `/api/google/save` | ذخیره Client ID/Secret گوگل (فقط سوپرادمین) |
| GET | `/api/report/charts?from=&to=` | داده‌ی نمودارها: ترکیب صندوق، هزینه به تفکیک دسته، روند روزانه، ماهانه، طرف‌های برتر، **روند نرخ** و **مقایسه با سال قبل** |

## فاز ۰٫۴ — امنیت، ارزها، اسکناس گروهی، کف موجودی، PDF

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/currency/save` | افزودن/ویرایش ارز (فقط سوپرادمین) — `{id?, code, name, symbol, decimals, unit_ratio, sort_order, is_active}` |
| GET | `/api/currencies/all` | فهرست کامل ارزها (فعال + غیرفعال) — فقط سوپرادمین |
| POST | `/api/banknote/bulk` | ثبت گروهی اسکناس — `{currency_id, denomination, serials: [...], status?, cashbox_id?, note?}`؛ پاسخ `{inserted, duplicates, skipped}` |
| GET | `/api/lowstock` | ارزهایی که موجودی‌شان زیر حد تعیین‌شده است |
| POST | `/api/lowstock/save` | ذخیره حداقل موجودی هر ارز — `{thresholds: {"USD": 100, "EUR": 0}}` (۰ = حذف) |
| GET | `/api/report/pdf?from=&to=` | خروجی PDF فارسی (RTL، فونت وزیرمتن) — خلاصه سود/زیان، FIFO، ماهانه، صندوق‌ها |
| POST | `/api/password/forgot` | ساخت کد یک‌بارمصرف بازنشانی (بدون ورود) |
| POST | `/api/password/reset` | مصرف کد + رمز جدید — `{username, code, new_password}` |
| POST | `/api/password/change` | تغییر رمز شخصی — `{old_password, new_password}` |
| GET | `/api/settings` | خواندن تنظیمات حساب جاری (از جمله `min_stock_{CODE}`) |
| POST | `/api/2fa/start` | ساخت کلید TOTP (فقط مدیر/سوپرادمین) — پاسخ `{secret, url}` |
| POST | `/api/2fa/confirm` | فعال‌سازی 2FA — `{secret, code}` |
| POST | `/api/2fa/disable` | غیرفعال‌سازی — `{code}` یا `{password}`؛ سوپرادمین می‌تواند با `{user_id}` برای دیگری غیرفعال کند |
| POST | `/api/login` | در صورت فعال بودن 2FA، فیلد `code` لازم است؛ پاسخ `401` با `"need_2fa": true` |

### قفل ورود (anti brute-force)
- ۵ تلاش ناموفق → قفل ۱۵ دقیقه‌ای برای آن نام کاربری (پاسخ `429` با پیام فارسی).
- ورود موفق تلاش‌ها را پاک می‌کند.
- حساب «معلق» (suspended) نمی‌تواند وارد شود (`403`) و عملیاتش مسدود است.

### محدودیت پلن
- پلن `free`: حداکثر ۵ کاربر، ۵ صندوق، ۲۰۰۰ فاکتور. پلن `pro`: نامحدود.
- هنگام ساخت کاربر جدید از سقف، خطای فارسی برمی‌گردد.

### سوپرادمین و هدر `X-Account-Id`
سوپرادمین با ارسال `X-Account-Id: N` همان پاسخ‌ها را برای حساب N دریافت می‌کند
(مشاهده‌ی داده‌ی هر مشترک بدون ورود مجدد).

### نرخ آنلاین
- `provider`: `navasan` (پیش‌فرض — نرخ بازار ایران، تومان → ریال ×۱۰، نیاز به کلید) | `er-api` (نرخ ریال) | `tgju` (سنا — تومان → ریال ×۱۰) | `frankfurter` (بدون IRR)
- پاسخ `rates/fetch`: `{ "ok": true, "source_name": "...", "updated": [{code, rate}, ...], "provider", "fallback", "tried": [...] }`
- **v0.9.1**: اگر منبعی در لحظه پاسخ نداشته باشد (سنا `[]` برگرداند یا منبع نرخ ریالی نداشته باشد)،
  سرور به‌جای خطای ۵۰۰، `400` با پیام شفاف برمی‌گرداند (مثلاً «این منبع نرخ ریال ندارد»).
- **v0.9.2 — بازگشت خودکار (fallback)**: اگر منبع انتخابی شکست بخورد یا نرخ نداشته باشد،
  سرور به‌ترتیب `navasan ← er-api ← tgju` را امتحان می‌کند و اولین موفقیت را برمی‌گرداند
  (`fallback: true` یعنی منبع اصلی در دسترس نبوده و `tried` فهرست خطاهاست).
- کلید API نوسان در تنظیمات حساب ذخیره می‌شود (کلید `rate_navasan_key`) و در خروجی
  `/api/settings` همیشه **ماسک** (`********`) است؛ متغیر محیطی `SARRAFI_NAVASAN_KEY` هم پشتیبانی می‌شود.
- upsert نرخ با کلید یکتای `(account_id, currency_id, rate_date, rate_type)` انجام می‌شود؛
  اسکیما هنگام راه‌اندازی ایندکس یکتای `uq_er_acc_cur_date_type` را تضمین می‌کند.

## فاز ۰٫۵ — صندوق‌های بانکی/نقدی، ثبت اسکناس با دسته، تشخیص تصویری

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/cashbox/save` | تعریف/نام‌گذاری/ویرایش صندوق — `{id?, name, kind: "physical"\|"bank", description?, is_active?}` (فقط مدیر/سوپرادمین) |
| GET | `/api/batches` | فهرست دسته‌های ثبت اسکناس (banknote_batches) با تعداد اسکناس هر دسته |
| POST | `/api/detect` | تشخیص چند اسکناس از یک عکس — `{image: "data:...;base64,...", currency_id?}` |
| POST | `/api/detect/register` | ثبت اسکناس‌های تأییدشده از روی عکس — ساخت دسته + اسکناس + حرکت + عکس |

### پاسخ `/api/sell` و `/api/buy` (v0.5)
علاوه بر `invoice_no` و `rial_value`، حالا `invoice_id` و `journal_id` هم برمی‌گردد تا
فرانت بتواند بلافاصله ثبت اسکناسِ همان فاکتور را باز کند.

### پاسخ `/api/cashboxes` (v0.5)
هر صندوق حالا شامل `kind` (`physical` / `bank`)، `description` و `is_active` است.

### `POST /api/detect`
ورودی: `{ "image": "data:image/jpeg;base64,...", "currency_id": 2 }`

پاسخ:
```json
{
  "available": true,
  "count": 10,
  "quality": { "ok": true, "width": 2000, "height": 1600, "sharpness": 835.8,
               "saturation_ratio": 0.003, "issues": [], "tips": [] },
  "items": [
    { "index": 0, "serial": "S34765154Z", "serial_confidence": 1.0,
      "value": 100, "value_confidence": 0.99,
      "quad": [[x,y],...], "x": 54, "y": 48, "w": 348, "h": 705,
      "crop": "data:image/jpeg;base64,..." }
  ]
}
```
- `serial` و `value` صرفاً **پیشنهاد** OCR هستند؛ کاربر باید تأیید/اصلاح کند.
- `quality.issues` شامل `resolution` / `blur` / `glare` است و `tips` راهنمای فارسی دارد.
- اگر OpenCV نصب نباشد: `{ "available": false, "message": "..." }`.

### `POST /api/detect/register`
ورودی:
```json
{
  "currency_id": 2, "denomination": 100, "status": "sold",
  "cashbox_id": 1, "party_id": 5, "invoice_id": 11, "journal_id": 26,
  "source_image": "data:image/jpeg;base64,...",
  "items": [ { "serial": "S34765154Z", "crop": "data:image/jpeg;base64,..." } ]
}
```
پاسخ: `{ "batch_id": 1, "inserted": 2, "sold_existing": 0, "duplicates": [], "skipped": [], "banknote_ids": [...] }`

رفتار حالت `status="sold"`: اگر سریال قبلاً در خزانه ثبت شده باشد، وضعیتش «فروخته‌شده»
می‌شود و حرکت `sale` ثبت می‌گردد (به‌جای درج تکراری). عکس هر اسکناس (برش) به‌عنوان
`banknote_images` با `type="crop"` و `confidence` ذخیره و به فاکتور/مشتری متصل می‌شود.

### `GET /api/invoice?id=N` (v0.5)
علاوه بر `invoice` و `legs`، آرایه‌ی `photos` برمی‌گرداند: عکس‌های همه‌ی اسکناس‌هایی که
حرکتشان به `journal_id` همین فاکتور وصل است (به‌همراه سریال و ارز).

## فاز ۰٫۶ — چندنرخی، کارمزد/مالیات، سقف اعتبار، یادآور، اکسل، جستجو، SaaS

### چندنرخی — `POST /api/rate` با `rate_type`
```
{ "currency_id": 2, "rate": 501000, "rate_type": "buy" }   // market|buy|sell|sana
```
`GET /api/rates` حالا `by_type` هم برمی‌گرداند: `{ "buy": [...], "sell": [...], "sana": [...], "market": [...] }`.

### کارمزد و مالیات — `POST /api/buy` و `POST /api/sell`
پارامترهای جدید: `rate_type`, `fee_minor`, `tax_minor` (بر حسب ارز فاکتور).
پاسخ شامل `total_rial` (مبلغ + کارمزد + مالیات) و برای فروش نسیه `credit` (بررسی سقف اعتبار) است:
```json
{ "ok": true, "invoice_no": "S-1042", "total_rial": 50750000, "fee_rial": 500000, "tax_rial": 250000,
  "credit": { "credit_limit": 1000000, "used_rial": 500000, "would_exceed": true, "available_rial": 500000 } }
```

### `POST /api/party/save` با `credit_limit`
فیلد `credit_limit` (ریال) روی طرف حساب ذخیره می‌شود؛ `null` یعنی بدون محدودیت.

### `POST /api/loan/receive` و `POST /api/loan/give` با `due_date`
`due_date` با فرمت `YYYY-MM-DD`؛ `finance.loan_reminders()` قرض‌های معوق/نزدیک به سررسید را
برمی‌گرداند و `GET /api/dashboard` آن را در کلید `reminders` قرار می‌دهد.

### `POST /api/detect/register` با `count_only`
اگر `count_only` مثبت باشد، به همان تعداد اسکناس «شمارشی» با سریال موقت `NB{batch}-NNN` ساخته
می‌شود. اگر `invoice_id` داده شود، `reconciliation` هم برمی‌گردد:
```json
{ "reconciliation": { "expected_minor": 100000, "registered_minor": 90000, "matched": false, "diff_minor": 10000 } }
```
(مبلغ اسکناس = ارزش × `unit_ratio` × تعداد)

### `GET /api/search?q=...`
جستجوی سراسری: مشتریان، فاکتورها، اسناد، اسکناس‌ها. پاسخ `{ "q": "...", "items": [{type,id,title,subtitle,link}] }`.

### `GET /api/export/xlsx?type=...`
خروجی اکسل واقعی (openpyxl) با شیت راست‌به‌چپ. `type`: `transactions | invoices | banknotes | parties | loans`.

### `GET /api/forecast?days=30`
پیش‌بینی نقدینگی: `{ incoming_rial, outgoing_rial, net_rial, rial_balance, projected_rial, horizon }`.

### بکاپ رمزنگاری‌شده
- `POST /api/backup/passphrase { "passphrase": "..." }` → فعال/غیرفعال‌سازی رمزنگاری
- `POST /api/backup` → در صورت رمزنگاری، فایل `.enc` تولید می‌شود
- `POST /api/backup/restore { "data": "data:...", "passphrase": "..." }` → بازیابی (JSON یا `.enc`)

### SaaS — پلن و صورتحساب
- `GET /api/plans` → فهرست پلن‌ها (free/pro/enterprise)
- `POST /api/billing/checkout { "plan_code": "pro" }` → ساخت صورتحساب شبیه‌سازی + `ref_code`
- `POST /api/billing/confirm { "ref_code": "..." }` → پرداخت موفق + فعال‌سازی پلن
- `GET /api/billing` → فهرست صورتحساب‌ها (سوپرادمین/مدیر)
- `POST /api/smtp/save` → پیکربندی ایمیل (سوپرادمین) برای ارسال واقعی کد بازیابی

### `POST /api/password/forgot`
در صورت پیکربندی SMTP و داشتن ایمیل کاربر، کد به ایمیل ارسال می‌شود (`sent: true`)؛
در غیر این صورت `code` در پاسخ برمی‌گردد (حالت دمو).

## فاز ۰٫۷ — ماژول‌ها، نقش‌های قابل ویرایش، صندوق سلسله‌مراتبی، پیوند اسکناس

### `GET /api/me` (تکمیل v0.7)
علاوه بر مشخصات، حالا `modules` (فلگ‌های موثر کاربر)، `perms` (مجوزهای موثر) و `roles` را برمی‌گرداند:
```json
{ "id": 1, "role": "admin", "modules": { "fee_tax": false, "loans": true, ... }, "perms": { "buy": true, ... } }
```

### ماژول‌ها — `GET /api/modules?user_id=N` و `POST /api/modules/save`
- `GET /api/modules` → `{ catalog: [{key,name,icon,desc,default}], account_flags: {...}, user_overrides: {...} }`
  با `user_id` استثناهای همان کاربر هم برمی‌گردد.
- `POST /api/modules/save { "flags": { "fee_tax": true, ... }, "user_id": N }` → بدون `user_id` فلگ‌های حساب
  (توسط مالک/مدیر)، با `user_id` استثناهای یک کاربر (توسط سوپرادمین). اعمال سروری: هر ماژول به
  مسیرهای API خودش نگاشت دارد (`MODULE_ENDPOINTS`) و درخواست ماژول خاموش `403` می‌گیرد.

### نقش‌های قابل ویرایش — `GET /api/permissions` و `POST /api/permissions/save`
- `GET /api/permissions` → `{ perms: [{key,name}], roles, role_fa, matrix: { role: { perm: bool } } }`
- `POST /api/permissions/save { "role": "cashier", "perms": { "buy": true, "void": false, ... } }` →
  ماتریس آن نقش را برای **همه‌ی حساب‌ها** بازنویسی می‌کند (سوپرادمین). نقش `super_admin` همیشه همه‌چیز دارد.

### صندوق سلسله‌مراتبی — `POST /api/cashbox/save`
فیلدهای جدید: `parent_id` (زیرشاخه‌ی بانک/گروه) و `currency_id` (تک‌ارزی‌کردن زیرشاخه).
```json
{ "name": "بانک ملی", "kind": "bank" }                     → والد
{ "name": "دلاری", "kind": "bank", "parent_id": 1, "currency_id": 2 }  → زیرشاخه تک‌ارزی
```
`GET /api/cashboxes` حالا `parent_id` و `currency_id` را برمی‌گرداند تا فرانت درخت را رسم کند.
دسترسی ساخت/ویرایش صندوق با مجوز `cashbox_manage` (قابل ویرایش در ماتریس نقش‌ها).

### پیوند اسکناس به طرف حساب — `POST /api/banknote/bulk`
فیلدهای جدید: `party_id` و `movement_type` (`purchase`/`sale`). برای هر اسکناس یک ردیف در
`banknote_movements` ثبت می‌شود تا مالکیت اسکناس به همان طرفِ معامله متصل بماند:
```json
{ "currency_id": 2, "denomination": 10000, "serials": ["AB12345678"],
  "status": "in_vault", "cashbox_id": 1, "party_id": 5, "movement_type": "purchase" }
```

### کارمزد/مالیات اختیاری
وقتی ماژول `fee_tax` خاموش است، سرور `fee_minor`/`tax_minor` را نادیده می‌گیرد و صفر ذخیره می‌کند
و پاسخ فاکتور فاقد ردیف کارمزد/مالیات است؛ فرانت هم فیلدها را مخفی می‌کند. پیش‌فرض حساب‌های جدید: **خاموش**.

## فاز ۰٫۹٫۲ — منبع نرخ «نوسان» + بازگشت خودکار

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/rates/fetch` | دریافت نرخ — `{ provider? }`؛ بدون provider از پیش‌فرض (نوسان) شروع و در صورت شکست fallback می‌شود؛ پاسخ شامل `fallback` و `tried` |
| POST | `/api/rates/test` | تست اتصال به یک منبع — `{ provider?, key? }`؛ بدون ذخیره‌سازی |
| GET | `/api/rates/status` | حالا `navasan_key_set` (bool) و `source` پیش‌فرض `navasan` را برمی‌گرداند |
| POST | `/api/settings/save` | کلید جدید `rate_navasan_key` — رشتهٔ خالی یعنی حذف کلید؛ `********` یعنی بدون تغییر |
| GET | `/api/settings` | مقدار `rate_navasan_key` همیشه `********` (ماسک) است |

### نمادهای نوسان → کد ارز (نگاشت)
`usd→USD`، `usd_sell→USD`، `usd_buy→USD`، `eur→EUR`، `gbp→GBP`، `aed→AED`،
`try→TRY`، `chf→CHF`، `cny→CNY`، `rub→RUB` — برای هر ارز اولین نمادِ موجود انتخاب می‌شود.
پاسخ نوسان `value` را به‌صورت رشته برمی‌گرداند و واحدش **تومان** است (→ ×۱۰ ریال).
دینار عراق (IQD) در نوسان نیست و از er-api تأمین می‌شود.

## فاز ۰٫۹٫۱ — حذف مشترک، لوگوی حساب، اصلاح نرخ

| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/accounts` | فهرست مشترکین (فقط سوپرادمین) — حالا حساب‌های حذف‌شده را برنمی‌گرداند و `logo` هر حساب را دارد |
| POST | `/api/account/save` | ساخت/ویرایش حساب — فیلد جدید `logo` (مسیر نسبی مثل `uploads/acct_logo_1.png`) |
| POST | `/api/account/logo` | بارگذاری/حذف لوگوی حساب — `{ "account_id": N, "data": "data:image/png;base64,..." }`؛ با `data: ""` حذف می‌شود. سوپرادمین برای هر حساب، مدیر فقط برای حساب خودش |
| POST | `/api/delete` / `POST /api/restore` | نوع جدید `account` برای حذف نرم/بازیابی حساب (مشترک) |
| POST | `/api/rates/fetch` | خطای شفاف `400` وقتی منبع نرخ ندارد (به‌جای ۵۰۰) |

### لوگوی حساب (v0.9.1)
- ستون `accounts.logo` مسیر نسبی فایل در `data/uploads/` را نگه می‌دارد؛ فایل از
  `GET /uploads/<file>` سرو می‌شود.
- `/api/me` مقدار `account.logo` (برای کاربران دارای حساب) و `/api/accounts` مقدار `logo`
  هر حساب را برمی‌گرداند؛ فرانت از آن برای سایدبار و فهرست مشترکین استفاده می‌کند.

### اسکیما (v0.9.1)
- جدول `accounts`: ستون‌های جدید `logo` و `deleted_at`.
- جدول `exchange_rates`: ایندکس یکتای `uq_er_acc_cur_date_type` روی
  `(account_id, currency_id, rate_date, rate_type)` برای upsert نرخ‌ها.

## نمونه خطا

```json
{ "error": "موجودی کافی نیست: موجودی USD برابر 12650.00 است." }
```

</div>
