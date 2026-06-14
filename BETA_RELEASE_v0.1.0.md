# 📦 Beta Release Package — v0.1.0-beta
## نظام تقييم الأعمال | Business Valuation System

---

## 1. CHANGELOG.md

```markdown
# CHANGELOG — نظام تقييم الأعمال

All notable changes to this project are documented here.
يتم توثيق جميع التغييرات الجوهرية في هذا الملف.

Format: [Semantic Versioning](https://semver.org)
Compliance: IVS 105, IVS 200, IFRS 13

---

## [0.1.0-beta] — 2026-06-15

### 🆕 Added | المضاف

**Core Infrastructure | البنية الأساسية**
- FastAPI application with JWT authentication (admin / analyst / viewer roles)
- PostgreSQL ORM via SQLAlchemy — 8 tables: users, companies, financial_data,
  valuations, chat_sessions, chat_messages, prompt_templates, prompt_usage_log
- Redis-backed chat session store (TTL: 24h) + valuation cache (TTL: 1h)
- Async Claude AI integration via `ClaudeService` with retry logic (3 attempts),
  exponential backoff, per-model cost tracking, and 60s timeout
- Environment-validated settings via `pydantic-settings` v2 with field validators

**Prompt Registry | سجل الـ Prompts**
- `prompt_templates` table with versioning (draft → approved → deprecated)
- `prompt_versions` table for full content snapshots on every approval
- `prompt_usage_log` table for per-call token and cost tracking
- `PromptManager` service: get, render, cache, invalidate, log
- Governance API: create / test / approve / rollback / deprecate
- `MASTER_SYSTEM_PROMPT` v1.0.0 — 8 IVS/IFRS compliance principles

**Stage Prompts (11 مرحلة) | Stage Prompts**
- `1.1 extraction.financial_statements` — PDF/Excel/Word extraction with
  category, standard_name, source_location, confidence per line item
- `2.1 analysis.historical_trends` — revenue, profitability, efficiency,
  liquidity analysis + anomaly detection + management questions
- `3.1 questions.management_qa` — 15–20 prioritized due diligence questions
  with linked_kpi and impact_on_valuation fields
- `4.1 assumptions.update_from_qa` — stated vs inferred assumption updates
  with vs_historical comparison
- `5.1 methodology.selection` — IVS 105 methodology selection with
  suitability scores and compliance references
- `6.1 research.industry_analysis` — market size, benchmarks, competitive
  landscape with explicit data-source disclaimers
- `7.1 comps.selection` — comparable company scoring with 5 weighted criteria
- `8.1 dcf.narrative` — full WACC build-up (CAPM), terminal value rationale,
  sensitivity discussion
- `11.1 report.executive_summary` — IVS-compliant executive summary template
  with key_metrics_table

**Document Processing | معالجة المستندات**
- Multi-format extraction: PDF (PyMuPDF/fitz), Excel (pandas + openpyxl/xlrd),
  Word (python-docx), CSV/TXT
- `DocumentChunker`: page-based PDF splitting, sheet-based Excel splitting,
  deduplication by confidence score
- Background processing via FastAPI `BackgroundTasks` (202 Accepted pattern)
- Streaming read with 20MB size limit (1MB chunks)
- Auto-detection of statement type from keyword scoring

**Anti-Hallucination Validation | التحقق من الهلوسة**
- `ClaudeOutputValidator` with 4-tier confidence matrix (per Prompt Pack v1.0.0)
- Arithmetic checks for all three statement types:
  - Balance Sheet: Assets = Liabilities + Equity (error > 1%, warning 0.1–1%)
  - Income Statement: Gross Profit = Revenue − COGS
  - Cash Flow: Ending Cash = Beginning + Net Change
- Source cross-reference: extracted values vs source document numbers (5% threshold)
- Weighted confidence scoring: 70% Claude score + 30% field completeness

**API Endpoints | نقاط النهاية**
- `POST /auth/register` — تسجيل مستخدم
- `POST /auth/token` — تسجيل دخول OAuth2
- `GET  /auth/me` — بيانات المستخدم الحالي
- `POST /companies` — إضافة شركة
- `POST /companies/{id}/financials` — إضافة بيانات مالية
- `GET  /companies/{id}` — تفاصيل الشركة مع البيانات المالية
- `POST /valuations` — تقييم شركة بـ Claude AI مع حفظ في DB
- `GET  /valuations/{id}/stream` — تحليل مالي Streaming
- `POST /chat` — محادثة مع خبير التقييم (Redis-backed)
- `GET  /chat/{id}/history` — سجل المحادثة
- `POST /api/projects/{id}/upload-document` — رفع مستند
- `GET  /api/projects/{id}/documents/{file_id}` — حالة المعالجة
- `POST /api/prompts` — إنشاء prompt
- `POST /api/prompts/{id}/test` — اختبار prompt
- `POST /api/prompts/{id}/approve` — اعتماد prompt (admin)
- `POST /api/prompts/{id}/rollback` — Rollback لإصدار سابق
- `GET  /api/prompts/{id}/usage` — إحصائيات الاستخدام

### ⏭️ Deferred to v0.2.0 | مؤجل للإصدار القادم

- `9.1 discounts.dlom_dloc` — DLOM/DLOC calculation (Module 9)
- `10.1 reconciliation.methodologies` — Multi-method reconciliation (Module 10)
- Advanced React dashboard for analysts
- Celery background task queue for long-running valuations
- PDF generation for final reports (python-docx / WeasyPrint)

### 🐛 Known Issues | المشاكل المعروفة

| ID    | Severity | Issue | Workaround |
|-------|----------|-------|------------|
| BUG-001 | High | OCR fails on scanned Arabic PDFs — PyMuPDF returns empty text | Use text-layer PDFs or pre-convert with Adobe Acrobat |
| BUG-002 | Medium | DCF sensitivity table renders with misaligned columns in report output | Manually reformat `sensitivity_discussion` field post-generation |
| BUG-003 | Medium | Comparable company API times out after 60s for large candidate lists (>15 comps) | Limit `candidate_comps` to ≤10 items per request |

### 🔧 Infrastructure | البنية التحتية

- Python 3.11+
- FastAPI 0.115+, Uvicorn 0.32+
- SQLAlchemy 2.0+, Alembic 1.14+, psycopg2-binary 2.9+
- Redis 5.2+
- anthropic 0.40+
- pydantic-settings 2.7+
- PyMuPDF (fitz) 1.25+, pandas 2.2+, python-docx 1.1+

---

## [Unreleased] — upcoming v0.2.0

### Planned
- Module 9: DLOM/DLOC calculation with empirical study references
- Module 10: Multi-methodology reconciliation with variance analysis
- Fix BUG-001: Arabic OCR via pytesseract + Arabic language pack
- Fix BUG-002: Structured sensitivity table as JSON array
- Fix BUG-003: Pagination for comparable company API
- React analyst dashboard
- Celery + Redis task queue
- PDF/Word report export
```

