@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Sarrafi - Push to GitHub

REM ============================================================
REM  Sarrafi - سامانه‌ی مدیریت خرید و فروش ارز
REM  ابزار یک‌کلیکی ویندوز: ارسال فایل‌های پروژه روی GitHub
REM
REM  مراحل روی صفحه چاپ می‌شوند:
REM    1) بررسی گیت            2) آماده‌سازی مخزن و هویت
REM    3) تنظیمات مقصد          4) توکن گیت‌هاب
REM    5) بررسی مخزن مقصد        6) هم‌سان‌سازی تاریخچه و ثبت تغییرات
REM    7) ارسال به گیت‌هاب        8) تگ نسخه و آپلود اختیاری فایل
REM
REM  نکته‌ی مهم: پیش از ثبت تغییرات، تاریخچه با مخزن گیت هم‌سو می‌شود؛
REM  بنابراین ارسال بدون تعارض و بدون جایگزینی اجباری انجام می‌گیرد.
REM
REM  اجرا:
REM    git-push.bat          -> اجرای عادی، فقط بار اول سؤال می‌پرسد
REM    git-push.bat reset    -> پاک‌کردن تنظیمات و توکن ذخیره‌شده
REM    git-push.bat --yes    -> بدون هیچ سؤالی، خودکار
REM ============================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "CFG_DIR=%USERPROFILE%\.sarrafi"
set "CFG_FILE=%CFG_DIR%\push-config.txt"
set "TOK_FILE=%CFG_DIR%\push-token.dpapi"
set "DEF_USER=mrseif1367"
set "DEF_REPO=sarrafi"
set "DEF_BRANCH=main"
set "TMP_LOG=%TEMP%\sarrafi-push-%RANDOM%.log"
set "TLS=[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;"
set "PSH=powershell -NoProfile -ExecutionPolicy Bypass -Command"
set "GIT_TERMINAL_PROMPT=0"
set "NONSTOP="
set "VER="
set "RC=0"
set "FIXED="
set "KEPT=0"
if /i "%~1"=="--yes" set "NONSTOP=1"

echo:
echo +------------------------------------------------------------+
echo ^|       Sarrafi - ارسال خودکار فایل‌ها به GitHub             ^|
echo +------------------------------------------------------------+
echo:
echo   [i] همه‌ی مراحل با جزئیات نمایش داده می‌شود.
echo       اجرای بعدی خودکار است و چیزی نمی‌پرسد.
echo:

if /i "%~1"=="reset" (
  del /q "%CFG_FILE%" 2>nul
  del /q "%TOK_FILE%" 2>nul
  echo   [OK] تنظیمات و توکن ذخیره‌شده پاک شد.
  echo:
)

REM ============================================================
REM  پیدا کردن پوشه‌ی پروژه در صورت اجرا از پوشه‌ی والد
REM ============================================================
if not exist "app\web.py" (
  for /d %%d in (*) do (
    if exist "%%d\app\web.py" (
      echo   [i] پوشه‌ی پروژه پیدا شد: %%d
      cd /d "%%d"
    )
  )
)

REM ============================================================
REM  1) بررسی نصب بودن گیت
REM ============================================================
where git >nul 2>nul
if errorlevel 1 (
  echo   [X] گیت روی این سیستم نصب نیست.
  echo       صفحه‌ی دانلود باز می‌شود: https://git-scm.com/download/win
  start "" "https://git-scm.com/download/win"
  goto :fail
)
for /f "delims=" %%v in ('git --version 2^>nul') do echo   [1/8] %%v آماده است.
where powershell >nul 2>nul
if errorlevel 1 echo   [i] پاورشل پیدا نشد؛ ورودی مخفی توکن و بررسی‌های آنلاین انجام نمی‌شود.

REM ============================================================
REM  2) آماده‌سازی مخزن محلی و هویت گیت
REM ============================================================
if not exist ".git" (
  echo   [2/8] ساخت مخزن گیت محلی ...
  git init -q
  git branch -M main
) else (
  echo   [2/8] مخزن گیت موجود است.
)

