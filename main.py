"""
التطبيق الرئيسي - FastAPI مع المصادقة + الشركات + التقييم + المحادثة
"""

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import timedelta
import json

from models import (
    User, Company, FinancialData, Valuation,
    ChatSession, ChatMessage,
    UserRole, ValuationStatus
)
from infrastructure import (
    get_db, init_db, settings,
    hash_password, verify_password,
    create_access_token, decode_token,
    ChatSessionStore, Cache
)
from ai_valuation_service import (
    generate_valuation_report,
    batch_quick_valuation,
    stream_valuation_analysis,
    client, SYSTEM_PROMPT
)

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────
app = FastAPI(
    title="نظام تقييم الأعمال",
    description="Business Valuation System — Claude AI + PostgreSQL + Redis",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # عدّل في الإنتاج
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


@app.on_event("startup")
async def startup():
    init_db()
    print("🚀 النظام جاهز")


# ─────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="توكن غير صالح")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود أو معطل")
    return user


def require_role(*roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="صلاحيات غير كافية")
        return current_user
    return checker


# ─────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.analyst

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    class Config: from_attributes = True

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class CompanyCreate(BaseModel):
    name: str
    sector: str
    market: str = "المملكة العربية السعودية"
    description: Optional[str] = None
    employees: Optional[int] = None
    founded_year: Optional[int] = None

class FinancialCreate(BaseModel):
    year: int
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_profit: Optional[float] = None
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None

class ValuationRequest(BaseModel):
    company_id: int
    use_cache: bool = True

class ChatRequest(BaseModel):
    session_id: str
    message: str
    company_id: Optional[int] = None


# ─────────────────────────────────────────────
# ① Auth Routes
# ─────────────────────────────────────────────
@app.post("/auth/register", response_model=UserOut, tags=["Auth"])
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "البريد الإلكتروني مسجل مسبقاً")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role
    )
    db.add(user); db.commit(); db.refresh(user)
    return user


@app.post("/auth/token", response_model=TokenOut, tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "بيانات الدخول غير صحيحة")
    token = create_access_token(
        {"sub": user.email},
        timedelta(minutes=settings.access_token_expire_minutes)
    )
    return {"access_token": token, "user": user}


@app.get("/auth/me", response_model=UserOut, tags=["Auth"])
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ─────────────────────────────────────────────
# ② Companies Routes
# ─────────────────────────────────────────────
@app.post("/companies", tags=["Companies"])
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
):
    company = Company(**data.model_dump())
    db.add(company); db.commit(); db.refresh(company)
    return {"id": company.id, "name": company.name}


@app.post("/companies/{company_id}/financials", tags=["Companies"])
def add_financials(
    company_id: int,
    data: FinancialCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
):
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(404, "الشركة غير موجودة")
    fin = FinancialData(company_id=company_id, **data.model_dump())
    db.add(fin); db.commit()
    return {"message": f"تمت إضافة بيانات {data.year} بنجاح"}


@app.get("/companies/{company_id}", tags=["Companies"])
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "الشركة غير موجودة")
    return {
        "id": company.id,
        "name": company.name,
        "sector": company.sector,
        "market": company.market,
        "employees": company.employees,
        "financials": [
            {
                "year": f.year, "revenue": f.revenue, "ebitda": f.ebitda,
                "net_profit": f.net_profit, "total_debt": f.total_debt, "cash": f.cash
            }
            for f in company.financials
        ]
    }


@app.get("/companies", tags=["Companies"])
def list_companies(
    skip: int = 0, limit: int = 20,
    sector: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    q = db.query(Company)
    if sector:
        q = q.filter(Company.sector.ilike(f"%{sector}%"))
    companies = q.offset(skip).limit(limit).all()
    return [{"id": c.id, "name": c.name, "sector": c.sector, "market": c.market}
            for c in companies]


# ─────────────────────────────────────────────
# ③ Valuation Routes
# ─────────────────────────────────────────────
@app.post("/valuations", tags=["Valuations"])
def create_valuation(
    req: ValuationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.analyst))
):
    """تقييم شركة بالكامل باستخدام Claude AI مع حفظ النتائج في PostgreSQL"""

    company = db.query(Company).filter(Company.id == req.company_id).first()
    if not company:
        raise HTTPException(404, "الشركة غير موجودة")

    # فحص الكاش أولاً
    cache_key = Cache.valuation_key(req.company_id)
    if req.use_cache:
        cached = Cache.get(cache_key)
        if cached:
            return {**cached, "source": "cache"}

    financials = company.financials
    if len(financials) < 2:
        raise HTTPException(400, "يجب إدخال بيانات مالية لسنتين على الأقل")

    # بناء بيانات الشركة
    company_info = {
        "name": company.name,
        "sector": company.sector,
        "market": company.market,
        "employees": company.employees,
        "revenue_3y": [f.revenue for f in financials[-3:] if f.revenue],
        "ebitda_3y":  [f.ebitda  for f in financials[-3:] if f.ebitda],
        "net_debt": (financials[-1].total_debt or 0) - (financials[-1].cash or 0)
    }

    # استدعاء Claude
    try:
        ai_report = generate_valuation_report(company_info)
    except Exception as e:
        raise HTTPException(500, f"خطأ في Claude AI: {str(e)}")

    # حفظ في قاعدة البيانات
    methods = ai_report.get("methods", {})
    v_range = ai_report.get("valuation_range", {})

    valuation = Valuation(
        company_id   = company.id,
        created_by   = current_user.id,
        status       = ValuationStatus.completed,
        value_low    = v_range.get("low"),
        value_mid    = v_range.get("mid"),
        value_high   = v_range.get("high"),
        currency     = v_range.get("currency", "SAR"),
        dcf_value    = methods.get("dcf", {}).get("value"),
        dcf_assumptions = methods.get("dcf", {}).get("assumptions"),
        ebitda_multiple  = methods.get("ebitda_multiple", {}).get("multiple_used"),
        ebitda_mult_value= methods.get("ebitda_multiple", {}).get("value"),
        revenue_multiple = methods.get("revenue_multiple", {}).get("multiple_used"),
        revenue_mult_value=methods.get("revenue_multiple", {}).get("value"),
        ai_report    = ai_report,
        key_risks    = ai_report.get("key_risks", []),
        value_drivers= ai_report.get("value_drivers", []),
        recommendation = ai_report.get("recommendation")
    )
    db.add(valuation); db.commit(); db.refresh(valuation)

    result = {
        "valuation_id": valuation.id,
        "company": company.name,
        "valuation_range": v_range,
        "methods": methods,
        "key_risks": valuation.key_risks,
        "value_drivers": valuation.value_drivers,
        "recommendation": valuation.recommendation,
        "source": "ai"
    }

    # حفظ في الكاش (ساعة واحدة)
    Cache.set(cache_key, result, ttl=3600)
    return result


