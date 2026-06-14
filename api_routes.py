"""
FastAPI - نقاط نهاية تقييم الأعمال بتكامل Claude AI
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import json
import asyncio

# استيراد خدمة التقييم
from ai_valuation_service import (
    BusinessValuationAgent,
    generate_valuation_report,
    batch_quick_valuation,
    client,
    SYSTEM_PROMPT
)

app = FastAPI(
    title="نظام تقييم الأعمال - Valuation AI",
    description="API لتقييم الأعمال والشركات مع تكامل Claude AI",
    version="1.0.0"
)

# تخزين جلسات المحادثة (في الإنتاج: استخدم Redis)
sessions: dict[str, BusinessValuationAgent] = {}


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="معرف الجلسة")
    message: str = Field(..., description="رسالة المستخدم")


class CompanyInfo(BaseModel):
    name: str
    sector: str
    revenue_3y: list[float] = Field(..., description="الإيرادات لآخر 3 سنوات بالريال")
    ebitda_3y: list[float] = Field(..., description="EBITDA لآخر 3 سنوات")
    net_debt: float = Field(0, description="صافي الدين")
    employees: Optional[int] = None
    market: str = "المملكة العربية السعودية"


class BatchCompany(BaseModel):
    name: str
    sector: str
    revenue: Optional[float] = None
    ebitda: Optional[float] = None


class BatchRequest(BaseModel):
    companies: list[BatchCompany]


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.post("/api/chat", summary="محادثة تفاعلية مع خبير التقييم")
async def chat_with_expert(req: ChatRequest):
    """
    محادثة متعددة الأدوار مع Claude كخبير تقييم أعمال.
    يحفظ السياق عبر رسائل متعددة.
    """
    if req.session_id not in sessions:
        sessions[req.session_id] = BusinessValuationAgent()

    agent = sessions[req.session_id]

    try:
        reply = agent.chat(req.message)
        return {
            "session_id": req.session_id,
            "reply": reply,
            "turns": len(agent.conversation_history) // 2
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/{session_id}", summary="إعادة تعيين جلسة المحادثة")
async def reset_session(session_id: str):
    if session_id in sessions:
        sessions[session_id].reset()
    return {"message": "تمت إعادة تعيين الجلسة"}


@app.post("/api/valuation/report", summary="توليد تقرير تقييم منظم")
async def create_valuation_report(company: CompanyInfo):
    """
    يولد تقرير تقييم كامل بصيغة JSON يشمل:
    - تقييم DCF
    - مضاعفات EBITDA
    - مضاعفات الإيرادات
    - نطاق القيمة (أدنى/متوسط/أعلى)
    - المخاطر ومحركات القيمة
    """
    try:
        report = generate_valuation_report(company.model_dump())
        return report
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="فشل تحليل رد Claude - أعد المحاولة")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/valuation/stream", summary="تحليل مالي مع Streaming")
async def stream_analysis(company: CompanyInfo):
    """
    تحليل مالي شامل مع streaming للردود الطويلة.
    مثالي لواجهات المستخدم التي تعرض النص تدريجياً.
    """
    financial_text = f"""
    الشركة: {company.name} | القطاع: {company.sector}
    إيرادات 3 سنوات: {company.revenue_3y}
    EBITDA 3 سنوات: {company.ebitda_3y}
    صافي الدين: {company.net_debt:,.0f} ريال
    عدد الموظفين: {company.employees or 'غير محدد'}
    السوق: {company.market}
    """

    prompt = f"""قم بتحليل مالي شامل لـ {company.name} بناءً على:
{financial_text}

يشمل: الأداء المالي، النمو، الربحية، المخاطر، التوصية للمستثمرين."""

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                yield text

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@app.post("/api/valuation/batch", summary="تقييم دفعي لمحفظة شركات")
async def batch_valuation(req: BatchRequest):
    """
    تقييم سريع لقائمة شركات دفعة واحدة.
    مفيد لصناديق الاستثمار لمسح فرص الاستثمار.
    """
    try:
        companies = [c.model_dump() for c in req.companies]
        results = batch_quick_valuation(companies)
        return {
            "total": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/valuation/document", summary="تحليل وثيقة مالية نصية")
async def analyze_document(file: UploadFile = File(...)):
    """
    رفع وثيقة مالية (TXT) وتحليلها باستخدام Claude.
    """
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="مدعوم حالياً: ملفات TXT فقط")

    content = await file.read()
    text = content.decode('utf-8')

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""حلل هذه البيانات المالية واستخرج:
1. الإيرادات السنوية
2. صافي الربح والهامش
3. EBITDA المقدر  
4. الديون والسيولة
5. أي مؤشرات تحذيرية

البيانات:
{text}"""
        }]
    )

    return {
        "filename": file.filename,
        "analysis": response.content[0].text
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Valuation AI System"}