set "GIT_MAIL="
for /f "delims=" %%i in ('git config user.email 2^>nul') do set "GIT_MAIL=%%i"
if "%GIT_MAIL%"=="" (
  echo         ثبت هویت گیت برای این مخزن ...
  git config user.name "%DEF_USER%"
  git config user.email "%DEF_USER%@users.noreply.github.com"
)

REM خط پایانی فایل‌ها را به .gitattributes پروژه بسپار تا هشدار LF/CRLF ندهد
set "AUTOCRLF="
for /f "delims=" %%a in ('git config --get core.autocrlf 2^>nul') do set "AUTOCRLF=%%a"
if /i not "!AUTOCRLF!"=="false" (
  git config core.autocrlf false
  echo         [i] تنظیم خط پایانی مخزن روی false — حذف هشدارهای LF/CRLF.
)

REM ============================================================
REM  3) تنظیمات مقصد: کاربر / مخزن / شاخه
REM ============================================================
set "GH_USER="
set "GH_REPO="
set "GH_BRANCH="
if exist "%CFG_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%a in ("%CFG_FILE%") do (
    if /i "%%a"=="user"   set "GH_USER=%%b"
    if /i "%%a"=="repo"   set "GH_REPO=%%b"
    if /i "%%a"=="branch" set "GH_BRANCH=%%b"
  )
)

if "%GH_USER%"=="" (
  set "ORIGIN_URL="
  for /f "delims=" %%u in ('git remote get-url origin 2^>nul') do set "ORIGIN_URL=%%u"
  if not "!ORIGIN_URL!"=="" (
    for /f "tokens=3,4 delims=/: " %%a in ("!ORIGIN_URL!") do (
      set "GH_USER=%%a"
      set "GH_REPO=%%b"
    )
    set "GH_REPO=!GH_REPO:.git=!"
    echo !GH_USER!| findstr /r /c:"^[0-9A-Za-z][0-9A-Za-z-]*$" >nul
    if errorlevel 1 (
      echo   [i] آدرس remote فعلی قابل تشخیص نبود؛ مقدار پیش‌فرض استفاده می‌شود.
      set "GH_USER="
      set "GH_REPO="
    ) else (
      echo   [i] از remote فعلی خوانده شد: !GH_USER!/!GH_REPO!
    )
  )
)

REM اعتبارسنجی مقادیر: مقدار نامعتبر یا شبه‌متغیر نادیده گرفته می‌شود
if not "!GH_USER!"=="" (
  echo !GH_USER!| findstr /r /c:"^[0-9A-Za-z][0-9A-Za-z-]*$" >nul
  if errorlevel 1 set "GH_USER="
)
if not "!GH_REPO!"=="" (
  echo !GH_REPO!| findstr /r /c:"^[0-9A-Za-z._-][0-9A-Za-z._-]*$" >nul
  if errorlevel 1 set "GH_REPO="
  if /i "!GH_REPO!"=="GH_REPO" set "GH_REPO="
  if /i "!GH_REPO!"=="REPO" set "GH_REPO="
  if /i "!GH_REPO!"=="NAME" set "GH_REPO="
)
if not "!GH_BRANCH!"=="" (
  echo !GH_BRANCH!| findstr /r /c:"^[0-9A-Za-z._/-][0-9A-Za-z._/-]*$" >nul
  if errorlevel 1 set "GH_BRANCH="
  if /i "!GH_BRANCH!"=="GH_BRANCH" set "GH_BRANCH="
)

if "!GH_USER!"=="" set "GH_USER=%DEF_USER%"
if "!GH_REPO!"=="" set "GH_REPO=%DEF_REPO%"
if "!GH_BRANCH!"=="" set "GH_BRANCH=%DEF_BRANCH%"

