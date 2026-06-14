"""
نظام تقييم الأعمال والشركات - تكامل Claude AI
Business Valuation System - Claude AI Integration
"""

import json
from typing import Optional
from anthropic import Anthropic
from infrastructure import settings

# ─────────────────────────────────────────────
# Claude Client — يستخدم settings بدلاً من os.environ مباشرةً
# ─────────────────────────────────────────────
client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """أنت خبير متخصص في تقييم الأعمال والشركات، لديك خبرة واسعة في:
- طرق التقييم: DCF، المضاعفات، صافي الأصول، المعاملات المماثلة
- تحليل البيانات المالية: الإيرادات، EBITDA، التدفق النقدي
- تقييم المخاطر والفرص في السوق السعودي والخليجي
- معايير IFRS والمعايير المحاسبية الدولية

عند تقييم أي شركة:
1. اطلب البيانات المالية للسنوات الثلاث الماضية على الأقل
2. حدد القطاع والمنافسين الرئيسيين
3. استخدم أكثر من طريقة تقييم واحدة
4. قدم نطاقاً للقيمة (أدنى - أعلى) مع التبرير
5. أشر إلى المخاطر والعوامل المؤثرة في التقييم

أجب دائماً باللغة العربية ما لم يُطلب غير ذلك."""


# ─────────────────────────────────────────────
# Core Valuation Engine (Multi-turn)
# ─────────────────────────────────────────────
class BusinessValuationAgent:
    def __init__(self):
        self.conversation_history = []
        self.company_data = {}

    def chat(self, user_message: str) -> str:
        """إرسال رسالة والحصول على رد Claude مع الحفاظ على السياق"""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=SYSTEM_PROMPT,
            messages=self.conversation_history
        )

        assistant_message = response.content[0].text
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message

    def reset(self):
        """إعادة تعيين المحادثة لشركة جديدة"""
        self.conversation_history = []
        self.company_data = {}


# ─────────────────────────────────────────────
# Structured Valuation Report
# ─────────────────────────────────────────────
def generate_valuation_report(company_info: dict) -> dict:
    """
    توليد تقرير تقييم منظم باستخدام Claude
    
    company_info مثال:
    {
        "name": "شركة النماء للتجزئة",
        "sector": "تجزئة",
        "revenue_3y": [15000000, 18000000, 22000000],  # ريال
        "ebitda_3y": [2500000, 3200000, 4100000],
        "net_debt": 5000000,
        "employees": 150,
        "market": "المملكة العربية السعودية"
    }
    """

    prompt = f"""قم بتقييم الشركة التالية وأعطني تقريراً منظماً بصيغة JSON فقط بدون أي نص إضافي:

بيانات الشركة:
{json.dumps(company_info, ensure_ascii=False, indent=2)}

أعد JSON بالهيكل التالي:
{{
  "company_name": "اسم الشركة",
  "valuation_date": "تاريخ اليوم",
  "methods": {{
    "dcf": {{
      "value": 0,
      "assumptions": "الافتراضات",
      "growth_rate": 0.0,
      "discount_rate": 0.0
    }},
    "ebitda_multiple": {{
      "value": 0,
      "multiple_used": 0.0,
      "sector_range": "نطاق القطاع"
    }},
    "revenue_multiple": {{
      "value": 0,
      "multiple_used": 0.0
    }}
  }},
  "valuation_range": {{
    "low": 0,
    "mid": 0,
    "high": 0,
    "currency": "SAR"
  }},
  "key_risks": ["خطر 1", "خطر 2"],
  "value_drivers": ["محرك 1", "محرك 2"],
  "recommendation": "ملخص التقييم والتوصية"
}}"""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # إزالة markdown إن وُجد
    raw = raw.replace("```json", "").replace("```", "").strip()

    return json.loads(raw)