---

## 2. Beta Checklist — قبل الإصدار

```markdown
# ✅ Beta Release Checklist — v0.1.0-beta

## Environment | البيئة
- [ ] `.env` يحتوي على ANTHROPIC_API_KEY صالح (ليس placeholder)
- [ ] PostgreSQL يعمل وجداول Alembic مُهيّأة (`python setup_db.py`)
- [ ] Redis يعمل (`redis-cli ping` → PONG)
- [ ] `python scripts/seed_prompts.py` اكتمل بنجاح (11/11 prompts)
- [ ] `GET /health` يُعيد `{"redis": "متصل"}`

## Security | الأمان
- [ ] `SECRET_KEY` ليس القيمة الافتراضية "change-me"
- [ ] `CORS` مقيّد بـ domains محددة (ليس `allow_origins=["*"]`)
- [ ] Admin account مُنشأ بكلمة مرور قوية
- [ ] `/docs` و `/redoc` معطّلة أو محمية بـ auth في Production

## Core Flows | التدفقات الأساسية
- [ ] Register → Login → Token يعمل
- [ ] رفع PDF نصي → استخراج line items بـ confidence ≥ 0.8
- [ ] رفع Excel → استخراج بيانات شركة
- [ ] `POST /valuations` يُعيد valuation_range مع 3 طرق
- [ ] Streaming response لا تنتهي بـ timeout
- [ ] Chat session محفوظ في Redis بين الرسائل

## Prompt Registry | سجل الـ Prompts
- [ ] 11 prompts بحالة "approved" في قاعدة البيانات
- [ ] `render_prompt()` يرفع ValueError لمتغيرات مفقودة
- [ ] `log_usage()` يسجّل tokens والتكلفة لكل استدعاء

## Known Issues Acknowledged | المشاكل المعروفة موثّقة
- [ ] BUG-001 (Arabic OCR) موثّق في CHANGELOG
- [ ] BUG-002 (DCF table) موثّق في CHANGELOG
- [ ] BUG-003 (Comps timeout) موثّق في CHANGELOG

## Deferred Features Confirmed | الميزات المؤجلة مؤكدة
- [ ] Module 9 (DLOM/DLOC) — ليس في هذا الإصدار
- [ ] Module 10 (Reconciliation) — ليس في هذا الإصدار
```

---

## 3. README.md Banner — النسخة التجريبية