if not "%NONSTOP%"=="" goto :cfg_ready
if exist "%CFG_FILE%" (
  echo   [3/8] تنظیمات ذخیره‌شده: %GH_USER%/%GH_REPO%  شاخه %GH_BRANCH%
  echo         برای تغییر، دستور git-push.bat reset را اجرا کنید.
  goto :cfg_ready
)

echo   [3/8] مقصد ارسال روی گیت‌هاب:
set "IN="
set /p "IN=        نام کاربری گیت‌هاب [%GH_USER%]: "
if not "%IN%"=="" set "GH_USER=%IN%"
set "IN="
set /p "IN=        نام مخزن [%GH_REPO%]: "
if not "%IN%"=="" set "GH_REPO=%IN%"
set "IN="
set /p "IN=        نام شاخه [%GH_BRANCH%]: "
if not "%IN%"=="" set "GH_BRANCH=%IN%"

:cfg_ready
set "REMOTE_URL=https://github.com/%GH_USER%/%GH_REPO%.git"

REM ============================================================
REM  4) گرفتن توکن گیت‌هاب
REM ============================================================
set "GH_TOKEN="
if not "%GITHUB_TOKEN%"=="" (
  set "GH_TOKEN=%GITHUB_TOKEN%"
  echo   [4/8] توکن از متغیر محیطی GITHUB_TOKEN خوانده شد.
  goto :token_ready
)

if exist "%TOK_FILE%" (
  echo   [4/8] خواندن توکن ذخیره‌شده ...
  call :load_token
  if not "!GH_TOKEN!"=="" (
    echo         توکن رمزنگاری‌شده‌ی ویندوز خوانده شد.
    goto :token_ready
  )
  echo         توکن ذخیره‌شده خوانده نشد؛ دوباره وارد کنید.
)

echo   [4/8] توکن گیت‌هاب لازم است.
echo:
echo         ساخت توکن در سایت گیت‌هاب:
echo           Settings - Developer settings - Personal access tokens
echo           Tokens classic - اسکوپ لازم: repo
echo:
call :ask_token
if "!GH_TOKEN!"=="" (
  echo   [X] بدون توکن امکان ارسال وجود ندارد.
  goto :fail
)

:token_ready
set "AUTH_URL=https://!GH_USER!:!GH_TOKEN!@github.com/!GH_USER!/!GH_REPO!.git"

REM ============================================================
REM  5) بررسی وجود مخزن مقصد روی گیت‌هاب
REM ============================================================
echo   [5/8] بررسی مخزن مقصد روی گیت‌هاب ...

REM شناسایی حساب واقعی صاحب توکن
set "TOKEN_LOGIN="
for /f "usebackq delims=" %%l in (`%PSH% "%TLS% try{ (Invoke-RestMethod -Uri 'https://api.github.com/user' -Headers @{'User-Agent'='sarrafi';Authorization='token %GH_TOKEN%'} -ErrorAction Stop).login } catch { '' }" 2^>nul`) do set "TOKEN_LOGIN=%%l"
set "TL_OK="
echo !TOKEN_LOGIN!| findstr /r /c:"^[0-9A-Za-z][0-9A-Za-z-]*$" >nul
if not errorlevel 1 set "TL_OK=1"
if not defined TL_OK set "TOKEN_LOGIN="
if not "!TOKEN_LOGIN!"=="" echo         حساب صاحب توکن: !TOKEN_LOGIN!

REM اعتبارسنجی نام کاربری: گیت‌هاب نقطه و زیرخط و فاصله نمی‌پذیرد
set "BADUSER="
echo !GH_USER!| findstr /r /c:"[._ ]" >nul
if not errorlevel 1 set "BADUSER=1"
echo !GH_USER!| findstr /r /c:"^[0-9A-Za-z][0-9A-Za-z-]*$" >nul
if errorlevel 1 set "BADUSER=1"
if defined BADUSER (
  echo         [i] نام کاربری «!GH_USER!» نامعتبر است؛ گیت‌هاب نقطه و زیرخط و فاصله نمی‌پذیرد.
  if not "!TOKEN_LOGIN!"=="" (
    set "GH_USER=!TOKEN_LOGIN!"
    set "FIXED=1"
    echo             نام کاربری از روی توکن اصلاح شد: !GH_USER!
  ) else (
    echo             دستور git-push.bat reset را اجرا و مقادیر را از نو وارد کنید.
    goto :fail
  )
)

