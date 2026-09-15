@echo off
chcp 65001 >nul
setlocal EnableExtensions

REM ============================================================
REM  Sarrafi - Currency Exchange Management System
REM  One-click Windows launcher / bootstrapper (online-first).
REM
REM  Every step is printed on screen so you always know what the
REM  system is doing: find Python -> install if missing -> install
REM  each library (skip if present) -> optional Tesseract OCR ->
REM  start server -> open browser.
REM
REM  Usage:  run.bat [port]
REM ============================================================

title Sarrafi - Currency Exchange Manager

REM --- Configuration ---
set "SCRIPT_DIR=%~dp0"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=%SARRAFI_PORT%"
if "%PORT%"=="" set "PORT=8000"
set "BROWSER_URL=http://localhost:%PORT%"

cd /d "%SCRIPT_DIR%"

echo:
echo +------------------------------------------------------------+
echo ^|            Sarrafi - Currency Exchange Manager             ^|
echo ^|    سامانه‌ی مدیریت خرید و فروش ارز  -  راه‌انداز ویندوز     ^|
echo +------------------------------------------------------------+
echo:
echo   [i] این پنجره همه‌ی مراحل را قدم‌به‌قدم نشان می‌دهد:
echo       1) پیدا کردن پایتون  2) نصب در صورت نبود  3) نصب کتابخانه‌ها
echo       4) موتور OCR (اختیاری)  5) اجرای سرور  6) باز کردن مرورگر
echo:

REM ============================================================
REM  1) Find a working Python interpreter
REM ============================================================
call :log "STEP 1/6" "بررسی وجود پایتون روی سیستم ..."
call :find_python

if defined PYTHON_EXE (
    echo   [OK] پایتون پیدا شد:
    "%PYTHON_EXE%" --version
    echo:
) else (
    echo   [!] پایتونی پیدا نشد - در ادامه به صورت خودکار نصب می‌شود.
    echo:
)

REM ============================================================
REM  2) If missing, download and install Python
REM ============================================================
if not defined PYTHON_EXE (
    call :log "STEP 2/6" "دانلود و نصب خودکار پایتون ..."
    call :install_python
    call :find_python
)

if not defined PYTHON_EXE (
    echo   [ERROR] نصب خودکار پایتون موفق نبود.
    echo           لطفا Python 3.9+ را از این آدرس نصب کنید:
    echo           https://www.python.org/downloads/
    echo           و در هنگام نصب، گزینه‌ی "Add Python to PATH" را فعال کنید.
    echo:
    pause
    exit /b 1
)

echo   [OK] پایتون آماده است:
"%PYTHON_EXE%" --version
echo:

REM ============================================================
REM  3) Bootstrap pip if needed
REM ============================================================
call :log "STEP 3/6" "بررسی pip (نصب‌کننده‌ی بسته‌های پایتون) ..."
"%PYTHON_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo   [..] pip پیدا نشد - در حال نصب آن از python.org ...
    call :download "https://bootstrap.pypa.io/get-pip.py" "%TEMP%\sarrafi-get-pip.py"
    if not errorlevel 1 "%PYTHON_EXE%" "%TEMP%\sarrafi-get-pip.py" --disable-pip-version-check -q
    if exist "%TEMP%\sarrafi-get-pip.py" del "%TEMP%\sarrafi-get-pip.py"
)
echo   [OK] pip آماده است.
echo:

REM ============================================================
REM  4) Required libraries (skip if already installed)
REM ============================================================
call :log "STEP 4/6" "نصب کتابخانه‌های لازم (از PyPI؛ نصب‌شده‌ها رد می‌شوند) ..."
echo:
echo   کتابخانه‌های زیر یکی‌یکی بررسی و در صورت نیاز نصب می‌شوند:
call :ensure_pkg reportlab reportlab
call :ensure_pkg arabic_reshaper arabic-reshaper
call :ensure_pkg bidi python-bidi
call :ensure_pkg PIL pillow
call :ensure_pkg numpy numpy
call :ensure_pkg cv2 opencv-python-headless
call :ensure_pkg pytesseract pytesseract
call :ensure_pkg psycopg2 psycopg2-binary
call :ensure_pkg openpyxl openpyxl
echo:
echo   [i] وضعیت نهایی امکانات نصب‌شده:
"%PYTHON_EXE%" "%SCRIPT_DIR%tools\check_pkg.py"
echo:

REM ============================================================
REM  5) OCR engine (Tesseract) - best effort, never blocks startup
REM ============================================================
call :log "STEP 5/6" "بررسی موتور OCR (تشخیص سریال اسکناس) ..."
call :ensure_tesseract

