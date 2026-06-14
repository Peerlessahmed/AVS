"""
routers/prompts.py
Prompt Registry governance — create / test / approve / rollback
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from infrastructure import get_db, decode_token
from fastapi.security import OAuth2PasswordBearer
from models import User, UserRole
from models.prompt_models import PromptTemplate, PromptVersion, PromptStatus, PromptStage
from services.prompt_manager import PromptManager
from services.claude_service_enhanced import ClaudeServiceEnhanced

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="توكن غير صالح")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="صلاحيات غير كافية — يتطلب admin")
    return current_user


# ── Schemas ──────────────────────────────────
class PromptCreate(BaseModel):
    prompt_key:           str = Field(..., pattern=r"^[a-z_]+\.[a-z_]+$")
    version:              str = Field(..., pattern=r"^v\d+\.\d+\.\d+$")
    user_prompt_template: str
    system_prompt:        Optional[str] = None
    stage:                PromptStage
    language:             str   = "en"
    model_recommended:    str   = "claude-sonnet-4-6"
    temperature:          float = Field(0.0, ge=0.0, le=1.0)
    max_tokens:           int   = Field(16000, ge=100, le=100000)

class PromptTestRequest(BaseModel):
    variables:  Dict
    project_id: str = "test"

class RollbackRequest(BaseModel):
    target_version: str


# ── List ─────────────────────────────────────
@router.get("")
def list_prompts(
    stage: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PromptTemplate)
    if stage:  q = q.filter(PromptTemplate.stage  == stage)
    if status: q = q.filter(PromptTemplate.status == status)
    prompts = q.order_by(PromptTemplate.prompt_key, PromptTemplate.created_at.desc()).all()
    return {
        "total": len(prompts),
        "prompts": [
            {"id": p.id, "prompt_key": p.prompt_key, "version": p.version,
             "stage": p.stage, "status": p.status, "usage_count": p.usage_count}
            for p in prompts
        ],
    }


# ── Create ────────────────────────────────────
@router.post("", status_code=201)
def create_prompt(
    data: PromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exists = db.query(PromptTemplate).filter_by(
        prompt_key=data.prompt_key, version=data.version, language=data.language
    ).first()
    if exists:
        raise HTTPException(409, f"الإصدار {data.version} موجود مسبقاً")

    from services.prompt_manager import MASTER_SYSTEM_PROMPT
    p = PromptTemplate(
        prompt_key=data.prompt_key, version=data.version,
        system_prompt=data.system_prompt or MASTER_SYSTEM_PROMPT,
        user_prompt_template=data.user_prompt_template,
        stage=data.stage, language=data.language,
        model_recommended=data.model_recommended,
        temperature=data.temperature, max_tokens=data.max_tokens,
        status=PromptStatus.draft, created_by=str(current_user.id),
    )
    db.add(p); db.commit(); db.refresh(p)
    return {"status": "created", "prompt_id": p.id, "prompt_key": p.prompt_key,
            "version": p.version, "requires_approval": True}


# ── Test ──────────────────────────────────────
@router.post("/{prompt_id}/test")
async def test_prompt(
    prompt_id: str, req: PromptTestRequest,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    p = _get_or_404(db, prompt_id)
    original = p.status
    p.status = PromptStatus.approved; db.commit()
    try:
        svc = ClaudeServiceEnhanced(db=db)
        result = await svc.execute_stage_prompt(
            prompt_key=p.prompt_key, variables=req.variables,
            project_id=req.project_id, version=p.version,
        )
    finally:
        p.status = original; db.commit()
    return {"test_passed": result["success"], "result": result,
            "ready_for_approval": result["success"]}


# ── Approve ───────────────────────────────────
@router.post("/{prompt_id}/approve")
def approve_prompt(
    prompt_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    p = _get_or_404(db, prompt_id)
    if p.status == PromptStatus.approved:
        raise HTTPException(400, "الـ prompt معتمد مسبقاً")
    snapshot = PromptVersion(
        prompt_key=p.prompt_key, version=p.version,
        content_snapshot={"system_prompt": p.system_prompt,
                          "user_prompt_template": p.user_prompt_template,
                          "metadata": {"stage": str(p.stage), "model": p.model_recommended,
                                       "temperature": float(p.temperature), "max_tokens": p.max_tokens}},
        created_by=str(current_user.id),
    )
    db.add(snapshot)
    p.status = PromptStatus.approved
    p.approved_by = str(current_user.id)
    p.approved_at = datetime.now(timezone.utc)
    db.commit()
    PromptManager(db).invalidate_cache(p.prompt_key)
    return {"status": "approved", "prompt_key": p.prompt_key, "version": p.version}


# ── Deprecate ─────────────────────────────────
@router.post("/{prompt_id}/deprecate")
def deprecate_prompt(
    prompt_id: str, db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    p = _get_or_404(db, prompt_id)
    p.status = PromptStatus.deprecated; db.commit()
    PromptManager(db).invalidate_cache(p.prompt_key)
    return {"status": "deprecated", "prompt_key": p.prompt_key}


# ── Rollback ──────────────────────────────────
@router.post("/{prompt_id}/rollback")
def rollback_prompt(
    prompt_id: str, req: RollbackRequest,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    p = _get_or_404(db, prompt_id)
    old = db.query(PromptVersion).filter_by(
        prompt_key=p.prompt_key, version=req.target_version
    ).first()
    if not old:
        raise HTTPException(404, f"الإصدار {req.target_version} غير موجود")
    p.status = PromptStatus.deprecated; db.commit()
    snap = old.content_snapshot
    restored = PromptTemplate(
        prompt_key=p.prompt_key, version=f"{req.target_version}-restored",
        system_prompt=snap.get("system_prompt"),
        user_prompt_template=snap["user_prompt_template"],
        stage=snap["metadata"].get("stage"),
        model_recommended=snap["metadata"].get("model"),
        temperature=snap["metadata"].get("temperature", 0.0),
        max_tokens=snap["metadata"].get("max_tokens", 16000),
        status=PromptStatus.approved,
        approved_by=str(current_user.id), approved_at=datetime.now(timezone.utc),
        created_by=str(current_user.id),
    )
    db.add(restored); db.commit(); db.refresh(restored)
    PromptManager(db).invalidate_cache(p.prompt_key)
    return {"status": "rolled_back", "new_version": restored.version}


# ── Usage stats ───────────────────────────────
@router.get("/{prompt_id}/usage")
def get_usage(
    prompt_id: str, db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from models.prompt_models import PromptUsageLog
    from sqlalchemy import func as sqlfunc
    p = _get_or_404(db, prompt_id)
    stats = db.query(
        sqlfunc.count(PromptUsageLog.id).label("calls"),
        sqlfunc.sum(PromptUsageLog.input_tokens).label("total_input"),
        sqlfunc.sum(PromptUsageLog.output_tokens).label("total_output"),
        sqlfunc.sum(PromptUsageLog.cost_usd).label("total_cost"),
    ).filter(PromptUsageLog.prompt_key == p.prompt_key).first()
    return {
        "prompt_key": p.prompt_key, "version": p.version,
        "calls": stats.calls or 0,
        "total_input_tokens": int(stats.total_input or 0),
        "total_output_tokens": int(stats.total_output or 0),
        "total_cost_usd": round(float(stats.total_cost or 0), 6),
    }


def _get_or_404(db, prompt_id):
    p = db.query(PromptTemplate).filter_by(id=prompt_id).first()
    if not p:
        raise HTTPException(404, "الـ Prompt غير موجود")
    return p