call :api_get repos/!GH_USER!/!GH_REPO!
if "!API_MSG!"=="EXISTS" (
  echo         [OK] مخزن !GH_USER!/!GH_REPO! در دسترس است.
  goto :repo_ready
)

REM اگر حساب توکن متفاوت است، همان را هم بررسی کن
if not "!TOKEN_LOGIN!"=="" (
  if /i not "!GH_USER!"=="!TOKEN_LOGIN!" (
    echo         مخزن زیر !GH_USER! پیدا نشد؛ بررسی حساب صاحب توکن ...
    call :api_get repos/!TOKEN_LOGIN!/!GH_REPO!
    if "!API_MSG!"=="EXISTS" (
      set "GH_USER=!TOKEN_LOGIN!"
      set "FIXED=1"
      echo         [OK] مخزن در حساب !GH_USER! پیدا شد و آدرس اصلاح شد.
      goto :repo_ready
    )
  )
)

echo         مخزن «!GH_USER!/!GH_REPO!» روی گیت‌هاب پیدا نشد.
if not "%NONSTOP%"=="" goto :do_create
set "MK="
set /p "MK=        مخزن خصوصی با همین نام ساخته شود؟ [Y/n]: "
if /i "!MK!"=="n" (
  echo             لغو شد. برای تغییر مقصد: git-push.bat reset
  goto :fail
)

:do_create
echo         در حال ساخت مخزن ...
call :api_create
if "!API_MSG!"=="OK" (
  if not "!TOKEN_LOGIN!"=="" set "GH_USER=!TOKEN_LOGIN!"
  set "FIXED=1"
  echo         [OK] مخزن ساخته شد: !GH_USER!/!GH_REPO!
  goto :repo_ready
)
if "!API_MSG!"=="" (
  echo         [i] ساخت خودکار انجام نشد؛ بدون پاسخ از گیت‌هاب. اینترنت یا پاورشل را بررسی کنید.
) else (
  echo         [i] ساخت خودکار انجام نشد. کد خطا: !API_MSG!
)
if "!API_MSG!"=="ERR401" echo             توکن نامعتبر یا منقضی است؛ توکن تازه بسازید.
if "!API_MSG!"=="ERR403" echo             توکن اجازه‌ی ساخت مخزن ندارد؛ اسکوپ repo لازم است.
if "!API_MSG!"=="ERR422" echo             مخزنی با این نام از قبل وجود دارد؛ شاید در حساب دیگری.
echo             اگر مخزن ساخته شده مهم نیست؛ در غیر این صورت یکی بسازید: https://github.com/new

:repo_ready
set "REMOTE_URL=https://github.com/!GH_USER!/!GH_REPO!.git"
set "AUTH_URL=https://!GH_USER!:!GH_TOKEN!@github.com/!GH_USER!/!GH_REPO!.git"
echo         آدرس مقصد: !REMOTE_URL!

if defined FIXED (
  if exist "%CFG_FILE%" (
    > "%CFG_FILE%" echo user=!GH_USER!
    >>"%CFG_FILE%" echo repo=!GH_REPO!
    >>"%CFG_FILE%" echo branch=!GH_BRANCH!
    echo         [i] تنظیمات ذخیره‌شده برای اجراهای بعدی به‌روز شد.
  )
)

git remote | findstr /x /c:"origin" >nul 2>nul
if errorlevel 1 (
  git remote add origin "%REMOTE_URL%"
) else (
  git remote set-url origin "%REMOTE_URL%"
)

