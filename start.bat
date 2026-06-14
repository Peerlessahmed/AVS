@echo off
chcp 65001 >nul
echo.
echo ══════════════════════════════════════════════
echo    Business Valuation System v0.1.0-beta
echo ══════════════════════════════════════════════
echo.

:: ── 1. Python check ──────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python غير مثبت. ثبّته من https://python.org
    pause & exit /b 1
)
echo [OK] Python مثبت

:: ── 2. .env check ────────────────────────────
if not exist ".env" (
    echo [INFO] جاري إنشاء .env من .env.example
    copy .env.example .env >nul
    echo.
    echo  ┌─────────────────────────────────────────┐
    echo  │  افتح ملف .env وأضف هذه القيم:          │
    echo  │                                          │
    echo  │  ANTHROPIC_API_KEY=sk-ant-...            │
    echo  │  DATABASE_URL=postgresql://...           │
    echo  │  SECRET_KEY=any-long-random-string       │
    echo  └─────────────────────────────────────────┘
    echo.
    pause
)
echo [OK] .env موجود

:: ── 3. Virtual environment ───────────────────
if not exist "venv\" (
    echo [INFO] جاري إنشاء البيئة الافتراضية...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [OK] Virtual environment مفعّل

:: ── 4. Install dependencies ──────────────────
echo [INFO] جاري تثبيت المكتبات...
pip install -q -r requirements.txt
echo [OK] المكتبات مثبتة

:: ── 5. Docker (optional) ────────────────────
docker --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] تشغيل PostgreSQL و Redis...
    docker start valuation-db >nul 2>&1 || docker run -d --name valuation-db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=valuation_db -p 5432:5432 postgres:16 >nul 2>&1
    docker start valuation-redis >nul 2>&1 || docker run -d --name valuation-redis -p 6379:6379 redis:7 >nul 2>&1
    timeout /t 3 /nobreak >nul
    echo [OK] PostgreSQL و Redis يعملان
) else (
    echo [WARN] Docker غير مثبت — تأكد من تشغيل PostgreSQL و Redis يدوياً
)

:: ── 6. Database init ─────────────────────────
echo [INFO] تهيئة قاعدة البيانات...
python setup_db.py
echo [OK] قاعدة البيانات جاهزة

:: ── 7. Seed prompts ──────────────────────────
echo [INFO] تحميل الـ Prompts...
python scripts\seed_prompts.py
echo [OK] Prompts محمّلة

:: ── 8. Launch ────────────────────────────────
echo.
echo ══════════════════════════════════════════════
echo [OK] النظام جاهز! 
echo.
echo   Swagger UI:  http://localhost:8000/docs
echo   Health:      http://localhost:8000/health
echo   إيقاف:       Ctrl+C
echo ══════════════════════════════════════════════
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
