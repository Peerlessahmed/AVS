"""
خدمة Claude المركزية — Production-Ready
إصلاحات: نموذج صحيح، تكلفة دقيقة، retry، streaming، timeout، JSON آمن
"""

import json
import asyncio
import logging
from typing import Optional, Dict, List, AsyncIterator

from anthropic import AsyncAnthropic, APIStatusError, APITimeoutError, APIConnectionError

from infrastructure import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# أسعار النماذج (لكل مليون token)
# المصدر: https://www.anthropic.com/pricing
# ─────────────────────────────────────────────
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0},
    "claude-opus-4-6":   {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}

# ─────────────────────────────────────────────
# استثناءات مخصصة
# ─────────────────────────────────────────────
class ClaudeServiceError(Exception):
    """خطأ عام في خدمة Claude"""

class ClaudeJSONParseError(ClaudeServiceError):
    """فشل استخراج JSON من رد Claude"""
    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


# ─────────────────────────────────────────────
# ClaudeService
# ─────────────────────────────────────────────
class ClaudeService:
    """خدمة مركزية لكل تفاعلات Claude"""

    def __init__(self, api_key: str):
        # FIX 1: timeout صريح — بدونه يتجمد الطلب إلى الأبد
        self.client = AsyncAnthropic(api_key=api_key, timeout=60.0)
        self.usage_log: List[Dict] = []

    # ──────────────────────────────────────────
    # الاستدعاء الرئيسي
    # ──────────────────────────────────────────
    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        # FIX 2: يقرأ من settings بدلاً من قيم ثابتة مكررة
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: str = "json",   # "json" | "text"
        # FIX 3: retry مدمج لأخطاء الشبكة والـ rate limit
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> Dict:
        """
        استدعاء موحد لـ Claude مع retry ومعالجة أخطاء وتسجيل.

        Returns:
            {"success": True,  "data": ..., "usage": ..., "message_id": ...}
            {"success": False, "error": ..., "retries": ...}
        """
        _model       = model       or settings.claude_model
        _max_tokens  = max_tokens  or settings.claude_max_tokens
        _temperature = temperature if temperature is not None else settings.claude_temperature

        kwargs = {
            "model":      _model,
            "max_tokens": _max_tokens,
            "temperature": _temperature,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                message = await self.client.messages.create(**kwargs)

                usage = {
                    "input_tokens":  message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens,
                    "model":         _model,
                    # FIX 4: حساب التكلفة مباشرةً عند التسجيل
                    "cost_usd":      self._calc_cost(
                        _model,
                        message.usage.input_tokens,
                        message.usage.output_tokens
                    ),
                }
                self.usage_log.append(usage)

                response_text = message.content[0].text

                if response_format == "json":
                    try:
                        parsed = self._extract_json(response_text)
                    except ClaudeJSONParseError as e:
                        logger.error("فشل تحليل JSON | raw: %.200s", e.raw_text)
                        return {
                            "success":  False,
                            "error":    f"JSON parse error: {e}",
                            "raw_text": e.raw_text,
                            "usage":    usage,
                        }
                    return {
                        "success":    True,
                        "data":       parsed,
                        "raw_text":   response_text,
                        "usage":      usage,
                        "message_id": message.id,
                    }

                return {
                    "success":    True,
                    "data":       response_text,
                    "usage":      usage,
                    "message_id": message.id,
                }

            # FIX 5: تفريق أنواع الأخطاء — بعضها لا فائدة من إعادة المحاولة
            except APIStatusError as e:
                last_error = e
                if e.status_code in (400, 401, 403):
                    # خطأ دائم — لا تعيد المحاولة
                    logger.error("خطأ Claude دائم %s: %s", e.status_code, e.message)
                    break
                # 429 rate-limit أو 5xx → أعد المحاولة
                wait = retry_delay * attempt
                logger.warning("خطأ Claude %s (محاولة %d/%d) — انتظار %.1fs",
                               e.status_code, attempt, max_retries, wait)
                await asyncio.sleep(wait)

            except (APITimeoutError, APIConnectionError) as e:
                last_error = e
                wait = retry_delay * attempt
                logger.warning("خطأ شبكة (محاولة %d/%d) — انتظار %.1fs",
                               attempt, max_retries, wait)
                await asyncio.sleep(wait)

            except Exception as e:
                last_error = e
                logger.exception("خطأ غير متوقع في ClaudeService")
                break

        return {
            "success":  False,
            "error":    str(last_error),
            "retries":  max_retries,
        }

    # ──────────────────────────────────────────
    # Streaming
    # ──────────────────────────────────────────
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """
        مولّد async للردود المتدفقة — مناسب لـ FastAPI StreamingResponse.

        Usage:
            async for chunk in claude_service.stream("حلل هذه الشركة..."):
                yield chunk
        """
        _model       = model       or settings.claude_model
        _max_tokens  = max_tokens  or settings.claude_max_tokens
        _temperature = temperature if temperature is not None else settings.claude_temperature

        kwargs = {
            "model":       _model,
            "max_tokens":  _max_tokens,
            "temperature": _temperature,
            "messages":    [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    # ──────────────────────────────────────────
    # JSON Extractor
    # ──────────────────────────────────────────
    @staticmethod
    def _extract_json(text: str) -> Dict:
        """
        استخراج JSON من رد Claude بأمان.
        يدعم: JSON نظيف، ```json...```، ``` ... ```.
        """
        original = text

        # إزالة code fences
        if "```json" in text:
            start = text.find("```json") + 7
            end   = text.find("```", start)
            text  = text[start:end].strip() if end != -1 else text[start:].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end   = text.find("```", start)
            text  = text[start:end].strip() if end != -1 else text[start:].strip()

        # FIX 6: استخراج أول كائن/مصفوفة JSON في النص (يتجاوز نص تمهيدي)
        for opener, closer in [('{', '}'), ('[', ']')]:
            idx = text.find(opener)
            if idx != -1:
                # البحث عن الإغلاق الموافق
                depth, end_idx = 0, -1
                for i, ch in enumerate(text[idx:], start=idx):
                    if ch == opener:   depth += 1
                    elif ch == closer: depth -= 1
                    if depth == 0:
                        end_idx = i + 1
                        break
                if end_idx != -1:
                    candidate = text[idx:end_idx]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass

        raise ClaudeJSONParseError("لم يُعثر على JSON صالح في الرد", original)

    # ──────────────────────────────────────────
    # Cost & Stats
    # ──────────────────────────────────────────
    @staticmethod
    def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})
        return (
            (input_tokens  / 1_000_000) * pricing["input"] +
            (output_tokens / 1_000_000) * pricing["output"]
        )

    def get_total_cost(self) -> float:
        """التكلفة الإجمالية لكل الاستدعاءات في هذه الجلسة"""
        return sum(u["cost_usd"] for u in self.usage_log)

    def get_usage_summary(self) -> Dict:
        """ملخص الاستخدام: عدد الاستدعاءات + الـ tokens + التكلفة"""
        return {
            "calls":         len(self.usage_log),
            "total_input":   sum(u["input_tokens"]  for u in self.usage_log),
            "total_output":  sum(u["output_tokens"] for u in self.usage_log),
            "total_cost_usd": round(self.get_total_cost(), 6),
        }


# ─────────────────────────────────────────────
# Singleton — مثيل واحد للتطبيق
# ─────────────────────────────────────────────
claude_service = ClaudeService(api_key=settings.anthropic_api_key)