REM ============================================================
REM  6) هم‌سان‌سازی تاریخچه و ثبت تغییرات
REM ============================================================
if exist "app\web.py" (
  for /f "tokens=3 delims= " %%v in ('findstr /b /c:"VERSION = " app\web.py 2^>nul') do set "VER=%%~v"
)
if not "!VER!"=="" echo   [i] نسخه‌ی پروژه: !VER!

echo   [6/8] هم‌سان‌سازی با مخزن گیت و ثبت تغییرات ...
call :sync_history
call :do_commit

REM ============================================================
REM  7) ارسال به گیت‌هاب
REM ============================================================
echo   [7/8] ارسال به گیت‌هاب ...
call :do_push

if not "!RC!"=="0" (
  echo:
  echo         ارسال رد شد؛ یک‌بار دیگر هم‌سان‌سازی و تلاش مجدد ...
  call :sync_history
  call :do_commit
  call :do_push
)

if not "!RC!"=="0" (
  echo:
  echo         [i] ارسال معمولی ممکن نشد.
  echo             این حالت وقتی رخ می‌دهد که مخزن گیت تغییراتی داشته باشد
  echo             که در این نسخه نیست؛ یا دسترسی توکن کافی نباشد.
  if "%NONSTOP%"=="" (
    echo             راه دیگر: نسخه‌ی این سیستم جایگزین نسخه‌ی روی گیت شود.
    set "F="
    set /p "F=        جایگزینی اجباری انجام شود؟ [y/N]: "
    if /i "!F!"=="y" call :do_force
  )
)

if not "!RC!"=="0" goto :fail

git update-ref "refs/remotes/origin/%GH_BRANCH%" HEAD >nul 2>nul
git config "branch.%GH_BRANCH%.remote" "origin" >nul 2>nul
git config "branch.%GH_BRANCH%.merge" "refs/heads/%GH_BRANCH%" >nul 2>nul

REM ============================================================
REM  8) تگ نسخه و آپلود اختیاری فایل نصبی
REM ============================================================
if "!VER!"=="" (
  echo   [8/8] نسخه‌ی پروژه پیدا نشد؛ از تگ صرف‌نظر شد.
  goto :asset
)

set "HEAD_SHA="
for /f "delims=" %%h in ('git rev-parse --verify HEAD 2^>nul') do set "HEAD_SHA=%%h"
set "TAG_SHA="
for /f "delims=" %%h in ('git rev-parse --verify "refs/tags/v!VER!" 2^>nul') do set "TAG_SHA=%%h"

if "!TAG_SHA!"=="" (
  git tag "v!VER!" >> "%TMP_LOG%" 2>&1
  echo         تگ v!VER! روی کامیت فعلی ساخته شد.
) else (
  if /i not "!TAG_SHA!"=="!HEAD_SHA!" (
    git tag -d "v!VER!" >> "%TMP_LOG%" 2>&1
    git tag "v!VER!" >> "%TMP_LOG%" 2>&1
    echo         [i] تگ v!VER! به کامیت فعلی منتقل شد.
  ) else (
    echo         [i] تگ v!VER! از قبل روی همین کامیت است.
  )
)

REM تگ روی گیت از قبل هست؟ (بررسی پیش از ارسال تا پیام تکراری/خطای بی‌مورد ندهیم)
set "TAG_REMOTE="
for /f "delims=" %%t in ('git ls-remote --tags "%AUTH_URL%" "refs/tags/v!VER!" 2^>nul') do set "TAG_REMOTE=1"

