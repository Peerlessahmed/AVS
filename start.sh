#!/bin/bash
# ═══════════════════════════════════════════════
# Business Valuation System — Quick Start Script
# نظام تقييم الأعمال — سكريبت التشغيل السريع
# ═══════════════════════════════════════════════

set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo ""
echo "══════════════════════════════════════════════"
echo "   Business Valuation System v0.1.0-beta"
echo "══════════════════════════════════════════════"
echo ""

# ── 1. Python check ──────────────────────────
python3 --version &>/dev/null || err "Python 3 غير مثبت. ثبّته من https://python.org"
PY_VER=$(python3 -c "import sys; print(sys.version_info.minor)")
[ "$PY_VER" -ge 11 ] || err "يتطلب Python 3.11+. الإصدار الحالي: $(python3 --version)"
ok "Python $(python3 --version)"

# ── 2. .env check ────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env غير موجود — جاري إنشاؤه من .env.example"
    cp .env.example .env
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  افتح ملف .env وأضف هذه القيم:          │"
    echo "  │                                          │"
    echo "  │  ANTHROPIC_API_KEY=sk-ant-...            │"
    echo "  │  DATABASE_URL=postgresql://...           │"
    echo "  │  SECRET_KEY=any-long-random-string       │"
    echo "  └─────────────────────────────────────────┘"
    echo ""
    read -p "  اضغط Enter بعد إضافة القيم في .env ..."
fi

# تحقق أن API key ليس placeholder
source .env 2>/dev/null || true
if [[ "$ANTHROPIC_API_KEY" == "your_api_key_here" ]] || [[ -z "$ANTHROPIC_API_KEY" ]]; then
    err "ANTHROPIC_API_KEY غير مضبوط في .env\nاحصل على مفتاحك من https://console.anthropic.com"
fi
ok ".env جاهز"

# ── 3. Virtual environment ───────────────────
if [ ! -d "venv" ]; then
    echo "📦 جاري إنشاء البيئة الافتراضية..."
    python3 -m venv venv
fi
source venv/bin/activate
ok "Virtual environment مفعّل"

# ── 4. Install dependencies ──────────────────
echo "📥 جاري تثبيت المكتبات..."
pip install -q -r requirements.txt
ok "المكتبات مثبتة"

# ── 5. Docker check ──────────────────────────
if command -v docker &>/dev/null; then
    # PostgreSQL
    if ! docker ps --format '{{.Names}}' | grep -q "valuation-db"; then
        echo "🐘 تشغيل PostgreSQL..."
        docker run -d --name valuation-db \
            -e POSTGRES_PASSWORD=password \
            -e POSTGRES_DB=valuation_db \
            -p 5432:5432 postgres:16 &>/dev/null || \
        docker start valuation-db &>/dev/null || true
        sleep 3
    fi
    ok "PostgreSQL يعمل"

    # Redis
    if ! docker ps --format '{{.Names}}' | grep -q "valuation-redis"; then
        echo "🔴 تشغيل Redis..."
        docker run -d --name valuation-redis \
            -p 6379:6379 redis:7 &>/dev/null || \
        docker start valuation-redis &>/dev/null || true
        sleep 2
    fi
    ok "Redis يعمل"
else
    warn "Docker غير مثبت — تأكد أن PostgreSQL وRedis يعملان يدوياً"
fi

# ── 6. Database init ─────────────────────────
echo "🗄️  تهيئة قاعدة البيانات..."
python setup_db.py
ok "قاعدة البيانات جاهزة"

# ── 7. Seed prompts ──────────────────────────
echo "🌱 تحميل الـ Prompts..."
python scripts/seed_prompts.py
ok "Prompts محمّلة"

# ── 8. Launch ────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
ok "النظام جاهز! 🚀"
echo ""
echo "  📖 Swagger UI:  http://localhost:8000/docs"
echo "  💚 Health:      http://localhost:8000/health"
echo "  🔴 إيقاف:       Ctrl+C"
echo "══════════════════════════════════════════════"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
