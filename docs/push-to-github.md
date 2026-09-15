# بردن نسخه روی GitHub

مخزن مقصد: `https://github.com/mrseif1367/sarrafi.git`
شاخهٔ فعلی پروژه: `main` — در حال حاضر ۳۲ کامیت آمادهٔ ارسال است.

---

## روش ۰ (ساده‌ترین — ویندوز) — فایل `git-push.bat`

روی فایل **`git-push.bat`** دوبار کلیک کنید. همین. اسکریپت خودش همه‌ی کارها را انجام می‌دهد:

1. بررسی نصب بودن گیت
2. ساخت مخزن محلی در صورت نبود و تنظیم هویت گیت
3. خواندن/گرفتن نام کاربری، نام مخزن و شاخه
4. گرفتن توکن (ورودی مخفی) و **ذخیره‌ی رمزنگاری‌شده‌ی آن** برای اجراهای بعدی
5. بررسی وجود مخزن روی گیت‌هاب؛ **تصحیح خودکار نام کاربری از روی توکن** و **ساخت خودکار مخزن** در صورت نبود
6. کامیت همه‌ی تغییرات با پیام خودکار
7. ارسال به گیت‌هاب + **هم‌سان‌سازی خودکار** اگر ریموت جلوتر باشد
8. ساخت و ارسال تگ نسخه + پیشنهاد آپلود فایل بسته در بخش Releases

نکات مهم:

- **بار اول** توکن و نام مخزن را می‌پرسد؛ از آن به بعد اجرا کاملاً خودکار است.
- **نام کاربری را خودش بررسی می‌کند**: گیت‌هاب در نام کاربری نقطه/زیرخط/فاصله نمی‌پذیرد؛
  اگر نام اشتباه باشد، bat حساب واقعی را از روی توکن می‌خواند و خودش اصلاح می‌کند.
- اگر تعارضی بین فایل‌های محلی و نسخه‌ی روی گیت باشد، **وضعیت به قبل برمی‌گردد و هیچ فایلی پاک نمی‌شود**؛
  سپس با تأیید شما می‌تواند نسخه‌ی محلی را جایگزین نسخه‌ی روی گیت کند.
- توکن به‌صورت **رمزنگاری‌شده با کلید ویندوز (DPAPI)** در `%USERPROFILE%\.sarrafi\` ذخیره می‌شود
  و فقط با همان حساب کاربری ویندوز قابل خواندن است.
- اجرا بدون پرسش: `git-push.bat --yes` — پاک‌کردن تنظیمات: `git-push.bat reset`
- اگر توکن ندارید در همان پنجره راهنما نشان داده می‌شود؛ ساخت توکن یک‌دقیقه‌ای است (بخش بعدی).

---

## روش ۱ (لینوکس/مک و حالت دستی) — اسکریپت `git-push.sh` و توکن PAT

### ۱- گرفتن توکن
**توکن کلاسیک (ساده‌تر):**
1. وارد GitHub شوید → روی عکس پروفایل → **Settings**
2. پایین منوی چپ → **Developer settings**
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
4. نام: `sarrafi-push` — مدت: ۹۰ روز (یا دلخواه)
5. تیک اسکوپ **`repo`** را بزنید (کامل)
6. **Generate token** → توکن (`ghp_...`) را کپی کنید. **فقط یک‌بار نمایش داده می‌شود.**

**توکن ریزدانه (جایگزین مدرن):**
Settings → Developer settings → **Personal access tokens → Fine-grained tokens** → Generate new token
→ Repository access: *Only select repositories* → `sarrafi`
→ Permissions → Repository permissions → **Contents: Read and write** (+ **Metadata: Read**)

### ۲- اجرای پوش
در پوشهٔ پروژه:

```bash
cd sarrafi
bash git-push.sh
```
اسکریپت نام کاربری (`mrseif1367`) و توکن را می‌پرسد (توکن هنگام تایپ نمایش داده نمی‌شود)،
remote را تنظیم می‌کند و شاخهٔ `main` را می‌فرستد.

**دستی (بدون اسکریپت):**
```bash
git remote add origin https://github.com/mrseif1367/sarrafi.git   # اگر قبلاً نبود
git branch -M main
git push -u origin main
# وقتی پرسید: Username = mrseif1367   |   Password = همان توکن (نه رمز گیت‌هاب)
```

> ⚠️ نکتهٔ امنیتی: توکن را داخل آدرس remote **ذخیره نکنید** (`git remote set-url` با توکن داخل URL).
> اگر این کار را کردید، بعدش پاکش کنید:
> `git remote set-url origin https://github.com/mrseif1367/sarrafi.git`

### ۳- ذخیرهٔ توکن برای دفعه‌های بعد (اختیاری)
```bash
git config --global credential.helper store   # لینوکس/مک (ذخیره در ~/.git-credentials)
git config --global credential.helper manager # ویندوز (Credential Manager)
```

---

## روش ۲ — از روی کامپیوتر خودتان (بعد از دانلود فایل)