if not defined TAG_REMOTE (
  call :do_push_tag
  if "!RC!"=="0" (
    echo   [8/8] تگ v!VER! برای نخستین بار ارسال شد.
  ) else (
    echo         ارسال تگ ناموفق بود؛ تلاش با جایگزینی ...
    call :do_push_tag_force
    if "!RC!"=="0" (echo   [8/8] تگ v!VER! ارسال شد.) else (echo   [8/8] ارسال تگ انجام نشد — فایل‌ها ارسال شده‌اند.)
  )
) else (
  echo         تگ v!VER! روی گیت موجود است؛ به‌روزرسانی روی کامیت فعلی ...
  call :do_push_tag_force
  if "!RC!"=="0" (
    echo   [8/8] تگ v!VER! به‌روزرسانی شد.
  ) else (
    echo   [8/8] به‌روزرسانی تگ انجام نشد — خودِ فایل‌ها ارسال شده‌اند.
  )
)

:asset
call :maybe_asset

echo:
echo +------------------------------------------------------------+
echo ^|                       پایان - موفق                         ^|
echo +------------------------------------------------------------+
echo:
echo   مخزن: %REMOTE_URL%
echo   شاخه: %GH_BRANCH%   ^|   نسخه: %VER%
echo:
if exist "%TOK_FILE%" (
  echo   [i] اجرای بعدی خودکار است؛ فقط همین فایل را دوباره باز کنید.
  echo       پاک‌کردن توکن ذخیره‌شده: git-push.bat reset
) else (
  echo   [i] توکن ذخیره نشد؛ اجرای بعدی دوباره توکن می‌پرسد.
)
echo:
start "" "https://github.com/%GH_USER%/%GH_REPO%"
goto :done

REM ============================================================
REM                       زیربرنامه‌ها
REM ============================================================

:sync_history
REM تاریخچه‌ی محلی را با مخزن گیت هم‌سو می‌کند تا ارسال بدون تعارض انجام شود.
REM فایل‌های کاری هرگز پاک یا بازنویسی نمی‌شوند؛ فقط پایه‌ی تاریخچه تنظیم می‌شود.
set "KEPT=0"
git fetch "%AUTH_URL%" "%GH_BRANCH%" > "%TMP_LOG%" 2>&1
if not "!ERRORLEVEL!"=="0" goto :eof

set "REMOTE_TIP="
for /f "delims=" %%h in ('git rev-parse --verify FETCH_HEAD 2^>nul') do set "REMOTE_TIP=%%h"
if "!REMOTE_TIP!"=="" goto :eof

set "LOCAL_TIP="
for /f "delims=" %%h in ('git rev-parse --verify HEAD 2^>nul') do set "LOCAL_TIP=%%h"
if /i "!REMOTE_TIP!"=="!LOCAL_TIP!" goto :eof

git merge-base "!LOCAL_TIP!" "!REMOTE_TIP!" >nul 2>nul
if not "!ERRORLEVEL!"=="0" goto :sync_align

echo         [i] تاریخچه مشترک است؛ تغییرات گیت ادغام می‌شود ...
git pull --rebase "%AUTH_URL%" "%GH_BRANCH%" > "%TMP_LOG%" 2>&1
if "!ERRORLEVEL!"=="0" (
  echo         [i] ادغام انجام شد.
  goto :eof
)
git rebase --abort >nul 2>nul
git merge --abort >nul 2>nul
echo         [i] ادغام ممکن نبود؛ تاریخچه هم‌سو می‌شود. فایل‌های شما دست‌نخورده می‌مانند.

:sync_align
git reset --soft "!REMOTE_TIP!" >nul 2>nul
git read-tree "!REMOTE_TIP!" >nul 2>nul
for /f "delims=" %%p in ('git ls-tree -r --name-only "!REMOTE_TIP!" 2^>nul') do (
  if not exist "%%p" (
    git checkout "!REMOTE_TIP!" -- "%%p" >nul 2>nul
    set /a KEPT+=1
  )
)
echo         [i] تاریخچه با مخزن گیت هم‌سو شد؛ کامیت‌های قبلی گیت حفظ می‌شوند.
if not "!KEPT!"=="0" echo         [i] !KEPT! فایل که فقط روی گیت بود، حفظ شد.
goto :eof

