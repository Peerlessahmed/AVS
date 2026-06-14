"""
services/validation_service.py
Anti-Hallucination Validator — التحقق من مخرجات Claude
"""

import re
import json
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Confidence tiers per Prompt Pack v1.0.0 (Section 0 — Principle 3)
CONFIDENCE_TIERS = {
    "explicit":     (0.95, 1.00),  # Clear, unambiguous
    "minor_interp": (0.80, 0.94),  # Minor interpretation needed
    "ambiguous":    (0.60, 0.79),  # Some ambiguity — validate
    "uncertain":    (0.00, 0.59),  # Highly uncertain — human review
}
CONFIDENCE_REVIEW_THRESHOLD = 0.80   # < 0.80 → flag for human review
ARITHMETIC_ERROR_THRESHOLD  = 0.01   # > 1%   → error
ARITHMETIC_WARN_THRESHOLD   = 0.001  # 0.1%–1% → warning (rounding)


class ClaudeOutputValidator:
    """
    التحقق من مخرجات Claude لمنع الهلوسة:
    1. قيم موجودة فعلاً في المستند المصدر
    2. درجات ثقة منخفضة → مراجعة بشرية
    3. صحة العلاقات الحسابية
    """

    def validate_extraction(
        self,
        claude_output: Dict,
        source_document: Dict,
    ) -> Dict:
        """
        يتحقق من أن البيانات المستخرجة موجودة في المستند الأصلي.

        Returns:
            {valid, errors, warnings, requires_human_review}
        """
        errors:   List[Dict] = []
        warnings: List[Dict] = []

        if not isinstance(claude_output, dict):
            return {
                "valid": False,
                "errors": [{"rule": "structure", "message": "المخرج ليس JSON صالح"}],
                "warnings": [],
                "requires_human_review": True,
            }

        # ── 1. تحقق من القيم في المصدر ────────
        source_numbers = self._extract_all_numbers(source_document)
        line_items     = claude_output.get("line_items", [])

        for item in line_items:
            value = item.get("value")
            if value is None or not isinstance(value, (int, float)):
                continue

            # ابحث عن أقرب قيمة في المصدر
            if source_numbers:
                closest = min(source_numbers, key=lambda x: abs(x - value))
                diff_pct = abs(closest - value) / value * 100 if value != 0 else 0

                if diff_pct > 5:    # فارق أكثر من 5%
                    errors.append({
                        "rule":                 "source_mismatch",
                        "item":                 item.get("standard_name"),
                        "extracted_value":      value,
                        "closest_in_source":    closest,
                        "difference_pct":       round(diff_pct, 2),
                        "severity":             "high" if diff_pct > 10 else "medium",
                        "possible_hallucination": True,
                    })
                elif diff_pct > 1:  # فارق تقريبي مقبول
                    warnings.append({
                        "rule":              "rounding_difference",
                        "item":              item.get("standard_name"),
                        "extracted_value":   value,
                        "closest_in_source": closest,
                        "difference_pct":    round(diff_pct, 2),
                    })

        # ── 2. تحقق من درجات الثقة ────────────
        low_conf = [
            item for item in line_items
            if item.get("confidence", 1.0) < CONFIDENCE_REVIEW_THRESHOLD
        ]
        if low_conf:
            warnings.append({
                "rule":   "low_confidence",
                "count":  len(low_conf),
                "items":  [i.get("standard_name") for i in low_conf],
                "action": "flag_for_human_review",
            })

        # ── 3. تحقق حسابي ─────────────────────
        arithmetic_errors = self._check_arithmetic(claude_output)
        errors.extend(arithmetic_errors)

        requires_review = len(errors) > 0 or len(low_conf) > 0

        return {
            "valid":                len(errors) == 0,
            "errors":               errors,
            "warnings":             warnings,
            "requires_human_review": requires_review,
        }

    # ──────────────────────────────────────────
    # استخراج الأرقام من المستند
    # ──────────────────────────────────────────
    @staticmethod
    def _extract_all_numbers(document: Dict) -> List[float]:
        """يستخرج كل الأرقام من المستند (نص + جداول)"""
        text    = json.dumps(document, ensure_ascii=False)
        pattern = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
        numbers = []
        for match in pattern.findall(text):
            try:
                numbers.append(float(match.replace(",", "")))
            except ValueError:
                pass
        return numbers

    # ──────────────────────────────────────────
    # فحوصات حسابية
    # ──────────────────────────────────────────
    @staticmethod
    def _check_arithmetic(data: Dict) -> List[Dict]:
        """
        يُفرّق بين خطأ (> 1%) وتحذير (0.1–1%) — per Prompt Pack v1.0.0 Principle 4
        """
        errors: List[Dict] = []

        items_dict = {
            item["standard_name"]: item["value"]
            for item in data.get("line_items", [])
            if item.get("value") is not None
        }

        # دمج بالأسماء العربية/الإنجليزية
        def get(*keys):
            for k in keys:
                if k in items_dict:
                    return items_dict[k]
            return None

        stmt_type = data.get("statement_type")

        # ── Balance Sheet: Assets = Liabilities + Equity ──
        if stmt_type == "balance_sheet":
            assets = get("Total Assets", "total_assets")
            liab   = get("Total Liabilities", "total_liabilities")
            equity = get("Total Equity", "total_equity")

            if all(v is not None for v in [assets, liab, equity]) and assets > 0:
                diff     = abs(assets - (liab + equity))
                diff_pct = diff / assets

                if diff_pct > ARITHMETIC_ERROR_THRESHOLD:
                    errors.append({
                        "rule":     "accounting_equation",
                        "severity": "high",
                        "type":     "error",
                        "message":  f"Assets ({assets:,.0f}) ≠ Liabilities ({liab:,.0f}) + Equity ({equity:,.0f}) | diff {diff_pct:.2%}",
                        "possible_hallucination": True,
                    })
                elif diff_pct > ARITHMETIC_WARN_THRESHOLD:
                    errors.append({
                        "rule":     "accounting_equation_rounding",
                        "severity": "low",
                        "type":     "warning",
                        "message":  f"Minor rounding in balance sheet: diff {diff:,.0f} ({diff_pct:.3%}) — likely rounding",
                        "possible_hallucination": False,
                    })

        # ── Income Statement: Gross Profit = Revenue − COGS ──
        elif stmt_type == "income_statement":
            revenue = get("Revenue", "revenue")
            cogs    = get("Cost of Goods Sold", "cost_of_goods_sold", "Cost of Sales")
            gross   = get("Gross Profit", "gross_profit")

            if revenue and gross and gross > revenue:
                errors.append({
                    "rule":     "gross_profit_exceeds_revenue",
                    "severity": "high",
                    "type":     "error",
                    "message":  f"Gross Profit ({gross:,.0f}) > Revenue ({revenue:,.0f})",
                    "possible_hallucination": True,
                })

            if all(v is not None for v in [revenue, cogs, gross]) and revenue > 0:
                expected = revenue - cogs
                diff_pct = abs(expected - gross) / revenue
                if diff_pct > ARITHMETIC_ERROR_THRESHOLD:
                    errors.append({
                        "rule":     "gross_profit_formula",
                        "severity": "high",
                        "type":     "error",
                        "message":  f"Gross Profit ({gross:,.0f}) ≠ Revenue ({revenue:,.0f}) − COGS ({cogs:,.0f}) = {expected:,.0f} | diff {diff_pct:.2%}",
                        "possible_hallucination": True,
                    })
                elif diff_pct > ARITHMETIC_WARN_THRESHOLD:
                    errors.append({
                        "rule":     "gross_profit_formula_rounding",
                        "severity": "low",
                        "type":     "warning",
                        "message":  f"Minor rounding: Gross Profit diff {diff_pct:.3%}",
                        "possible_hallucination": False,
                    })

        # ── Cash Flow: Ending Cash = Beginning Cash + Net Change ──
        elif stmt_type == "cash_flow":
            op  = get("Operating Cash Flow",  "operating_cash_flow")
            inv = get("Investing Cash Flow",  "investing_cash_flow")
            fin = get("Financing Cash Flow",  "financing_cash_flow")
            net = get("Net Change in Cash",   "net_change_in_cash")
            beg = get("Beginning Cash",       "beginning_cash")
            end = get("Ending Cash",          "ending_cash")

            if all(v is not None for v in [op, inv, fin, net]):
                calculated = op + inv + fin
                diff       = abs(calculated - net)
                base       = max(abs(net), 1)
                diff_pct   = diff / base

                if diff_pct > ARITHMETIC_ERROR_THRESHOLD:
                    errors.append({
                        "rule":     "cash_flow_sum",
                        "severity": "medium",
                        "type":     "error",
                        "message":  f"Op+Inv+Fin ({calculated:,.0f}) ≠ Net Change ({net:,.0f}) | diff {diff_pct:.2%}",
                        "possible_hallucination": True,
                    })
                elif diff_pct > ARITHMETIC_WARN_THRESHOLD:
                    errors.append({
                        "rule":     "cash_flow_sum_rounding",
                        "severity": "low",
                        "type":     "warning",
                        "message":  f"Minor rounding in cash flow sum: diff {diff_pct:.3%}",
                        "possible_hallucination": False,
                    })

            if all(v is not None for v in [beg, end, net]):
                expected = beg + net
                diff_pct = abs(expected - end) / max(abs(end), 1)
                if diff_pct > ARITHMETIC_ERROR_THRESHOLD:
                    errors.append({
                        "rule":     "ending_cash_check",
                        "severity": "medium",
                        "type":     "error",
                        "message":  f"Ending Cash ({end:,.0f}) ≠ Beginning ({beg:,.0f}) + Net Change ({net:,.0f}) = {expected:,.0f}",
                        "possible_hallucination": True,
                    })

        return errors