# ─────────────────────────────────────────────
# Streaming Valuation Analysis
# ─────────────────────────────────────────────
def stream_valuation_analysis(company_name: str, financial_data: str):
    """تحليل مالي مع streaming للردود الطويلة"""

    prompt = f"""قم بتحليل مالي شامل لشركة "{company_name}" بناءً على البيانات التالية:

{financial_data}

يشمل التحليل:
1. نظرة عامة على الأداء المالي
2. تحليل النمو والربحية  
3. مقارنة بمعايير القطاع
4. تقييم المخاطر
5. توصيات للمستثمرين"""

    print(f"\n{'='*60}")
    print(f"📊 تحليل مالي: {company_name}")
    print('='*60)

    with client.messages.stream(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

    print(f"\n{'='*60}\n")


# ─────────────────────────────────────────────
# Document Analysis (PDF/Financial Statements)
# ─────────────────────────────────────────────
def analyze_financial_document(file_path: str, question: str = None) -> str:
    """
    تحليل ميزانية عمومية أو قائمة دخل من ملف
    يقرأ الملف النصي ويحلله مع Claude
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    default_question = """استخرج من هذه البيانات المالية:
    1. إجمالي الإيرادات لكل سنة
    2. صافي الربح والهامش
    3. EBITDA المقدر
    4. إجمالي الديون والنقد
    5. أي مؤشرات تحذيرية (Red Flags)"""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        messages=[{
            "role": "user",
            "content": f"البيانات المالية:\n\n{content}\n\n{question or default_question}"
        }]
    )

    return response.content[0].text


# ─────────────────────────────────────────────
# Batch Valuation (متعدد الشركات)
# ─────────────────────────────────────────────
def batch_quick_valuation(companies: list[dict]) -> list[dict]:
    """
    تقييم سريع لقائمة شركات باستخدام Batch API
    مفيد لصناديق الاستثمار لمسح السوق
    """
    results = []

    for company in companies:
        prompt = f"""قيّم هذه الشركة بإيجاز شديد وأعد JSON فقط:
شركة: {company['name']} | قطاع: {company['sector']}
إيرادات: {company.get('revenue', 'غير متاح')} ريال | EBITDA: {company.get('ebitda', 'غير متاح')} ريال

JSON المطلوب: {{"name":"","estimated_value":0,"method":"","confidence":"low/medium/high","note":""}}"""

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        try:
            results.append(json.loads(raw))
        except json.JSONDecodeError:
            results.append({"name": company['name'], "error": "فشل التحليل"})

    return results


# ─────────────────────────────────────────────
# Demo / Test
# ─────────────────────────────────────────────
if __name__ == "__main__":

    print("🏢 نظام تقييم الأعمال - Claude AI Integration\n")

    # ── 1. محادثة تفاعلية ──────────────────────
    print("═" * 60)
    print("1️⃣  وضع المحادثة التفاعلية")
    print("═" * 60)

    agent = BusinessValuationAgent()

    r1 = agent.chat("أريد تقييم شركة تجزئة في السوق السعودي، إيراداتها 20 مليون ريال وEBITDA بـ 3 مليون ريال")
    print("Claude:", r1[:400], "...\n")

    r2 = agent.chat("ما هي طريقة التقييم الأنسب لهذا النوع من الشركات؟")
    print("Claude:", r2[:400], "...\n")

    # ── 2. تقرير منظم ──────────────────────────
    print("═" * 60)
    print("2️⃣  تقرير تقييم منظم (JSON)")
    print("═" * 60)

    company_data = {
        "name": "شركة الرياض للتجزئة",
        "sector": "تجزئة - مواد غذائية",
        "revenue_3y": [15_000_000, 18_500_000, 22_000_000],
        "ebitda_3y": [2_200_000, 3_000_000, 3_800_000],
        "net_debt": 4_000_000,
        "employees": 120,
        "market": "المملكة العربية السعودية - الرياض"
    }

    report = generate_valuation_report(company_data)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # ── 3. تحليل Streaming ─────────────────────
    print("\n" + "═" * 60)
    print("3️⃣  تحليل مالي مع Streaming")
    print("═" * 60)

    financial_summary = """
    السنة 2022: إيرادات 15م | صافي ربح 1.5م | ديون 6م
    السنة 2023: إيرادات 18.5م | صافي ربح 2.1م | ديون 5م
    السنة 2024: إيرادات 22م | صافي ربح 2.8م | ديون 4م
    نقد متاح: 2 مليون ريال | عدد الفروع: 8
    """

    stream_valuation_analysis("شركة الرياض للتجزئة", financial_summary)

    # ── 4. تقييم دفعي ──────────────────────────
    print("═" * 60)
    print("4️⃣  تقييم دفعي لمحفظة شركات")
    print("═" * 60)

    portfolio = [
        {"name": "شركة أ للتقنية", "sector": "تقنية", "revenue": 5_000_000, "ebitda": 1_200_000},
        {"name": "شركة ب للمطاعم", "sector": "مطاعم", "revenue": 8_000_000, "ebitda": 900_000},
        {"name": "شركة ج للخدمات اللوجستية", "sector": "لوجستيات", "revenue": 12_000_000, "ebitda": 1_800_000},
    ]

    batch_results = batch_quick_valuation(portfolio)
    print("\nنتائج التقييم السريع:")
    for r in batch_results:
        print(f"  • {r.get('name','؟')}: {r.get('estimated_value', 0):,} ريال ({r.get('confidence','؟')})")

    print("\n✅ اكتمل التكامل بنجاح!")