:do_commit
git add -A
set "HASCHANGE="
for /f "delims=" %%s in ('git status --porcelain 2^>nul') do set "HASCHANGE=1"
if not defined HASCHANGE (
  echo         [i] تغییر جدیدی برای ثبت نیست.
  goto :eof
)
set "MSG="
if "%NONSTOP%"=="" set /p "MSG=        پیام کامیت، خالی یعنی خودکار: "
if "!MSG!"=="" (
  set "MSG=update: sync files"
  if not "!VER!"=="" set "MSG=update: v!VER! - sync files"
)
git commit -q -m "!MSG!"
echo         [OK] ثبت شد: !MSG!
goto :eof

:load_token
for /f "usebackq delims=" %%t in (`%PSH% "$p=(Get-Content -LiteralPath '%TOK_FILE%' -Raw).Trim(); $s=ConvertTo-SecureString $p; $b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)" 2^>nul`) do set "GH_TOKEN=%%t"
goto :eof

:ask_token
set "GH_TOKEN="
for /f "usebackq delims=" %%t in (`%PSH% "$s=Read-Host -AsSecureString '        توکن را بچسبانید و Enter بزنید'; $b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)" 2^>nul`) do set "GH_TOKEN=%%t"
if "!GH_TOKEN!"=="" (
  echo         [i] ورودی مخفی در دسترس نبود؛ توکن نمایان تایپ می‌شود.
  set /p "GH_TOKEN=        توکن: "
)
if "!GH_TOKEN!"=="" goto :eof
if not "%NONSTOP%"=="" goto :eof

set "SV="
set /p "SV=        برای اجراهای بعدی ذخیره شود؟ رمزنگاری‌شده در پروفایل ویندوز [Y/n]: "
if /i "!SV!"=="n" goto :eof
if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>nul
%PSH% "$s=ConvertTo-SecureString '%GH_TOKEN%' -AsPlainText -Force; ConvertFrom-SecureString $s | Set-Content -LiteralPath '%TOK_FILE%' -NoNewline" >nul 2>nul
if exist "%TOK_FILE%" (
  > "%CFG_FILE%" echo user=!GH_USER!
  >>"%CFG_FILE%" echo repo=!GH_REPO!
  >>"%CFG_FILE%" echo branch=!GH_BRANCH!
  echo         [OK] توکن و تنظیمات ذخیره شد. اجرای بعدی: یک کلیک.
)
goto :eof

:api_get
REM وجود یک مسیر روی API گیت‌هاب — %1 مسیر، نتیجه در API_MSG
set "API_MSG="
for /f "usebackq delims=" %%r in (`%PSH% "%TLS% try{ Invoke-RestMethod -Uri 'https://api.github.com/%1' -Headers @{'User-Agent'='sarrafi';Authorization='token %GH_TOKEN%'} -ErrorAction Stop | Out-Null; 'EXISTS' } catch { $c=$_.Exception.Response.StatusCode.value__; if($c){'ERR'+$c}else{'ERR0'} }" 2^>nul`) do set "API_MSG=%%r"
goto :eof

:api_create
REM ساخت مخزن خصوصی زیر حساب صاحب توکن — نتیجه در API_MSG
set "API_MSG="
for /f "usebackq delims=" %%r in (`%PSH% "%TLS% $b=@{name='%GH_REPO%';private=$true} | ConvertTo-Json; try{ Invoke-RestMethod -Uri 'https://api.github.com/user/repos' -Method Post -Headers @{'User-Agent'='sarrafi';Authorization='token %GH_TOKEN%'} -ContentType 'application/json' -Body $b -ErrorAction Stop | Out-Null; 'OK' } catch { $c=$_.Exception.Response.StatusCode.value__; if($c){'ERR'+$c}else{'ERR0'} }" 2^>nul`) do set "API_MSG=%%r"
goto :eof

:do_push
set "RC=1"
git -c credential.helper= push "%AUTH_URL%" "%GH_BRANCH%:%GH_BRANCH%" > "%TMP_LOG%" 2>&1
set "RC=!ERRORLEVEL!"
call :show_log
goto :eof

