"""
services/prompt_manager.py
إدارة مركزية للـ Prompts — جلب / تصيير / تسجيل
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from models.prompt_models import PromptTemplate, PromptVersion, PromptUsageLog, PromptStatus
from infrastructure import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Master System Prompt (ثابت لجميع المراحل)
# ─────────────────────────────────────────────
MASTER_SYSTEM_PROMPT = """You are an AI assistant specialized in business valuation following International Valuation Standards (IVS) and International Financial Reporting Standards (IFRS).

CORE OPERATING PRINCIPLES:

1. ACCURACY & TRUTHFULNESS
   ▸ NEVER invent, assume, or extrapolate data beyond what is explicitly provided
   ▸ If information is missing, state: "Not available - requires additional data"
   ▸ If uncertain about interpretation, flag with confidence score < 0.8
   ▸ Always distinguish between facts (from data) and professional judgment

2. SOURCE CITATION
   ▸ For all extracted data, provide exact source location:
     - PDF: "Page X, Line Y" or "Page X, Section Title"
     - Excel: "Sheet 'Name', Cell B10" or "Sheet 'Name', Row 5"
     - Word: "Section X, Paragraph Y"
   ▸ For industry data, cite: "Source: [Report Name, Publisher, Date]"

3. CONFIDENCE SCORING
   ▸ Assign confidence score (0.0 to 1.0) for each extracted value:
     - 0.95–1.0:  Explicit, clear, unambiguous
     - 0.80–0.94: Clear but minor interpretation needed
     - 0.60–0.79: Some ambiguity, requires validation
     - < 0.60:    Highly uncertain, requires human review
   ▸ Any score < 0.8 MUST be flagged for human review

4. ARITHMETIC VERIFICATION
   ▸ Always verify fundamental accounting equations:
     - Balance Sheet: Total Assets = Total Liabilities + Total Equity
     - Income Statement: Gross Profit = Revenue - Cost of Goods Sold
     - Cash Flow: Ending Cash = Beginning Cash + Net Change
   ▸ Flag discrepancies > 1% as errors
   ▸ Flag discrepancies 0.1–1% as warnings (potential rounding)

5. OUTPUT FORMATTING
   ▸ For structured tasks: Output ONLY valid JSON, no additional text
   ▸ For narrative tasks: Use professional valuation language
   ▸ Always include metadata: date, version, assumptions, limitations

6. COMPLIANCE REFERENCES
   ▸ When selecting methodologies, reference:
     - IVS 105 (Valuation Approaches and Methods)
     - IVS 200 (Businesses and Business Interests)
     - IFRS 13 (Fair Value Measurement)
   ▸ When discussing discounts, reference empirical studies by name

7. PROFESSIONAL CONSERVATISM
   ▸ When faced with multiple reasonable interpretations, choose the more conservative
   ▸ Clearly state assumptions and their basis
   ▸ Highlight sensitivity to key assumptions
   ▸ Note limitations and qualifications

