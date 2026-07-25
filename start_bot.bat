@echo off
chcp 65001 >nul
title Telegram Music Bot

echo.
echo ========================================
echo    🐻 TELEGRAM MUSIC BOT
echo ========================================
echo.

echo 🔍 جاري التحقق من Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python غير موجود! يرجى تثبيت Python 3.8+
    echo 📥 تحميل: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python موجود
echo.

echo 🔍 جاري التحقق من ملف music_bot.py...
if not exist "music_bot.py" (
    echo ❌ ملف music_bot.py غير موجود!
    pause
    exit /b 1
)

echo ✅ ملف music_bot.py موجود
echo.

echo 🔍 جاري التحقق من ملف tracks.json...
if not exist "tracks.json" (
    echo ⚠️ ملف tracks.json غير موجود، جاري إنشاء ملف فارغ...
    echo {} > tracks.json
)

echo ✅ ملف tracks.json جاهز
echo.

echo 🔍 جاري التحقق من مجلد cache...
if not exist "cache" (
    echo 📁 جاري إنشاء مجلد cache...
    mkdir cache
)

echo ✅ مجلد cache جاهز
echo.

echo 🚀 جاري تشغيل البوت...
echo.
echo 💡 لإيقاف البوت اضغط Ctrl+C
echo 💡 يمكن إغلاق النافذة
echo.

python music_bot.py

echo.
echo ❌ تم إيقاف البوت
pause
