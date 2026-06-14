"""
نماذج قاعدة البيانات - SQLAlchemy ORM
"""

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    Boolean, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    admin    = "admin"
    analyst  = "analyst"
    viewer   = "viewer"


class ValuationStatus(str, enum.Enum):
    draft      = "draft"
    processing = "processing"
    completed  = "completed"
    failed     = "failed"


# ── Users ────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String(255), unique=True, index=True, nullable=False)
    full_name    = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role         = Column(SAEnum(UserRole), default=UserRole.analyst)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    valuations   = relationship("Valuation", back_populates="created_by_user")
    sessions     = relationship("ChatSession", back_populates="user")


# ── Companies ────────────────────────────────
class Company(Base):
    __tablename__ = "companies"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(255), nullable=False)
    sector       = Column(String(100))
    market       = Column(String(100), default="المملكة العربية السعودية")
    description  = Column(Text)
    employees    = Column(Integer)
    founded_year = Column(Integer)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    financials   = relationship("FinancialData", back_populates="company",
                                order_by="FinancialData.year")
    valuations   = relationship("Valuation", back_populates="company")


# ── Financial Data ───────────────────────────
class FinancialData(Base):
    __tablename__ = "financial_data"

    id           = Column(Integer, primary_key=True, index=True)
    company_id   = Column(Integer, ForeignKey("companies.id"), nullable=False)
    year         = Column(Integer, nullable=False)
    revenue      = Column(Float)          # الإيرادات
    ebitda       = Column(Float)          # EBITDA
    net_profit   = Column(Float)          # صافي الربح
    total_assets = Column(Float)          # إجمالي الأصول
    total_debt   = Column(Float)          # إجمالي الديون
    cash         = Column(Float)          # النقد والمعادلات
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    company      = relationship("Company", back_populates="financials")


# ── Valuations ───────────────────────────────
class Valuation(Base):
    __tablename__ = "valuations"

    id              = Column(Integer, primary_key=True, index=True)
    company_id      = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=False)
    status          = Column(SAEnum(ValuationStatus), default=ValuationStatus.draft)

    # نتائج التقييم
    value_low       = Column(Float)
    value_mid       = Column(Float)
    value_high      = Column(Float)
    currency        = Column(String(10), default="SAR")

    # تفاصيل الطرق
    dcf_value           = Column(Float)
    dcf_assumptions     = Column(Text)
    ebitda_multiple     = Column(Float)
    ebitda_mult_value   = Column(Float)
    revenue_multiple    = Column(Float)
    revenue_mult_value  = Column(Float)

    # تقرير Claude الكامل
    ai_report       = Column(JSON)
    key_risks       = Column(JSON)          # قائمة المخاطر
    value_drivers   = Column(JSON)          # محركات القيمة
    recommendation  = Column(Text)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    company         = relationship("Company", back_populates="valuations")
    created_by_user = relationship("User", back_populates="valuations")


# ── Chat Sessions ────────────────────────────
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id  = Column(Integer, ForeignKey("companies.id"), nullable=True)
    session_key = Column(String(100), unique=True, index=True)  # مفتاح Redis
    title       = Column(String(255))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now())

    user        = relationship("User", back_populates="sessions")
    messages    = relationship("ChatMessage", back_populates="session",
                               order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id          = Column(Integer, primary_key=True, index=True)
    session_id  = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role        = Column(String(20), nullable=False)   # user | assistant
    content     = Column(Text, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    session     = relationship("ChatSession", back_populates="messages")


# ── Financial Documents ──────────────────────
class DocumentStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    completed  = "completed"
    failed     = "failed"


class StatementType(str, enum.Enum):
    income_statement = "income_statement"
    balance_sheet    = "balance_sheet"
    cash_flow        = "cash_flow"
    notes            = "notes"
    unknown          = "unknown"


class FinancialDocument(Base):
    __tablename__ = "financial_documents"

    id                = Column(String(36), primary_key=True)
    project_id        = Column(String(36), index=True, nullable=False)
    company_id        = Column(Integer, ForeignKey("companies.id"), nullable=True)
    original_name     = Column(String(500), nullable=False)
    storage_path      = Column(String(1000), nullable=False)
    file_size         = Column(Integer)
    mime_type         = Column(String(100))
    status            = Column(SAEnum(DocumentStatus), default=DocumentStatus.pending)
    statement_type    = Column(SAEnum(StatementType),  default=StatementType.unknown)
    error_message     = Column(Text, nullable=True)
    extracted_data    = Column(JSON, nullable=True)
    confidence        = Column(Float, nullable=True)
    page_count        = Column(Integer, nullable=True)
    validated         = Column(Boolean, default=False)
    validation_errors = Column(JSON, nullable=True)
    claude_message_id = Column(String(100), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    processed_at      = Column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", backref="documents")