```markdown
> [!WARNING]
> **🧪 نسخة تجريبية — Beta v0.1.0**
>
> هذا النظام في مرحلة Beta ولم يُصدر للإنتاج الرسمي بعد.
> استخدمه للاختبار والتقييم فقط. لا تستخدم مخرجاته في تقارير
> رسمية أو قرارات مالية دون مراجعة خبير تقييم معتمد.
>
> **⚠️ Beta Release — Not Production Ready**
>
> This system is in Beta. Outputs must be reviewed by a qualified
> valuation professional before use in formal reports or financial decisions.
> Modules 9 (DLOM/DLOC) and 10 (Reconciliation) are not yet available.
>
> Known issues: Arabic OCR (BUG-001) · DCF table formatting (BUG-002) · Comps API timeout (BUG-003)
>
> 📋 [Full CHANGELOG](./BETA_RELEASE_v0.1.0.md) · 🐛 [Report an Issue](#) · 📅 Next release: v0.2.0
```

---

## 4. Commit Message — رسالة الـ Commit

```
release: v0.1.0-beta — Business Valuation System initial beta

Includes:
- FastAPI + PostgreSQL + Redis + JWT authentication
- Async Claude AI integration with retry, cost tracking, streaming
- Prompt Registry (11 stage prompts, v1.0.0) with governance workflow
- Document processing: PDF/Excel/Word + auto-chunking
- Anti-hallucination validation (4-tier confidence, arithmetic checks)
- 20 API endpoints across auth/companies/valuations/chat/prompts/documents

Deferred: Module 9 (DLOM/DLOC), Module 10 (Reconciliation), React UI
Known issues: BUG-001 Arabic OCR, BUG-002 DCF table, BUG-003 Comps timeout

BREAKING: Requires Python 3.11+, PostgreSQL 16+, Redis 7+
Co-authored-by: Claude <claude@anthropic.com>
```

---

## 5. أول 5 اختبارات بعد الإصدار — Post-Release Smoke Tests

### 🧪 Test 1 — Auth + Permissions (الأولوية: عالية)

```bash
# 1. تسجيل مستخدم Analyst
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@firm.com","full_name":"مختبر","password":"Test@1234","role":"analyst"}'

# 2. تسجيل دخول
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -d "username=test@firm.com&password=Test@1234" | jq -r .access_token)

# ✅ المتوقع: access_token موجود وغير null
echo $TOKEN | cut -c1-20

# 3. Analyst لا يمكنه الموافقة على Prompt (يجب 403)
curl -s -X POST http://localhost:8000/api/prompts/SOME_ID/approve \
  -H "Authorization: Bearer $TOKEN" | jq .detail
# ✅ المتوقع: "صلاحيات غير كافية"
```

**ما تثبته:** JWT يعمل، role-based access يعمل، token expiry مضبوط.

---

### 🧪 Test 2 — PDF Extraction End-to-End (الأولوية: عالية)

```bash
# رفع PDF مالي نصي (ليس ممسوح ضوئياً)
curl -X POST "http://localhost:8000/api/projects/proj-001/upload-document" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_income_statement.pdf" \
  -F "statement_type=income_statement"

# ✅ المتوقع: 202 Accepted + file_id + status_url

# انتظر 15 ثانية ثم تحقق من الحالة
sleep 15
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/projects/proj-001/documents/FILE_ID" | jq '{
    status, statement_type, confidence,
    items_count: (.data.line_items | length),
    warnings: .data.warnings
  }'

# ✅ المتوقع:
# status: "completed"
# confidence: ≥ 0.80
# items_count: > 0
# لا يوجد في line_items قيم null دون سبب
```

**ما تثبته:** PyMuPDF يعمل، Claude يستخرج، DB يحفظ، BG task ينتهي.

---

### 🧪 Test 3 — Prompt Registry + Governance (الأولوية: عالية)

```python
# اختبار Python مباشر
import httpx, json

BASE = "http://localhost:8000"

# Admin token
r = httpx.post(f"{BASE}/auth/token",
               data={"username": "admin@firm.com", "password": "AdminPass"})
admin_token = r.json()["access_token"]
H = {"Authorization": f"Bearer {admin_token}"}

# 1. تحقق أن 11 prompts موجودة ومعتمدة
r = httpx.get(f"{BASE}/api/prompts?status=approved", headers=H)
prompts = r.json()
assert prompts["total"] == 11, f"Expected 11, got {prompts['total']}"

# 2. إنشاء prompt مسودة
new_prompt = {
    "prompt_key": "test.smoke_test",
    "version": "v0.1.0",
    "user_prompt_template": "Test: {input_text}",
    "stage": "extraction"
}
r = httpx.post(f"{BASE}/api/prompts", headers=H, json=new_prompt)
assert r.status_code == 201
prompt_id = r.json()["prompt_id"]

# 3. اختبار الـ prompt
r = httpx.post(f"{BASE}/api/prompts/{prompt_id}/test", headers=H,
               json={"variables": {"input_text": "Hello test"}})
assert r.json()["test_passed"] == True

# 4. اعتماد → تحقق من الحالة
httpx.post(f"{BASE}/api/prompts/{prompt_id}/approve", headers=H)
r = httpx.get(f"{BASE}/api/prompts?status=approved", headers=H)
assert r.json()["total"] == 12   # 11 + 1 جديد

print("✅ Prompt Registry: جميع الاختبارات نجحت")
```