REM ============================================================
REM  6) Start the server and open the browser
REM ============================================================
call :log "STEP 6/6" "اجرای سرور صرافی ..."
echo:
echo   +------------------------------------------------------------+
echo   ^|   سرور در حال اجراست                                        ^|
echo   ^|   آدرس:  %BROWSER_URL%                                      ^|
echo   ^|   پورت:  %PORT%                                             ^|
echo   +------------------------------------------------------------+
echo:
echo   [i] در اولین اجرا، دیتابیس دمو به‌صورت خودکار ساخته می‌شود.
echo   [i] حساب‌های دمو:   root/root123   admin/admin123
echo   [i] برای توقف سرور، Ctrl+C را بزنید.
echo:

start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:%PORT%"

"%PYTHON_EXE%" run.py --port %PORT%

echo:
echo سرور متوقف شد. برای بستن این پنجره یک کلید بزنید.
pause
endlocal
exit /b 0


REM ============================================================
REM  Subroutines
REM ============================================================

REM ------------------------------------------------------------
REM Print a step banner: %1 = step label, %2 = description
REM ------------------------------------------------------------
:log
echo:
echo   +------------------------------------------------------------+
echo   ^|   %~1  ^|  %~2
echo   +------------------------------------------------------------+
exit /b 0


REM ------------------------------------------------------------
REM Resolve a working python.exe into PYTHON_EXE
REM ------------------------------------------------------------
:find_python
set "PYTHON_EXE="

REM (a) the py launcher -> resolve the real interpreter path
set "PYTMP=%TEMP%\sarrafi_py_path.txt"
if exist "%PYTMP%" del "%PYTMP%" >nul 2>nul
py -3 -c "import sys;print(sys.executable)" >"%PYTMP%" 2>nul
if exist "%PYTMP%" (
    set /p PYTHON_EXE=<"%PYTMP%"
    del "%PYTMP%" >nul 2>nul
)
call :try_py "%PYTHON_EXE%"

REM (b) python / python3 on PATH
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE call :try_py "%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python3 2^>nul') do if not defined PYTHON_EXE call :try_py "%%P"

REM (c) common per-user install locations
if not defined PYTHON_EXE for %%V in (314 313 312 311 310 39) do if not defined PYTHON_EXE call :try_py "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"

REM (d) any per-user Python3* folder
if not defined PYTHON_EXE for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PYTHON_EXE call :try_py "%%D\python.exe"

REM (e) any machine-wide Python3* folder
if not defined PYTHON_EXE for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PYTHON_EXE call :try_py "%%D\python.exe"
if not defined PYTHON_EXE for /d %%D in ("C:\Python3*") do if not defined PYTHON_EXE call :try_py "%%D\python.exe"
exit /b 0


REM ------------------------------------------------------------
REM Test a candidate interpreter: exists, runs, version >= 3.9.
REM On success sets PYTHON_EXE to the full path.
REM ------------------------------------------------------------
:try_py
if "%~1"=="" exit /b 1
if not exist "%~1" exit /b 1
set "PYVERFILE=%TEMP%\sarrafi_pyver.txt"
"%~1" -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" >"%PYVERFILE%" 2>nul
if not exist "%PYVERFILE%" exit /b 1
set "PYVER="
set /p PYVER=<"%PYVERFILE%"
del "%PYVERFILE%" >nul 2>nul
if "%PYVER%"=="" exit /b 1
if %PYVER% LSS 309 exit /b 1
set "PYTHON_EXE=%~1"
exit /b 0


REM ------------------------------------------------------------
REM Download and silently install Python (per-user)
REM ------------------------------------------------------------
:install_python
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 set "ARCH=x86"

set "PYVER=3.12.8"
set "PYDIR=Python312"
set "PYINST=python-%PYVER%-amd64.exe"
if "%ARCH%"=="x86" set "PYINST=python-%PYVER%.exe"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/%PYINST%"

echo   [..] در حال دانلود پایتون %PYVER% (%ARCH%) از python.org ...
echo        (حجم حدود ۲۵ مگابایت - چند دقیقه طول می‌کشد)
call :download "%PYURL%" "%TEMP%\%PYINST%"
if errorlevel 1 (
    echo   [ERROR] دانلود پایتون ممکن نشد. اینترنت را بررسی کنید یا پایتون
    echo           را دستی از https://www.python.org/downloads/ نصب کنید.
    exit /b 1
)

echo   [..] در حال نصب بی‌صدای پایتون (برای همین کاربر، بدون نیاز به ادمین) ...
echo        این مرحله ممکن است چند دقیقه طول بکشد؛ لطفا صبر کنید ...
start /wait "" "%TEMP%\%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 Include_doc=0 Shortcuts=0
if exist "%TEMP%\%PYINST%" del "%TEMP%\%PYINST%"

