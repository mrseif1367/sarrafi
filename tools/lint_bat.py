#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لینتر فایل‌های batch پروژه (git-push.bat و run.bat)

چرا لازم است: در cmd، کاراکترهای خاص داخل متن echo اگر خط درون یک بلوک
`if ( ... )` یا `for ( ... )` باشد، بلوک را زودتر می‌بندند و خطاهایی مثل
`. was unexpected at this time.` یا `unexpected )` رخ می‌دهد.
همچنین این لینتر سلامت برچسب‌ها، توازن پرانتزها، کدگذاری و خط پایانی را بررسی می‌کند.

اجرا:  python3 tools/lint_bat.py [فایل ...]
خروج با کد ۱ = خطای مسدودکننده
"""
import os
import re
import sys

DANGEROUS = "()|&<>"          # کاراکترهایی که در متن echo داخل بلوک خطرناک‌اند
SCRIPTS = ["git-push.bat", "run.bat"]


def lint(path):
    errors, warnings, info = [], [], []
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()

    # --- ۱) کدگذاری و خط پایانی ---
    if raw.startswith("\ufeff"):
        errors.append("فایل BOM دارد (باید UTF-8 بدون BOM باشد تا chcp 65001 درست کار کند)")
    if "\r\n" not in raw:
        errors.append("خط پایانی CRLF نیست (فایل .bat روی ویندوز باید CRLF باشد)")
    if re.search(r"(?<!\r)\n", raw):
        errors.append("خط پایانی مخلوط است (LF تنها پیدا شد)")
    if raw.count('chcp 65001') == 0:
        warnings.append("chcp 65001 پیدا نشد (نمایش صحیح فارسی روی کنسول)")

    lines = raw.split("\r\n")
    labels, refs, depth = set(), [], 0

    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        low = s.lower()
        if s.startswith("::"):
            continue
        is_rem = low.startswith("rem ") or low == "rem"
        is_echo = low.startswith("echo") and not low.startswith("echo:") and not is_rem

        # --- ۲) متن echo داخل بلوک نباید کاراکتر خاص داشته باشد ---
        # نکته: | و & و < و > وقتی جداکننده‌ی دستور (لوله/ریدایرکت) باشند مجازند،
        # پس فقط «متنِ» echo — تا اولین جداکننده‌ی خارج از رشته — بررسی می‌شود.
        if is_echo and depth > 0:
            body = s[4:]
            inq2, esc2, text = False, False, []
            for ch in body:
                if esc2:
                    text.append(ch)
                    esc2 = False
                    continue
                if ch == "^":
                    esc2 = True
                    text.append(ch)
                    continue
                if ch == '"':
                    inq2 = not inq2
                    text.append(ch)
                    continue
                if not inq2 and ch in "|&<>":
                    break
                text.append(ch)
            bad = sorted({c for c in DANGEROUS if c in "".join(text)})
            if bad:
                errors.append(
                    f"L{i}: متن echo داخل بلوک دارای کاراکتر خطرناک {' '.join(bad)} است "
                    f"(بلوک را زودتر می‌بندد) → {s[:70]}"
                )
        # --- ۳) echo خالی: باید echo: باشد، نه echo. ---
        if low in ("echo.", "echo "):
            warnings.append(f"L{i}: برای خط خالی از «echo:» استفاده کنید")

        # --- ۴) برچسب‌ها و ارجاع‌ها ---
        if not is_echo and not is_rem:
            # --- ۴‑الف) غلط تایپی در بسته‌شدن متغیر ---
            for mm in re.finditer(r"![A-Za-z_]\w*%|%[A-Za-z_]\w*!", ln):
                errors.append(
                    f"L{i}: بسته‌شدن نادرست متغیر ({mm.group(0)}) — "
                    f"صحیح: !name! یا %name% → {s[:60]}"
                )
            if s.count("!") % 2 == 1:
                warnings.append(f"L{i}: تعداد علامت ! فرد است (احتمال جاافتادن بسته‌شدن)")

            m = re.match(r"^:([A-Za-z_][\w]*)$", s)
            if m:
                labels.add(m.group(1).lower())
                if m.group(1).lower() == "eof":
                    errors.append(f"L{i}: «:eof» یک برچسب رزروشده است")
            else:
                for mm in re.finditer(r"\b(?:goto|call)\s+:([A-Za-z_]\w*)", ln, re.I):
                    refs.append((mm.group(1).lower(), i))
                # برچسب‌ها نباید داخل بلوک باشند
                if depth > 0 and re.match(r"^:[A-Za-z_]", s):
                    errors.append(f"L{i}: برچسب داخل بلوک پرانتزی تعریف شده است")

            # --- ۵) توازن پرانتزها (خارج از رشته و با احترام به ^) ---
            inq = esc = False
            for ch in ln:
                if esc:
                    esc = False
                    continue
                if ch == "^":
                    esc = True
                    continue
                if ch == '"':
                    inq = not inq
                    continue
                if inq:
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth < 0:
                        errors.append(f"L{i}: پرانتز بسته اضافه")
                        depth = 0

    if depth != 0:
        errors.append(f"در پایان فایل {depth} پرانتز بسته‌نشده باقی مانده است")
    for name, i in refs:
        if name != "eof" and name not in labels:
            errors.append(f"L{i}: برچسب :{name} تعریف نشده است")
    for name in labels:
        if not any(r == name for r, _ in refs):
            info.append(f"برچسب :{name} استفاده نشده است")

    # --- ۶) بررسی‌های کلی ---
    if "setlocal" in raw.lower() and "endlocal" not in raw.lower():
        warnings.append("setlocal بدون endlocal")
    if "EnableDelayedExpansion" in raw and "!" not in raw:
        info.append("EnableDelayedExpansion فعال است ولی از ! استفاده نشده")
    return errors, warnings, info


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = argv[1:] or [os.path.join(root, f) for f in SCRIPTS if os.path.exists(os.path.join(root, f))]
    bad = 0
    for f in files:
        if not os.path.exists(f):
            continue
        errors, warnings, info = lint(f)
        name = os.path.basename(f)
        print(f"\n=== {name} ===")
        for e in errors:
            print(f"  [خطا] {e}")
        for w in warnings:
            print(f"  [هشدار] {w}")
        for i in info:
            print(f"  [اطلاع] {i}")
        if not (errors or warnings or info):
            print("  سالم — هیچ ایرادی پیدا نشد")
        elif not errors:
            print("  تأیید شد — خطای مسدودکننده وجود ندارد")
        bad += len(errors)
    print()
    if bad:
        print(f"❌ مجموع {bad} خطای مسدودکننده")
        return 1
    print("✅ همه‌ی فایل‌های batch سالم هستند")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