:do_force
set "RC=1"
git -c credential.helper= push --force "%AUTH_URL%" "%GH_BRANCH%" > "%TMP_LOG%" 2>&1
set "RC=!ERRORLEVEL!"
call :show_log
goto :eof

:do_push_tag
set "RC=1"
git -c credential.helper= push "%AUTH_URL%" "refs/tags/v!VER!" > "%TMP_LOG%" 2>&1
set "RC=!ERRORLEVEL!"
call :show_log
goto :eof

:do_push_tag_force
set "RC=1"
git -c credential.helper= push --force "%AUTH_URL%" "refs/tags/v!VER!" > "%TMP_LOG%" 2>&1
set "RC=!ERRORLEVEL!"
call :show_log
goto :eof

:show_log
if not exist "%TMP_LOG%" goto :eof
%PSH% "(Get-Content -LiteralPath '%TMP_LOG%' -Raw) -replace [regex]::Escape('%GH_TOKEN%'),'****' | Write-Host -NoNewline" 2>nul
if not "!RC!"=="0" echo         [X] دستور گیت با کد !RC! تمام شد.
goto :eof

:maybe_asset
REM جستجوی بسته‌ی نصبی در پوشه‌ی پروژه و پوشه‌ی والد
set "ART="
for %%d in ("%~dp0." "%~dp0..") do (
  if not defined ART (
    for /f "delims=" %%f in ('dir /b /o-d "%%~fd\sarrafi-*.tar.gz" 2^>nul') do (
      if not defined ART set "ART=%%~fd\%%f"
    )
  )
)
if not defined ART goto :eof
if not exist "%ART%" goto :eof
if not "%NONSTOP%"=="" goto :eof
set "U="
set /p "U=        فایل بسته به‌عنوان دارایی نسخه v!VER! آپلود شود؟ [y/N]: "
if /i not "!U!"=="y" goto :eof
echo         در حال آپلود %ART% ...
%PSH% "%TLS% $h=@{'User-Agent'='sarrafi';Authorization='token %GH_TOKEN%'}; try{ $r=Invoke-RestMethod -Uri 'https://api.github.com/repos/%GH_USER%/%GH_REPO%/releases/tags/v%VER%' -Headers $h -ErrorAction Stop } catch { $b=@{tag_name='v%VER%';name='v%VER%'} | ConvertTo-Json; $r=Invoke-RestMethod -Uri 'https://api.github.com/repos/%GH_USER%/%GH_REPO%/releases' -Method Post -Headers $h -ContentType 'application/json' -Body $b -ErrorAction Stop }; $u='https://uploads.github.com/repos/%GH_USER%/%GH_REPO%/releases/'+$r.id+'/assets?name=%ART%'; Invoke-RestMethod -Uri $u -Method Post -Headers $h -ContentType 'application/gzip' -InFile '%ART%' -ErrorAction Stop | Out-Null; exit 0" >nul 2>nul
if errorlevel 1 (
  echo         [i] آپلود انجام نشد؛ فایل ممکن است بزرگ باشد یا توکن اجازه نداشته باشد.
) else (
  echo         [OK] فایل در صفحه‌ی Releases گیت‌هاب قرار گرفت.
)
goto :eof

:fail
echo:
echo +------------------------------------------------------------+
echo ^|                      پایان - با خطا                        ^|
echo +------------------------------------------------------------+
echo:
echo   راهنمای رفع مشکل: docs\push-to-github.md
if exist "%TMP_LOG%" del /q "%TMP_LOG%" >nul 2>nul
endlocal
pause
exit /b 1

:done
if exist "%TMP_LOG%" del /q "%TMP_LOG%" >nul 2>nul
echo %cmdcmdline% | findstr /i /c:"%~nx0" >nul 2>nul
if not errorlevel 1 pause
endlocal
exit /b 0
