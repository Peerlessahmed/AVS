"""
services/claude_service_enhanced.py
خدمة Claude محسّنة — Prompt Registry + Validation + Chunking
"""

import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from claude_service import claude_service, ClaudeServiceError
from services.prompt_manager import PromptManager, MASTER_SYSTEM_PROMPT
from services.validation_service import ClaudeOutputValidator
from infrastructure import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# ClaudeServiceEnhanced
# ─────────────────────────────────────────────
class ClaudeServiceEnhanced:
    """
    خدمة Claude مع:
    - Prompt Registry (جلب من DB)
    - تتبع الإصدارات
    - تسجيل الاستخدام والتكلفة
    - Anti-hallucination validation
    """

    def __init__(self, db: Session):
        self.db             = db
        self.prompt_manager = PromptManager(db)
        self.validator      = ClaudeOutputValidator()

    async def execute_stage_prompt(
        self,
        prompt_key: str,
        variables: Dict,
        project_id: str,
        version: Optional[str] = None,
        language: str = "en",
        validate: bool = True,
        source_document: Optional[Dict] = None,
    ) -> Dict:
        """
        تنفيذ prompt مرحلي مع تتبع كامل.

        Args:
            prompt_key:      مفتاح الـ prompt في Registry (e.g. 'extraction.financial_statements')
            variables:       قاموس متغيرات {placeholder: value}
            project_id:      معرف المشروع للتسجيل
            version:         إصدار محدد (None = أحدث معتمد)
            language:        'en' | 'ar'
            validate:        تشغيل anti-hallucination validation
            source_document: المستند الأصلي للمقارنة (لـ validate=True)
        """

        # ── 1. جلب وتصيير الـ Prompt ──────────
        try:
            prompt_config = self.prompt_manager.render_prompt(
                prompt_key = prompt_key,
                variables  = variables,
                version    = version,
                language   = language,
            )
        except ValueError as e:
            logger.error("فشل تصيير الـ prompt: %s", e)
            return {"success": False, "error": f"Prompt error: {e}"}

        # ── 2. استدعاء Claude ─────────────────
        result = await claude_service.call(
            prompt          = prompt_config["user"],
            system_prompt   = prompt_config["system"],
            model           = prompt_config["model"],
            max_tokens      = prompt_config["max_tokens"],
            temperature     = prompt_config["temperature"],
            response_format = "json",
        )

        # ── 3. تسجيل الاستخدام دائماً ─────────
        usage = result.get("usage", {})
        self.prompt_manager.log_usage(
            prompt_key    = prompt_key,
            version       = prompt_config["prompt_metadata"]["version"],
            project_id    = project_id,
            input_tokens  = usage.get("input_tokens", 0),
            output_tokens = usage.get("output_tokens", 0),
            cost_usd      = usage.get("cost_usd", 0.0),
            success       = result["success"],
            error_message = result.get("error"),
        )

        if not result["success"]:
            return result

        # ── 4. Anti-hallucination validation ──
        validation = {"valid": True, "errors": [], "warnings": []}
        if validate and source_document:
            validation = self.validator.validate_extraction(
                result["data"], source_document
            )
            if not validation["valid"]:
                logger.warning(
                    "Prompt '%s': %d أخطاء تحقق",
                    prompt_key, len(validation["errors"])
                )

        return {
            "success":    True,
            "data":       result["data"],
            "validation": validation,
            "metadata": {
                "prompt_key":     prompt_key,
                "prompt_version": prompt_config["prompt_metadata"]["version"],
                "stage":          prompt_config["prompt_metadata"]["stage"],
                "model":          prompt_config["model"],
                "message_id":     result.get("message_id"),
                "input_tokens":   usage.get("input_tokens", 0),
                "output_tokens":  usage.get("output_tokens", 0),
                "cost_usd":       usage.get("cost_usd", 0.0),
                "stop_reason":    result.get("stop_reason"),
            },
        }

    async def execute_text_prompt(
        self,
        prompt_key: str,
        variables: Dict,
        project_id: str,
        version: Optional[str] = None,
        language: str = "en",
    ) -> Dict:
        """نفس execute_stage_prompt لكن للردود النصية (تقارير، ملخصات)"""
        try:
            prompt_config = self.prompt_manager.render_prompt(
                prompt_key, variables, version, language
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}

        result = await claude_service.call(
            prompt          = prompt_config["user"],
            system_prompt   = prompt_config["system"],
            model           = prompt_config["model"],
            max_tokens      = prompt_config["max_tokens"],
            temperature     = prompt_config["temperature"],
            response_format = "text",
        )

        usage = result.get("usage", {})
        self.prompt_manager.log_usage(
            prompt_key    = prompt_key,
            version       = prompt_config["prompt_metadata"]["version"],
            project_id    = project_id,
            input_tokens  = usage.get("input_tokens", 0),
            output_tokens = usage.get("output_tokens", 0),
            cost_usd      = usage.get("cost_usd", 0.0),
            success       = result["success"],
            error_message = result.get("error"),
        )

        return {**result, "metadata": prompt_config["prompt_metadata"]}


# ─────────────────────────────────────────────
# DocumentChunker
# ─────────────────────────────────────────────
MAX_CHUNK_TOKENS = 50_000
CHARS_PER_TOKEN  = 4   # تقريب: 1 token ≈ 4 حروف