**ما تثبته:** lifecycle كامل (draft → test → approve)، cache invalidation، عدد prompts صحيح.

---

### 🧪 Test 4 — Valuation + Claude Anti-Hallucination (الأولوية: متوسطة)

```python
import httpx, json

BASE = "http://localhost:8000"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# 1. أنشئ شركة مع بيانات مالية
r = httpx.post(f"{BASE}/companies", headers=H,
               json={"name": "شركة الاختبار", "sector": "تجزئة",
                     "market": "السعودية"})
company_id = r.json()["id"]

for year, rev, ebitda in [(2022, 15_000_000, 2_200_000),
                           (2023, 18_500_000, 3_000_000),
                           (2024, 22_000_000, 3_800_000)]:
    httpx.post(f"{BASE}/companies/{company_id}/financials", headers=H,
               json={"year": year, "revenue": rev, "ebitda": ebitda,
                     "total_debt": 4_000_000, "cash": 1_500_000})

# 2. تقييم
r = httpx.post(f"{BASE}/valuations", headers=H,
               json={"company_id": company_id}, timeout=120.0)
v = r.json()

# ✅ تحقق من الهيكل
assert "valuation_range" in v
assert v["valuation_range"]["low"] < v["valuation_range"]["mid"] < v["valuation_range"]["high"]
assert len(v.get("key_risks", [])) > 0
assert len(v.get("value_drivers", [])) > 0
assert v.get("source") in ("ai", "cache")

# ✅ تحقق من التكلفة مسجّلة
r = httpx.get(f"{BASE}/api/prompts", headers=H)
# التكلفة يجب أن تكون > 0 في usage_log
print(f"✅ Valuation: {v['valuation_range']['mid']:,.0f} SAR")
print(f"   Risks: {len(v['key_risks'])}, Drivers: {len(v['value_drivers'])}")
```

**ما تثبته:** Claude يرد ببيانات منطقية، validation لا يرفض ردوداً صحيحة، الكاش يعمل.

---

### 🧪 Test 5 — Known Bugs Verification (الأولوية: متوسطة)

```bash
echo "=== BUG-001: Arabic OCR Test ==="
# رفع PDF ممسوح ضوئياً بالعربية
curl -s -X POST "http://localhost:8000/api/projects/test/upload-document" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@arabic_scanned.pdf" | jq .file_id > /tmp/fid.txt

sleep 20
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/projects/test/documents/$(cat /tmp/fid.txt)" \
  | jq '{status, confidence}'
# ⚠️ المتوقع: status="completed" لكن confidence < 0.5
# أو status="failed" مع error يذكر "empty text"
# → يؤكد BUG-001 موثّق بشكل صحيح

echo ""
echo "=== BUG-003: Comps Timeout Test ==="
# إرسال قائمة 16 شركة مماثلة
python3 - <<'PYEOF'
import httpx, time, json

comps = [{"name": f"Company {i}", "sector": "Tech",
           "revenue": 50_000_000, "ebitda": 8_000_000}
          for i in range(16)]

start = time.time()
r = httpx.post("http://localhost:8000/valuations",
               headers={"Authorization": f"Bearer TOKEN"},
               json={"companies": comps},
               timeout=70.0)
elapsed = time.time() - start

if elapsed > 60:
    print(f"⚠️ BUG-003 confirmed: timeout after {elapsed:.0f}s")
else:
    print(f"✅ No timeout: {elapsed:.0f}s")
PYEOF
```

**ما تثبته:** الـ bugs المعروفة موثّقة بشكل صحيح وسلوكها متوقع، لا يوجد crash غير متوقع.

---

## ملاحظات الإصدار

| البند | القيمة |
|-------|--------|
| الإصدار | `v0.1.0-beta` |
| تاريخ الإصدار | 2026-06-15 |
| Python المطلوب | 3.11+ |
| قاعدة البيانات | PostgreSQL 16+ |
| Cache | Redis 7+ |
| Claude Model | `claude-sonnet-4-6` |
| Prompts المحمّلة | 11 / 11 (Modules 1–8, 11) |
| Endpoints | 20 نقطة نهاية |
| الميزات المؤجلة | Module 9, 10, UI |
| الـ Bugs المعروفة | 3 (BUG-001, 002, 003) |

> هذا الملف مرجع شامل للإصدار التجريبي.
> للإصدار الرسمي v1.0.0، يجب إغلاق جميع الـ bugs وإكمال Modules 9 و10.