8. ANTI-HALLUCINATION CONTROLS
   ▸ DO NOT fill gaps with plausible but unverified data
   ▸ DO NOT generate benchmark data from general knowledge — request sources
   ▸ DO NOT create companies, studies, or citations that do not exist
   ▸ If asked to research, clearly state when using general knowledge vs. specific sources"""


# ─────────────────────────────────────────────
# PromptManager
# ─────────────────────────────────────────────
class PromptManager:
    """إدارة مركزية للـ Prompts — جلب، تصيير، تسجيل"""

    def __init__(self, db: Session):
        self.db     = db
        self._cache: Dict[str, PromptTemplate] = {}

    # ──────────────────────────────────────────
    # جلب Prompt
    # ──────────────────────────────────────────
    def get_prompt(
        self,
        prompt_key: str,
        version: Optional[str] = None,
        language: str = "en",
    ) -> Optional[PromptTemplate]:
        """
        جلب prompt معتمد من Registry.
        version=None → أحدث نسخة معتمدة.
        """
        cache_key = f"{prompt_key}:{version or 'latest'}:{language}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        q = self.db.query(PromptTemplate).filter(
            PromptTemplate.prompt_key == prompt_key,
            PromptTemplate.language   == language,
            PromptTemplate.status     == PromptStatus.approved,
        )
        if version:
            q = q.filter(PromptTemplate.version == version)
        else:
            q = q.order_by(PromptTemplate.created_at.desc())

        prompt = q.first()
        if not prompt:
            logger.error("Prompt غير موجود: %s v%s (%s)", prompt_key, version, language)
            return None

        self._cache[cache_key] = prompt
        return prompt

    # ──────────────────────────────────────────
    # تصيير Prompt
    # ──────────────────────────────────────────
    def render_prompt(
        self,
        prompt_key: str,
        variables: Dict,
        version: Optional[str] = None,
        language: str = "en",
    ) -> Dict:
        """
        تجهيز prompt جاهز للإرسال لـ Claude API.

        Returns:
            {system, user, model, temperature, max_tokens, prompt_metadata}

        Raises:
            ValueError: إذا لم يُعثر على الـ prompt أو فشل تعويض المتغيرات
        """
        template = self.get_prompt(prompt_key, version, language)
        if not template:
            raise ValueError(f"Prompt غير موجود أو غير معتمد: {prompt_key}")

        # FIX: تحقق من وجود جميع المتغيرات قبل التصيير
        try:
            user_prompt = template.user_prompt_template.format(**variables)
        except KeyError as e:
            missing = str(e).strip("'")
            raise ValueError(
                f"متغير مفقود في prompt '{prompt_key}': {{{missing}}}. "
                f"المتوقع: {_extract_placeholders(template.user_prompt_template)}"
            )

        # System Prompt: من Registry إن وُجد، وإلا Master الثابت
        system = template.system_prompt or MASTER_SYSTEM_PROMPT

        return {
            "system":      system,
            "user":        user_prompt,
            "model":       template.model_recommended or settings.claude_model,
            "temperature": float(template.temperature),
            "max_tokens":  template.max_tokens or settings.claude_max_tokens,
            "prompt_metadata": {
                "key":     template.prompt_key,
                "version": template.version,
                "stage":   str(template.stage) if template.stage else None,
            },
        }

    # ──────────────────────────────────────────
    # تسجيل الاستخدام
    # ──────────────────────────────────────────
    def log_usage(
        self,
        prompt_key: str,
        version: str,
        project_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        success: bool,
        error_message: Optional[str] = None,
    ):
        """تسجيل كل استدعاء Claude في جدول prompt_usage_log"""
        try:
            log = PromptUsageLog(
                prompt_key    = prompt_key,
                version       = version,
                project_id    = project_id,
                input_tokens  = input_tokens,
                output_tokens = output_tokens,
                cost_usd      = cost_usd,
                success       = success,
                error_message = error_message,
            )
            self.db.add(log)

            # تحديث عدد مرات الاستخدام
            template = self.get_prompt(prompt_key, version)
            if template:
                template.usage_count += 1
                template.last_used_at = datetime.now(timezone.utc)

            self.db.commit()
        except Exception as e:
            logger.error("فشل تسجيل استخدام الـ prompt: %s", e)
            self.db.rollback()

    # ──────────────────────────────────────────
    # إبطال الكاش
    # ──────────────────────────────────────────
    def invalidate_cache(self, prompt_key: Optional[str] = None):
        if prompt_key:
            self._cache = {k: v for k, v in self._cache.items()
                           if not k.startswith(prompt_key)}
        else:
            self._cache.clear()


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────
def _extract_placeholders(template: str) -> list[str]:
    """يستخرج أسماء المتغيرات {x} من قالب نصي"""
    import re
    return re.findall(r"\{(\w+)\}", template)