```bash
# استخراج بسته
tar -xzf sarrafi-full-git-ready-v092.tar.gz -C sarrafi
cd sarrafi

git init
git branch -M main
git add -A
git commit -m "v0.9.2: Navasan rate source + automatic fallback"

git remote add origin https://github.com/mrseif1367/sarrafi.git
git push -u origin main
```
اگر مخزن روی GitHub از قبل کامیت اولیه (README) دارد، قبلش این را بزنید تا تاریخچه‌ها تلاقی نکنند:
```bash
git pull origin main --rebase --allow-unrelated-histories
git push -u origin main
```

---

## روش ۳ — با SSH (بدون توکن، راحت‌ترین برای بلندمدت)

```bash
# ساخت کلید (اگر ندارید)
ssh-keygen -t ed25519 -C "you@example.com"     # اینتر اینتر اینتر
cat ~/.ssh/id_ed25519.pub
```
خروجی را در GitHub → Settings → **SSH and GPG keys** → **New SSH key** بچسبانید. بعد:
```bash
git remote set-url origin git@github.com:mrseif1367/sarrafi.git
git push -u origin main
```

---

## روش ۴ — با GitHub CLI

```bash
# نصب: https://cli.github.com   |  ویندوز: winget install GitHub.cli
gh auth login          # GitHub.com → HTTPS → Login with a web browser
gh repo set-default mrseif1367/sarrafi
git push -u origin main
```

---

## خطاهای رایج

| خطا | علت | راه‌حل |
|---|---|---|
| `Support for password authentication was removed` | به‌جای توکن، رمز حساب را زده‌اید | با PAT وارد شوید (روش ۱) |
| `remote: Permission to ... denied` | توکن اسکوپ `repo` ندارد یا حساب اشتباه است | توکن را با اسکوپ `repo` (یا Contents: Read and write) بسازید |
| `remote: Repository not found` (ولی مخزن وجود دارد) | **نام کاربری اشتباه/نامعتبر** — گیت‌هاب در نام کاربری نقطه، زیرخط و فاصله نمی‌پذیرد (مثلاً `mr.seif1367` نامعتبر است) | نام کاربری درست را وارد کنید؛ `git-push.bat` این حالت را خودکار تشخیص و اصلاح می‌کند |
| مخزن با نام عجیب مثل `GH_REPO` ساخته شد | خرابی مقدار در فایل تنظیمات (ذخیره‌شدن نام متغیر به‌جای مقدار آن) | آخرین نسخه‌ی `git-push.bat` مقادیر شبه‌متغیر را نادیده می‌گیرد؛ برای بازنشانی کامل: `git-push.bat reset`. مخزن اشتباه را از GitHub → Settings → Danger Zone حذف کنید |
| `. was unexpected at this time.` یا `( was unexpected at this time.` | در فایل‌های batch، پرانتز داخل متن `echo` درون بلوک `if ( ... )` بلوک را زودتر می‌بندد | از نسخه‌ی اصلاح‌شده‌ی `git-push.bat` استفاده کنید؛ صحت فایل با `python tools/lint_bat.py` بررسی می‌شود |
| سیل هشدار `LF will be replaced by CRLF` | تنظیم `core.autocrlf=true` ویندوز | `git-push.bat` خودش `core.autocrlf false` را در مخزن تنظیم می‌کند (پروژه `.gitattributes` دارد) |
| `remote origin already exists` | remote قبلاً تنظیم شده | `git remote set-url origin <url>` |
| `failed to push some refs / non-fast-forward` | تاریخچهٔ ناهمخوان (مثلاً README ساختهٔ GitHub) | ابتدا `git pull origin main --rebase --allow-unrelated-histories` |
| `src refspec main does not match any` | روی شاخهٔ دیگری هستید | `git branch -M main` |
| فایل‌های حجیم رد می‌شوند (>100MB) | فایل بزرگ کامیت شده | از `.gitignore` استفاده کنید یا `git lfs` |

---

## افزودن تگ نسخه (اختیاری، برای Release)

```bash
git tag -a v0.9.2 -m "نسخهٔ ۰٫۹٫۲ — منبع نرخ نوسان + بازگشت خودکار"
git push origin v0.9.2
```
بعد در GitHub → **Releases** → *Draft a new release* → تگ `v0.9.2` را انتخاب و فایل
`sarrafi-full-git-ready-v092.tar.gz` را به‌عنوان دارایی (asset) آپلود کنید.

---

## نکتهٔ مهم دربارهٔ فایل‌های ناخواسته
مطمئن شوید این‌ها هیچ‌وقت کامیت نشوند (در `.gitignore` هستند): پوشهٔ `data/` (دیتابیس و بکاپ‌ها)،
`__pycache__/`، `.env` (کلیدها و رمزها)، و `*.tar.gz`. توکن نوسان هم فقط در دیتابیس/متغیر محیطی
ذخیره می‌شود، نه در سورس.