@app.get("/valuations/company/{company_id}", tags=["Valuations"])
def get_company_valuations(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    valuations = db.query(Valuation)\
        .filter(Valuation.company_id == company_id)\
        .order_by(Valuation.created_at.desc()).all()
    return [
        {
            "id": v.id,
            "status": v.status,
            "value_low": v.value_low,
            "value_mid": v.value_mid,
            "value_high": v.value_high,
            "currency": v.currency,
            "created_at": v.created_at
        }
        for v in valuations
    ]


# ─────────────────────────────────────────────
# ④ Chat Routes (Redis-backed)
# ─────────────────────────────────────────────
@app.post("/chat", tags=["Chat"])
def chat_with_expert(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """محادثة مع خبير التقييم — السياق محفوظ في Redis"""

    # إنشاء جلسة في DB إن لم تكن موجودة
    db_session = db.query(ChatSession)\
        .filter(ChatSession.session_key == req.session_id).first()
    if not db_session:
        db_session = ChatSession(
            user_id    = current_user.id,
            company_id = req.company_id,
            session_key= req.session_id,
            title      = req.message[:50]
        )
        db.add(db_session); db.commit(); db.refresh(db_session)

    # تحميل السياق من Redis
    history = ChatSessionStore.get_history(req.session_id)

    # إضافة سياق الشركة إن طُلب
    system = SYSTEM_PROMPT
    if req.company_id:
        company = db.query(Company).filter(Company.id == req.company_id).first()
        if company:
            financials_summary = ", ".join(
                f"{f.year}: إيرادات {f.revenue:,.0f}" for f in company.financials[-3:]
                if f.revenue
            )
            system += f"\n\nالشركة الحالية: {company.name} | القطاع: {company.sector}\nالبيانات المالية: {financials_summary}"

    # استدعاء Claude
    history.append({"role": "user", "content": req.message})
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        system=system,
        messages=history
    )
    reply = response.content[0].text

    # حفظ في Redis
    ChatSessionStore.append_message(req.session_id, "user", req.message)
    ChatSessionStore.append_message(req.session_id, "assistant", reply)

    # حفظ في DB
    db.add(ChatMessage(session_id=db_session.id, role="user",      content=req.message))
    db.add(ChatMessage(session_id=db_session.id, role="assistant", content=reply))
    db.commit()

    return {
        "session_id": req.session_id,
        "reply": reply,
        "turns": ChatSessionStore.get_turn_count(req.session_id)
    }


@app.delete("/chat/{session_id}", tags=["Chat"])
def reset_chat(
    session_id: str,
    _: User = Depends(get_current_user)
):
    ChatSessionStore.reset(session_id)
    return {"message": "تمت إعادة تعيين الجلسة"}


@app.get("/chat/{session_id}/history", tags=["Chat"])
def get_chat_history(
    session_id: str,
    _: User = Depends(get_current_user)
):
    return {
        "session_id": session_id,
        "history": ChatSessionStore.get_history(session_id)
    }


# ─────────────────────────────────────────────
# ⑤ Streaming Analysis
# ─────────────────────────────────────────────
@app.get("/valuations/{company_id}/stream", tags=["Valuations"])
def stream_company_analysis(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """تحليل مالي مع Streaming"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "الشركة غير موجودة")

    financial_lines = "\n".join(
        f"  {f.year}: إيرادات {f.revenue:,.0f} | EBITDA {f.ebitda:,.0f} | دين {f.total_debt:,.0f}"
        for f in company.financials if f.revenue
    )
    prompt = f"""قم بتحليل مالي شامل لشركة "{company.name}" (قطاع: {company.sector}):
{financial_lines}
يشمل: الأداء، النمو، الربحية، المخاطر، التوصية."""

    def generate():
        with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                yield text

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    from infrastructure import redis_client
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "healthy",
        "redis": "متصل" if redis_ok else "غير متصل",
        "version": "2.0.0"
    }


# ── Prompt Registry Router ───────────────────
from routers.prompts import router as prompts_router
app.include_router(prompts_router)

# ── Documents Router ─────────────────────────
from routers.documents import router as documents_router
app.include_router(documents_router)
