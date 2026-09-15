#!/usr/bin/env bash
# ============================================================
#  اسکریپت ارسال پروژه به GitHub
#  استفاده:  bash git-push.sh
#  توکن هنگام تایپ نمایش داده نمی‌شود و روی دیسک ذخیره نمی‌شود.
# ============================================================
set -euo pipefail

USER_NAME="${SARRAFI_GH_USER:-mrseif1367}"
REPO="${SARRAFI_GH_REPO:-sarrafi}"
REMOTE_URL="https://github.com/${USER_NAME}/${REPO}.git"
BRANCH="${SARRAFI_GH_BRANCH:-main}"

echo "============================================================"
echo "  ارسال پروژه صرافی به GitHub"
echo "  مقصد: $REMOTE_URL   (شاخه: $BRANCH)"
echo "============================================================"

# --- بررسی گیت ---
if ! command -v git >/dev/null 2>&1; then
  echo "❌ گیت نصب نیست. اول Git را نصب کنید."
  exit 1
fi
if [ ! -d .git ]; then
  echo "❌ این پوشه مخزن گیت نیست (دستور را از ریشهٔ پروژه اجرا کنید)."
  exit 1
fi

# --- هویت گیت (اگر تنظیم نشده باشد، محلی تنظیم می‌شود) ---
if ! git config user.email >/dev/null 2>&1 || [ -z "$(git config user.email || true)" ]; then
  git config user.name "${USER_NAME}"
  git config user.email "${USER_NAME}@users.noreply.github.com"
  echo "ℹ️  هویت گیت به‌صورت محلی تنظیم شد: ${USER_NAME}"
fi

# --- بررسی کامیت‌های باقی‌مانده ---
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  تغییرات ذخیره‌نشده وجود دارد:"
  git status --short
  read -r -p "   همه را کامیت کنم؟ [y/N] " ans
  if [ "${ans,,}" = "y" ]; then
    git add -A
    read -r -p "   پیام کامیت: " msg
    git commit -m "${msg:-update}"
  else
    echo "   لغو شد."; exit 1
  fi
fi

# --- شاخه ---
git branch -M "$BRANCH"

# --- گرفتن توکن ---
if [ -n "${GITHUB_TOKEN:-}" ]; then
  TOKEN="$GITHUB_TOKEN"
  echo "✅ توکن از متغیر محیطی GITHUB_TOKEN خوانده شد."
else
  echo
  echo "نام کاربری گیت‌هاب را بزنید (پیش‌فرض: $USER_NAME):"
  read -r U_IN
  USER_NAME="${U_IN:-$USER_NAME}"
  echo "توکن (PAT) را بچسبانید و اینتر بزنید — نمایش داده نمی‌شود:"
  read -rs TOKEN
  echo
fi

if [ -z "${TOKEN:-}" ]; then
  echo "❌ توکن خالی است."
  echo "   توکن بسازید: GitHub → Settings → Developer settings →"
  echo "   Personal access tokens → Tokens (classic) → اسکوپ repo"
  exit 1
fi

# --- remote ---
AUTH_URL="https://${USER_NAME}:${TOKEN}@github.com/${USER_NAME}/${REPO}.git"
if git remote | grep -qx origin; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# --- پوش ---
echo
echo "⏳ در حال ارسال $(git rev-list --count HEAD) کامیت ..."
if git push "$AUTH_URL" "$BRANCH" 2>&1 | sed -E "s/${TOKEN}/****/g"; then
  echo
  echo "✅ ارسال با موفقیت انجام شد."
  echo "   مخزن: https://github.com/${USER_NAME}/${REPO}"
else
  echo
  echo "❌ ارسال ناموفق بود. خطاهای رایج:"
  echo "   • توکن اسکوپ repo ندارد (یا Contents: Read and write در توکن ریزدانه)"
  echo "   • تاریخچهٔ مخزن ناهمخوان است → اول: git pull origin $BRANCH --rebase --allow-unrelated-histories"
  echo "   • نام کاربری/نام مخزن اشتباه است"
  exit 1
fi

# --- تگ نسخه (اختیاری) ---
VERSION="$(grep -o '"version": "[0-9.]*"' app/web.py 2>/dev/null | head -1 | cut -d'"' -f4 || true)"
if [ -n "${VERSION:-}" ] && ! git rev-parse "v$VERSION" >/dev/null 2>&1; then
  read -r -p "تگ نسخه v$VERSION ساخته و ارسال شود؟ [y/N] " t
  if [ "${t,,}" = "y" ]; then
    git tag -a "v$VERSION" -m "نسخهٔ $VERSION"
    git push "$AUTH_URL" "v$VERSION" 2>&1 | sed -E "s/${TOKEN}/****/g"
    echo "✅ تگ v$VERSION ارسال شد."
  fi
fi

echo
echo "🎉 تمام. برای دفعه‌های بعد: git push origin $BRANCH"
echo "   (اگر خواستید توکن ذخیره شود: git config --global credential.helper store)"