class DocumentChunker:
    """تقسيم المستندات الكبيرة إلى أجزاء تناسب Context Window"""

    def chunk_document(self, document_data: Dict) -> List[Dict]:
        """
        يقسّم المستند إلى أجزاء لا يتجاوز كل منها MAX_CHUNK_TOKENS.
        يعيد قائمة من chunks، كل منها dict بنفس هيكل document_data.
        """
        doc_type = document_data.get("type", "unknown")

        if doc_type == "pdf":
            return self._chunk_pdf(document_data)
        elif doc_type == "excel":
            return self._chunk_excel(document_data)
        else:
            # نصوص أخرى: قسّم بحسب الحجم
            return self._chunk_text(document_data)

    def _chunk_pdf(self, doc: Dict) -> List[Dict]:
        """تقسيم PDF بحسب الصفحات"""
        full_text  = doc.get("text", "")
        all_tables = doc.get("tables", [])

        # استخراج الصفحات من النص
        import re
        page_pattern = re.compile(r"--- صفحة (\d+) ---\n(.*?)(?=--- صفحة|\Z)", re.DOTALL)
        pages = [
            {"number": int(m.group(1)), "text": m.group(2).strip()}
            for m in page_pattern.finditer(full_text)
        ]

        if not pages:
            # نص غير مقسّم — chunk بحسب الحجم
            return self._chunk_text(doc)

        chunks: List[Dict] = []
        current_pages: List[Dict] = []
        current_chars = 0

        for page in pages:
            page_chars = len(page["text"])
            if current_chars + page_chars > MAX_CHUNK_TOKENS * CHARS_PER_TOKEN and current_pages:
                chunks.append(self._build_pdf_chunk(current_pages, all_tables, doc))
                current_pages = []
                current_chars = 0
            current_pages.append(page)
            current_chars += page_chars

        if current_pages:
            chunks.append(self._build_pdf_chunk(current_pages, all_tables, doc))

        logger.info("PDF مقسّم إلى %d جزء", len(chunks))
        return chunks

    def _build_pdf_chunk(self, pages: List[Dict], all_tables: List, doc: Dict) -> Dict:
        page_nums = {p["number"] for p in pages}
        text      = "\n\n".join(
            f"--- صفحة {p['number']} ---\n{p['text']}" for p in pages
        )
        tables    = [t for t in all_tables if t.get("page") in page_nums]
        return {
            "type":       "pdf",
            "text":       text,
            "tables":     tables,
            "page_range": f"{min(page_nums)}-{max(page_nums)}",
            "page_count": len(pages),
        }

    def _chunk_excel(self, doc: Dict) -> List[Dict]:
        """كل ورقة Excel تصبح chunk مستقل"""
        sheets = doc.get("sheets", {})
        if not sheets:
            return [doc]

        chunks = []
        for sheet_name, sheet_data in sheets.items():
            sheet_text = f"[ورقة: {sheet_name}]\n"
            for row in sheet_data.get("data", []):
                sheet_text += " | ".join(str(v) for v in row.values() if v != "") + "\n"

            chunks.append({
                "type":       "excel",
                "text":       sheet_text,
                "sheets":     {sheet_name: sheet_data},
                "tables":     [],
                "page_count": 1,
                "sheet_name": sheet_name,
            })

        return chunks

    def _chunk_text(self, doc: Dict) -> List[Dict]:
        """تقسيم نص عام بحسب الحجم"""
        text       = doc.get("text", "")
        max_chars  = MAX_CHUNK_TOKENS * CHARS_PER_TOKEN
        chunks     = []
        for i in range(0, len(text), max_chars):
            chunk_text = text[i:i + max_chars]
            chunks.append({**doc, "text": chunk_text, "chunk_index": i // max_chars})
        return chunks or [doc]

    async def extract_from_chunks(
        self,
        chunks: List[Dict],
        claude_enhanced: ClaudeServiceEnhanced,
        project_id: str,
        statement_type: str = "auto",
    ) -> Dict:
        """
        يستخرج من كل chunk ويدمج النتائج مع إزالة التكرار.
        """
        all_line_items: List[Dict] = []
        metadata: Dict = {}
        chunks_ok = 0

        for i, chunk in enumerate(chunks):
            logger.info("معالجة chunk %d/%d", i + 1, len(chunks))
            result = await claude_enhanced.execute_stage_prompt(
                prompt_key = "extraction.financial_statements",
                variables  = {
                    "document_content": json.dumps(chunk, ensure_ascii=False),
                    "statement_type":   statement_type,
                },
                project_id = project_id,
            )

            if result["success"]:
                data = result["data"]
                all_line_items.extend(data.get("line_items", []))
                if i == 0:
                    metadata = data.get("metadata", {})
                    metadata["statement_type"] = data.get("statement_type")
                    metadata["period_end"]     = data.get("period_end")
                    metadata["currency"]       = data.get("currency", "SAR")
                chunks_ok += 1
            else:
                logger.warning("فشل chunk %d: %s", i + 1, result.get("error"))

        return {
            "statement_type":   metadata.get("statement_type"),
            "period_end":       metadata.get("period_end"),
            "currency":         metadata.get("currency", "SAR"),
            "line_items":       self._deduplicate(all_line_items),
            "metadata":         metadata,
            "chunks_processed": chunks_ok,
            "chunks_total":     len(chunks),
        }

    @staticmethod
    def _deduplicate(items: List[Dict]) -> List[Dict]:
        """يُبقي على القيمة ذات الثقة الأعلى لكل بند"""
        seen: Dict[str, Dict] = {}
        for item in items:
            key = item.get("standard_name", "")
            if key not in seen or item.get("confidence", 0) > seen[key].get("confidence", 0):
                seen[key] = item
        return list(seen.values())