set "PYTHON_EXE="
call :try_py "%LOCALAPPDATA%\Programs\Python\%PYDIR%\python.exe"
if not defined PYTHON_EXE call :try_py "%ProgramFiles%\Python\%PYDIR%\python.exe"
exit /b 0


REM ------------------------------------------------------------
REM Download helper.  %1 = URL, %2 = absolute output path.
REM Tries PowerShell, then curl.exe, then bitsadmin.
REM ------------------------------------------------------------
:download
set "DL_URL=%~1"
set "DL_OUT=%~2"
if exist "%DL_OUT%" del "%DL_OUT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}; Invoke-WebRequest -UseBasicParsing -UserAgent 'Mozilla/5.0' -Uri '%DL_URL%' -OutFile '%DL_OUT%'"
if not errorlevel 1 if exist "%DL_OUT%" exit /b 0

if exist "%DL_OUT%" del "%DL_OUT%"
where curl >nul 2>nul
if not errorlevel 1 (
    curl.exe -L --fail --silent --show-error -o "%DL_OUT%" "%DL_URL%"
    if not errorlevel 1 if exist "%DL_OUT%" exit /b 0
    if exist "%DL_OUT%" del "%DL_OUT%"
)

where bitsadmin >nul 2>nul
if not errorlevel 1 (
    bitsadmin /transfer "sarrafi_dl" /download /priority normal "%DL_URL%" "%DL_OUT%" >nul 2>nul
    if not errorlevel 1 if exist "%DL_OUT%" exit /b 0
    if exist "%DL_OUT%" del "%DL_OUT%"
)
exit /b 1


REM ------------------------------------------------------------
REM Install one library.  %1 = import module, %2 = pip package.
REM Prints progress; skip if already installed.
REM ------------------------------------------------------------
:ensure_pkg
"%PYTHON_EXE%" "%SCRIPT_DIR%tools\check_pkg.py" %~1 >nul 2>nul
if not errorlevel 1 (
    echo        [skip] %~2 - از قبل نصب شده است
    exit /b 0
)
echo        [..] %~2 - در حال دانلود و نصب از PyPI ...
"%PYTHON_EXE%" -m pip install --disable-pip-version-check --retries 2 --timeout 30 -q --index-url https://pypi.org/simple/ %~2 >nul 2>nul
"%PYTHON_EXE%" "%SCRIPT_DIR%tools\check_pkg.py" %~1 >nul 2>nul
if not errorlevel 1 (
    echo        [OK] %~2 - با موفقیت نصب شد
    exit /b 0
)
echo        [!!] %~2 - نصب نشد؛ قابلیت مربوطه غیرفعال می‌ماند
exit /b 0


REM ------------------------------------------------------------
REM Install the Tesseract OCR engine if missing (best effort).
REM ------------------------------------------------------------
:ensure_tesseract
where tesseract >nul 2>nul
if not errorlevel 1 (
    echo   [skip] Tesseract OCR - از قبل نصب شده است
    exit /b 0
)
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
    echo   [skip] Tesseract OCR - از قبل نصب شده است
    exit /b 0
)
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" (
    echo   [skip] Tesseract OCR - از قبل نصب شده است
    exit /b 0
)
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" (
    echo   [skip] Tesseract OCR - از قبل نصب شده است
    exit /b 0
)

set "TESS_INST=tesseract-ocr-w64-setup-5.4.0.20240606.exe"
set "TESS_URL=https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/%TESS_INST%"

echo   [..] Tesseract OCR پیدا نشد - در حال دانلود (حدود ۴۸ مگابایت) از GitHub ...
call :download "%TESS_URL%" "%TEMP%\%TESS_INST%"
if not exist "%TEMP%\%TESS_INST%" (
    echo   [!!] دانلود Tesseract ممکن نشد؛ تشخیص سریال با OCR غیرفعال می‌ماند.
    echo        می‌توانید بعدا از این آدرس نصب کنید:
    echo        https://github.com/UB-Mannheim/tesseract/wiki
    exit /b 0
)
echo   [..] در حال نصب Tesseract OCR ...
start /wait "" "%TEMP%\%TESS_INST%" /S
if exist "%TEMP%\%TESS_INST%" del "%TEMP%\%TESS_INST%"

where tesseract >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Tesseract OCR - نصب شد
    exit /b 0
)
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
    echo   [OK] Tesseract OCR - نصب شد
    exit /b 0
)
echo   [!!] نصب Tesseract تمام شد اما پیدا نشد - OCR شاید غیرفعال بماند
exit /b 0
