"""
routers/documents.py
رفع ومعالجة المستندات المالية — Production-Ready
"""

import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from infrastructure import get_db
from services.extraction_service import (
    process_document,
    ALLOWED_MIME,
    MAX_FILE_SIZE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["documents"])

# مجلد مؤقت للملفات قبل المعالجة
TMP_DIR = Path("/tmp/valuation_uploads")
TMP_DIR.mkdir(parents=True, exist_ok=True)

VALID_STATEMENT_TYPES = {"auto", "income_statement", "balance_sheet", "cash_flow"}


# ─────────────────────────────────────────────
# FIX 1: التحقق المبكر قبل أي عملية I/O
# ─────────────────────────────────────────────
def _validate_upload(file: UploadFile):
    clean_mime = (file.content_type or "").split(";")[0].strip().lower()
    if clean_mime not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"نوع الملف غير مدعوم: {file.content_type}. المدعوم: PDF, Excel, Word, CSV"
        )
    if not file.filename:
        raise HTTPException(status_code=400, detail="اسم الملف مفقود")


# ─────────────────────────────────────────────
# POST /api/projects/{project_id}/upload-document
# ─────────────────────────────────────────────
@router.post("/{project_id}/upload-document", status_code=202)
async def upload_financial_document(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    statement_type: str = Query(
        default="auto",
        description="نوع القائمة المالية",
        pattern="^(auto|income_statement|balance_sheet|cash_flow)$"
    ),
    # FIX 2: استخدام dependency حقيقية بدلاً من استيراد مباشر
    db: Session = Depends(get_db),
):
    """
    رفع مستند مالي (PDF / Excel / Word / CSV) ومعالجته بـ Claude AI.

    - **project_id**: معرف المشروع
    - **statement_type**: auto = اكتشاف تلقائي لنوع القائمة
    - الاستجابة فورية (202 Accepted) والمعالجة في الخلفية
    """

    # ── FIX 3: التحقق من الـ MIME قبل قراءة الملف ──
    _validate_upload(file)

    # ── FIX 4: قراءة بحد أقصى 20MB — تحمي من هجمات الذاكرة ──
    file_id  = str(uuid.uuid4())
    tmp_path = TMP_DIR / f"{file_id}_{Path(file.filename).name}"

    try:
        total_bytes = 0
        with open(tmp_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):   # قراءة 1MB في كل دورة
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"حجم الملف يتجاوز الحد المسموح (20MB)"
                    )
                f.write(chunk)

        if total_bytes == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="الملف فارغ")

    except HTTPException:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        logger.error("فشل حفظ الملف المؤقت: %s", e)
        raise HTTPException(status_code=500, detail="فشل استقبال الملف")

    finally:
        await file.close()

    # ── FIX 5: معالجة في الخلفية — الرد فوري للمستخدم ──
    background_tasks.add_task(
        _process_in_background,
        file_id       = file_id,
        tmp_path      = str(tmp_path),
        file_type     = file.content_type,
        project_id    = project_id,
        statement_type= statement_type,
        original_name = file.filename,
        db            = db,
    )

    return JSONResponse(
        status_code=202,
        content={
            "message":    "تم استلام الملف وبدأت المعالجة",
            "file_id":    file_id,
            "filename":   file.filename,
            "size_bytes": total_bytes,
            "status":     "processing",
            # FIX 6: endpoint لمتابعة الحالة
            "status_url": f"/api/projects/{project_id}/documents/{file_id}",
        }
    )


# ─────────────────────────────────────────────
# معالجة الخلفية
# ─────────────────────────────────────────────
async def _process_in_background(
    file_id: str,
    tmp_path: str,
    file_type: str,
    project_id: str,
    statement_type: str,
    original_name: str,
    db: Session,
):
    """تُنفَّذ بعد إرسال الرد للعميل مباشرةً"""
    try:
        result = await process_document(
            file_path      = tmp_path,
            file_type      = file_type,
            project_id     = project_id,
            statement_type = statement_type,
            db             = db,
        )
        status = result.get("status", "unknown")
        logger.info("✅ اكتملت معالجة %s [%s] — حالة: %s", original_name, file_id, status)

    except Exception as e:
        logger.error("❌ فشلت معالجة %s [%s]: %s", original_name, file_id, e)
    finally:
        # تنظيف الملف المؤقت دائماً
        Path(tmp_path).unlink(missing_ok=True)


# ─────────────────────────────────────────────
# GET /api/projects/{project_id}/documents/{file_id}
# ─────────────────────────────────────────────
@router.get("/{project_id}/documents/{file_id}", tags=["documents"])
async def get_document_status(
    project_id: str,
    file_id: str,
    db: Session = Depends(get_db),
):
    """
    متابعة حالة معالجة مستند.
    يُستخدم بعد رفع الملف للتحقق من اكتمال الاستخراج.
    """
    try:
        from models import FinancialDocument
        doc = db.query(FinancialDocument).filter(
            FinancialDocument.id         == file_id,
            FinancialDocument.project_id == project_id,
        ).first()

        if not doc:
            raise HTTPException(404, "المستند غير موجود")

        return {
            "file_id":        doc.id,
            "original_name":  doc.original_name,
            "status":         doc.status,
            "statement_type": doc.statement_type,
            "confidence":     doc.confidence,
            "page_count":     doc.page_count,
            "processed_at":   doc.processed_at,
            "error_message":  doc.error_message,
            "data":           doc.extracted_data if doc.status == "completed" else None,
        }

    except HTTPException:
        raise
    except ImportError:
        # FinancialDocument لم يُضَف بعد إلى models.py
        raise HTTPException(501, "جدول المستندات غير مفعّل — أضف FinancialDocument إلى models.py")


# ─────────────────────────────────────────────
# GET /api/projects/{project_id}/documents
# ─────────────────────────────────────────────
@router.get("/{project_id}/documents", tags=["documents"])
async def list_project_documents(
    project_id: str,
    status: Optional[str] = Query(None, pattern="^(pending|processing|completed|failed)$"),
    db: Session = Depends(get_db),
):
    """قائمة مستندات المشروع مع فلترة اختيارية حسب الحالة"""
    try:
        from models import FinancialDocument
        q = db.query(FinancialDocument).filter(
            FinancialDocument.project_id == project_id
        )
        if status:
            q = q.filter(FinancialDocument.status == status)

        docs = q.order_by(FinancialDocument.created_at.desc()).all()
        return {
            "project_id": project_id,
            "total":      len(docs),
            "documents": [
                {
                    "file_id":        d.id,
                    "original_name":  d.original_name,
                    "status":         d.status,
                    "statement_type": d.statement_type,
                    "confidence":     d.confidence,
                    "created_at":     d.created_at,
                }
                for d in docs
            ],
        }
    except ImportError:
        raise HTTPException(501, "جدول المستندات غير مفعّل")
