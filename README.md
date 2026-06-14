> [!WARNING]
> **🧪 نسخة تجريبية — Beta v0.1.0**
> هذا النظام في مرحلة Beta. لا تستخدم مخرجاته في تقارير رسمية دون مراجعة خبير تقييم معتمد.

# 🏢 Business Valuation System
**نظام تقييم الأعمال — Claude AI + FastAPI + PostgreSQL + Redis**

## ⚡ تشغيل سريع

### Mac / Linux
```bash
cd valuation-system
./start.sh
```

### Windows
```bat
cd valuation-system
start.bat
```

ثم افتح: **http://localhost:8000/docs**

---

## 📋 المتطلبات
- Python 3.11+
- Docker (لـ PostgreSQL و Redis تلقائياً)
- مفتاح Anthropic API من https://console.anthropic.com

## 🗂️ هيكل الملفات
```
valuation-system/
├── start.sh / start.bat   ← سكريبت التشغيل
├── main.py                ← FastAPI app
├── infrastructure.py      ← PostgreSQL + Redis + JWT
├── models.py              ← جداول قاعدة البيانات
├── claude_service.py      ← تكامل Claude AI
├── setup_db.py            ← تهيئة الجداول
├── .env.example           ← انسخه إلى .env
├── models/
│   └── prompt_models.py   ← Prompt Registry
├── services/
│   ├── prompt_manager.py
│   ├── claude_service_enhanced.py
│   ├── extraction_service.py
│   └── validation_service.py
├── routers/
│   ├── documents.py
│   └── prompts.py
└── scripts/
    └── seed_prompts.py    ← تحميل الـ 11 Prompts
```

## 🔌 API Endpoints الرئيسية
| Method | Endpoint | الوصف |
|--------|----------|-------|
| POST | `/auth/register` | تسجيل مستخدم |
| POST | `/auth/token` | تسجيل دخول |
| POST | `/companies` | إضافة شركة |
| POST | `/valuations` | تقييم شركة بـ Claude |
| POST | `/chat` | محادثة مع خبير التقييم |
| POST | `/api/projects/{id}/upload-document` | رفع مستند مالي |

الوثائق الكاملة: http://localhost:8000/docs
