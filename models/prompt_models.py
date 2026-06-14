"""
models/prompt_models.py
Prompt Registry DB models
"""

from sqlalchemy import (
    Column, String, Text, Integer, Float,
    Boolean, DateTime, JSON, ForeignKey, Enum as SAEnum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from models import Base


class PromptStatus(str, enum.Enum):
    draft      = "draft"
    approved   = "approved"
    deprecated = "deprecated"


class PromptStage(str, enum.Enum):
    extraction     = "extraction"
    analysis       = "analysis"
    questions      = "questions"
    assumptions    = "assumptions"
    methodology    = "methodology"
    research       = "research"
    comps          = "comps"
    dcf            = "dcf"
    discounts      = "discounts"
    reconciliation = "reconciliation"
    report         = "report"


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id                   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt_key           = Column(String(100), index=True, nullable=False)
    version              = Column(String(20), nullable=False)
    system_prompt        = Column(Text, nullable=True)
    user_prompt_template = Column(Text, nullable=False)
    stage                = Column(SAEnum(PromptStage), nullable=True)
    language             = Column(String(10), default="en")
    model_recommended    = Column(String(100), default="claude-sonnet-4-6")
    temperature          = Column(Float, default=0.0)
    max_tokens           = Column(Integer, default=16000)
    status               = Column(SAEnum(PromptStatus), default=PromptStatus.draft)
    approved_by          = Column(String(36), nullable=True)
    approved_at          = Column(DateTime(timezone=True), nullable=True)
    created_by           = Column(String(36), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    usage_count          = Column(Integer, default=0)
    last_used_at         = Column(DateTime(timezone=True), nullable=True)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt_key       = Column(String(100), nullable=False, index=True)
    version          = Column(String(20), nullable=False)
    content_snapshot = Column(JSON, nullable=False)
    change_notes     = Column(Text, nullable=True)
    created_by       = Column(String(36), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class PromptUsageLog(Base):
    __tablename__ = "prompt_usage_log"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt_key    = Column(String(100), nullable=False, index=True)
    version       = Column(String(20), nullable=False)
    project_id    = Column(String(36), nullable=True, index=True)
    input_tokens  = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd      = Column(Float, default=0.0)
    success       = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    executed_at   = Column(DateTime(timezone=True), server_default=func.now())
