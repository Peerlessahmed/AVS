"""
scripts/seed_prompts.py
Prompt Pack v1.0.0 — كامل من وثيقة المتطلبات
11 مرحلة + Master System Prompt

تشغيل: python scripts/seed_prompts.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure import SessionLocal
from models.prompt_models import PromptTemplate, PromptStatus, PromptStage
from services.prompt_manager import MASTER_SYSTEM_PROMPT

db = SessionLocal()

VERSION = "v1.0.0"

def upsert(key, stage, user_template, temperature=0.0, max_tokens=16000):
    existing = db.query(PromptTemplate).filter_by(
        prompt_key=key, version=VERSION, language="en"
    ).first()
    if existing:
        existing.user_prompt_template = user_template
        existing.system_prompt        = MASTER_SYSTEM_PROMPT
        existing.status               = PromptStatus.approved
        print(f"  🔄  {key}")
    else:
        db.add(PromptTemplate(
            prompt_key           = key,
            version              = VERSION,
            system_prompt        = MASTER_SYSTEM_PROMPT,
            user_prompt_template = user_template,
            stage                = stage,
            language             = "en",
            model_recommended    = "claude-sonnet-4-6",
            temperature          = temperature,
            max_tokens           = max_tokens,
            status               = PromptStatus.approved,
            created_by           = "system",
        ))
        print(f"  ✅  {key}")


# ══════════════════════════════════════════════════════════
# PROMPT 1.1 — EXTRACT_FINANCIAL_STATEMENTS
# ══════════════════════════════════════════════════════════
def p1_extraction():
    upsert(
        key   = "extraction.financial_statements",
        stage = PromptStage.extraction,
        user_template = """Extract financial statement data from the provided document.

**Input**:
- {{document_content}}: {document_content}
- {{statement_type}}: {statement_type}

**Task** — Follow this exact process:

1. IDENTIFY STATEMENT TYPE
   ▸ Determine: income_statement | balance_sheet | cash_flow
   ▸ If statement_type = 'auto', auto-detect from content
   ▸ confidence = 1.0 if headers clearly state type, < 0.9 if inferred

2. EXTRACT REPORTING PERIOD
   ▸ period_end: YYYY-MM-DD (1.0 if explicit, < 0.8 if inferred)
   ▸ period_start if mentioned

3. EXTRACT CURRENCY
   ▸ Use ISO codes: USD, EUR, SAR — default 'UNKNOWN' if not found

4. EXTRACT LINE ITEMS — for each item:
   ▸ category:         Revenue | Cost of Sales | Gross Profit | Operating Expenses | EBITDA | Net Income | Assets | Liabilities | Equity | Cash Flow
   ▸ standard_name:    English GAAP term (Revenue, Cost of Goods Sold, Total Assets…)
   ▸ original_name:    Exact text from document (preserve Arabic/English)
   ▸ value:            Number only — remove commas/symbols, preserve sign (negatives)
   ▸ source_location:  "Page X, Line Y" or "Sheet 'Name', Cell B10"
   ▸ confidence:       0.95–1.0 clear | 0.80–0.94 minor interpretation | < 0.80 flag
   ▸ notes:            "Value in thousands", "Blurred text", etc.

5. VERIFY ARITHMETIC
   ▸ Balance Sheet: Assets = Liabilities + Equity (flag > 1% diff as error, 0.1–1% as warning)
   ▸ Income Statement: Gross Profit = Revenue − COGS

**Output** (JSON ONLY — zero text outside JSON):
{{
  "statement_type": "income_statement",
  "period_end": "2024-12-31",
  "period_start": "2024-01-01",
  "currency": "SAR",
  "line_items": [
    {{
      "category": "Revenue",
      "standard_name": "Revenue",
      "original_name": "إجمالي الإيرادات",
      "value": 10000000,
      "source_location": "Page 2, Line 5",
      "confidence": 0.98,
      "notes": ""
    }}
  ],
  "metadata": {{
    "company_name": "",
    "fiscal_year": 2024,
    "audited": true,
    "auditor": "",
    "document_pages": 0
  }},
  "warnings": []
}}

**Critical Rules**:
- confidence < 0.8 → add explanatory note
- Missing arithmetic balance → add specific warning with amounts
- Missing period or currency → state in warnings
- NEVER invent values — omit missing line items entirely"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 2.1 — ANALYZE_HISTORICAL_TRENDS
# ══════════════════════════════════════════════════════════
def p2_analysis():
    upsert(
        key   = "analysis.historical_trends",
        stage = PromptStage.analysis,
        user_template = """Analyze multi-period financial data to identify trends, anomalies, and insights.

**Input**:
- {{historical_data}}: {historical_data}
- {{calculated_kpis}}: {calculated_kpis}

**Task** — Analyze across these dimensions:

REVENUE: trend (growing|declining|stable|volatile), CAGR, key drivers, concerns
PROFITABILITY: margin trends (gross/operating/net) — improving|declining|stable, cost insights
EFFICIENCY: working capital (DSO, inventory turnover, DPO), asset utilization
LIQUIDITY: position (strong|adequate|weak), trend, cash flow observations
ANOMALIES: metric, period, quantified observation, plausible causes, severity (high|medium|low)
QUESTIONS FOR MANAGEMENT: 5–10 specific questions to clarify anomalies
FORECAST CONSIDERATIONS: key factors for building forward projections

**Output** (JSON ONLY):
{{
  "executive_summary": "2–3 sentence overview of financial trajectory",
  "revenue_analysis": {{
    "trend": "growing",
    "cagr": 0.0,
    "cagr_assessment": "",
    "drivers": [],
    "concerns": []
  }},
  "profitability_analysis": {{
    "margin_trends": {{
      "gross_margin": "stable",
      "operating_margin": "declining",
      "net_margin": "declining"
    }},
    "key_insights": []
  }},
  "efficiency_analysis": {{
    "dso_trend": "",
    "inventory_trend": "",
    "asset_utilization": "",
    "concerns": []
  }},
  "liquidity_analysis": {{
    "current_position": "adequate",
    "trend": "stable",
    "cash_flow_observations": []
  }},
  "anomalies": [
    {{
      "metric": "",
      "period": "",
      "observation": "",
      "possible_causes": [],
      "severity": "high"
    }}
  ],
  "questions_for_management": [],
  "forecast_considerations": []
}}

**Rules**: Base ONLY on provided data. Do not cite industry benchmarks unless given.
Distinguish observations (facts) from hypotheses (possible causes)."""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 3.1 — GENERATE_MANAGEMENT_QUESTIONS
# ══════════════════════════════════════════════════════════
def p3_questions():
    upsert(
        key   = "questions.management_qa",
        stage = PromptStage.questions,
        user_template = """Generate 15–20 prioritized management interview questions for valuation due diligence.

**Input**:
- {{analysis_insights}}: {analysis_insights}
- {{company_context}}: {company_context}
- {{kpis}}: {kpis}

**Categories**: Historical Performance | Strategic Direction | Market & Competition | Operations | Financial | Risk Factors

**For each question provide**:
▸ priority:           high | medium | low
▸ category:           one of the six above
▸ question:           specific, quantified where possible
▸ rationale:          why it matters for valuation
▸ follow_ups:         2–3 sub-questions
▸ linked_kpi:         metric name (snake_case)
▸ impact_on_valuation: High|Medium|Low + brief explanation

**Output** (JSON ONLY):
{{
  "questions_by_priority": [
    {{
      "priority": "high",
      "category": "Historical Performance",
      "question": "",
      "rationale": "",
      "follow_ups": [],
      "linked_kpi": "",
      "impact_on_valuation": ""
    }}
  ],
  "suggested_interview_flow": [
    "Start with historical performance to build rapport",
    "Transition to strategic direction and growth plans",
    "Discuss market positioning and competition",
    "Address operational initiatives",
    "Close with risk factors and challenges"
  ],
  "key_assumptions_to_validate": []
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 4.1 — UPDATE_ASSUMPTIONS_FROM_QA
# ══════════════════════════════════════════════════════════
def p4_assumptions():
    upsert(
        key   = "assumptions.update_from_qa",
        stage = PromptStage.assumptions,
        user_template = """Revise financial forecast assumptions based on management interview responses.

**Input**:
- {{current_assumptions}}: {current_assumptions}
- {{qa_answers}}: {qa_answers}

**Principles**:
▸ EXPLICIT GUIDANCE: incorporate direct quantitative statements with Q&A citation
▸ IMPLIED ASSUMPTIONS: mark clearly as "inferred" vs "stated"
▸ CONSISTENCY: compare to historical trends, flag optimistic vs conservative scenarios
▸ CONSERVATISM: use midpoint or conservative end when range is given

**Output** (JSON ONLY):
{{
  "updated_assumptions": {{
    "revenue_growth": {{
      "2026": 0.0,
      "2027": 0.0,
      "2028": 0.0,
      "2029": 0.0,
      "2030": 0.0,
      "basis": "stated | inferred — explanation",
      "source": "Q&A #X: quote",
      "confidence": "high | medium | low",
      "risks": [],
      "vs_historical": ""
    }},
    "gross_margin": {{
      "2026": 0.0, "2027": 0.0, "2028": 0.0, "2029": 0.0, "2030": 0.0,
      "basis": "", "source": "", "confidence": "", "risks": [], "vs_historical": ""
    }},
    "ebitda_margin": {{
      "2026": 0.0, "2027": 0.0, "2028": 0.0, "2029": 0.0, "2030": 0.0,
      "basis": "", "source": "", "confidence": "", "risks": [], "vs_historical": ""
    }},
    "capex_pct_revenue": {{
      "value": 0.0, "basis": "", "source": "", "confidence": ""
    }}
  }},
  "changes_from_baseline": [
    {{
      "assumption": "",
      "old_value": "",
      "new_value": "",
      "reason": "",
      "materiality": "high | medium | low"
    }}
  ],
  "unresolved_items": [],
  "red_flags": []
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 5.1 — SELECT_VALUATION_METHODOLOGY
# ══════════════════════════════════════════════════════════
def p5_methodology():
    upsert(
        key   = "methodology.selection",
        stage = PromptStage.methodology,
        user_template = """Determine the most appropriate valuation methodology per IVS 105 hierarchy.

**Input**:
- {{company_profile}}: {company_profile}
- {{financial_summary}}: {financial_summary}
- {{valuation_purpose}}: {valuation_purpose}

**Methodology Options**:
INCOME APPROACH: DCF, Capitalization of Earnings — stable/predictable cash flows
MARKET APPROACH: Guideline Public Company (Trading Comps), Precedent Transactions — comparable data available
COST APPROACH: Adjusted Net Asset Value — asset-intensive or liquidation

**Evaluation Criteria**: data availability & reliability | nature of cash flows | valuation purpose | comparability | business lifecycle stage

**Output** (JSON ONLY):
{{
  "primary_methodology": {{
    "approach": "Income Approach",
    "method": "Discounted Cash Flow (DCF)",
    "justification": "",
    "ivs_reference": "IVS 105 Para ...",
    "ifrs_reference": "IFRS 13 Para ...",
    "suitability_score": 0.0,
    "key_requirements": []
  }},
  "secondary_methodology": {{
    "approach": "",
    "method": "",
    "justification": "",
    "role": "Corroboration / Sanity check",
    "suitability_score": 0.0,
    "limitations": []
  }},
  "rejected_methodologies": [
    {{"approach": "", "reason": ""}}
  ],
  "weighting_recommendation": {{
    "primary_weight": 75,
    "secondary_weight": 25,
    "rationale": ""
  }},
  "compliance_summary": ""
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 6.1 — CONDUCT_INDUSTRY_RESEARCH
# ══════════════════════════════════════════════════════════
def p6_research():
    upsert(
        key   = "research.industry_analysis",
        stage = PromptStage.research,
        user_template = """Research and summarize industry context for valuation purposes.

**Input**:
- {{industry}}: {industry}
- {{geography}}: {geography}
- {{company_name}}: {company_name}

**Cover**:
OVERVIEW: market size & CAGR (historical 5yr, projected 5yr), key drivers, challenges
BENCHMARKS: revenue growth (median, P25, P75), margins (gross/EBITDA/net), multiples (EV/Revenue, EV/EBITDA), working capital metrics
COMPETITIVE LANDSCAPE: market structure, key players, barriers to entry
OUTLOOK: growth forecast, emerging trends, key risks

**Output** (JSON ONLY):
{{
  "industry_overview": {{
    "description": "",
    "market_size": {{
      "current": {{"value": 0, "unit": "USD billions", "year": 2024}},
      "historical_cagr_5yr": 0.0,
      "projected_cagr_5yr": 0.0
    }},
    "key_drivers": [],
    "challenges": [],
    "sources": []
  }},
  "benchmarks": {{
    "revenue_growth": {{"median": 0.0, "percentile_25": 0.0, "percentile_75": 0.0}},
    "gross_margin":   {{"median": 0.0, "range": [0, 0]}},
    "ebitda_margin":  {{"median": 0.0, "range": [0, 0]}},
    "valuation_multiples": {{
      "ev_revenue": {{"median": 0.0, "range": [0.0, 0.0]}},
      "ev_ebitda":  {{"median": 0.0, "range": [0.0, 0.0]}}
    }},
    "sources": [],
    "data_quality_note": ""
  }},
  "competitive_landscape": {{
    "market_structure": "fragmented | concentrated",
    "key_players": [],
    "barriers_to_entry": []
  }},
  "outlook": {{
    "growth_forecast": "",
    "key_trends": [],
    "risk_factors": []
  }},
  "data_sources_disclaimer": "Clearly state: general knowledge vs specific sources. Do not fabricate reports or studies."
}}

**CRITICAL**: Always state when using general knowledge vs specific sources."""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 7.1 — SELECT_COMPARABLE_COMPANIES
# ══════════════════════════════════════════════════════════
def p7_comps():
    upsert(
        key   = "comps.selection",
        stage = PromptStage.comps,
        user_template = """Select 3–5 best comparable companies from a pre-screened candidate list.

**Input**:
- {{target_company}}: {target_company}
- {{candidate_comps}}: {candidate_comps}

**Selection Criteria** (weighted):
1. Business Model Similarity (35%) — revenue model, customer base, value proposition
2. Growth Profile (25%) — similar growth rates and lifecycle stage
3. Geographic Exposure (15%) — similar markets served
4. Size (15%) — revenue/market cap within 0.3x–3.0x range
5. Profitability (10%) — similar margin structure

**Output** (JSON ONLY):
{{
  "selected_comparables": [
    {{
      "company_name": "",
      "ticker": "",
      "exchange": "",
      "similarity_score": 0.0,
      "selection_rationale": "",
      "strengths_as_comp": [],
      "weaknesses_as_comp": [],
      "key_metrics": {{
        "revenue_mm": 0,
        "ebitda_margin": 0.0,
        "revenue_growth_3yr": 0.0,
        "market_cap_mm": 0
      }},
      "adjustment_notes": ""
    }}
  ],
  "rejected_candidates": [
    {{"company_name": "", "reason": "", "similarity_score": 0.0}}
  ],
  "comp_set_quality": {{
    "overall_assessment": "Strong | Adequate | Weak",
    "count": 0,
    "average_similarity": 0.0,
    "limitations": []
  }},
  "recommended_adjustments": [
    {{"type": "", "magnitude": "", "rationale": ""}}
  ]
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 8.1 — GENERATE_DCF_NARRATIVE
# ══════════════════════════════════════════════════════════
def p8_dcf():
    upsert(
        key         = "dcf.narrative",
        stage       = PromptStage.dcf,
        temperature = 0.1,
        user_template = """Generate professional DCF methodology narrative for a valuation report.

**Input**:
- {{dcf_results}}: {dcf_results}
- {{assumptions}}: {assumptions}

**Cover**: methodology overview | forecast period | revenue assumptions | profitability | CapEx & working capital | WACC build-up | terminal value | results summary | sensitivity

**Output** (JSON ONLY):
{{
  "methodology_overview": "",
  "forecast_period": "",
  "revenue_assumptions": {{
    "narrative": "",
    "growth_rates": [],
    "basis_by_year": {{}}
  }},
  "profitability_assumptions": {{
    "narrative": "",
    "ebitda_margin_forecast": [],
    "cost_drivers": []
  }},
  "wacc_calculation": {{
    "narrative": "",
    "components": {{
      "cost_of_equity": {{
        "value": 0.0,
        "calculation": "Risk-free rate (X%) + Beta (Y) × ERP (Z%) + Size premium (W%)",
        "risk_free_rate":  {{"value": 0.0, "source": ""}},
        "beta":            {{"value": 0.0, "source": "Median of comps, relevered for target structure"}},
        "erp":             {{"value": 0.0, "source": "Damodaran ERP for Saudi Arabia"}},
        "size_premium":    {{"value": 0.0, "source": "Duff & Phelps Size Premium Study"}}
      }},
      "cost_of_debt": {{
        "value": 0.0, "after_tax": 0.0, "source": ""
      }},
      "target_weights": {{
        "equity": 0, "debt": 0, "source": ""
      }}
    }},
    "wacc": 0.0
  }},
  "terminal_value": {{
    "method": "Perpetuity Growth Model (Gordon Growth)",
    "terminal_growth_rate": 0.0,
    "rationale": "",
    "terminal_value_amount": 0,
    "percentage_of_ev": 0,
    "sensitivity_note": ""
  }},
  "valuation_summary": {{
    "pv_explicit_period": 0,
    "pv_terminal_value":  0,
    "enterprise_value":   0,
    "less_debt":          0,
    "plus_cash":          0,
    "equity_value":       0,
    "implied_multiples": {{
      "ev_forward_revenue": 0.0,
      "ev_forward_ebitda":  0.0
    }}
  }},
  "sensitivity_discussion": ""
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 9.1 — RESEARCH_DISCOUNTS (DLOM / DLOC)
# ══════════════════════════════════════════════════════════
def p9_discounts():
    upsert(
        key   = "discounts.dlom_dloc",
        stage = PromptStage.discounts,
        user_template = """Determine appropriate DLOM and DLOC based on company characteristics and empirical studies.

**Input**:
- {{valuation_context}}: {valuation_context}
- {{interest_type}}: {interest_type}
- {{marketability}}: {marketability}

**DLOM guidance** (typical 20–40%): Longstaff, FMV Opinions, restricted stock studies
**DLOC guidance** (typical 10–30%): Mergerstat control premium studies, minority rights analysis

**Output** (JSON ONLY):
{{
  "dlom": {{
    "applicable": true,
    "recommended_discount": 0,
    "range_considered": [0, 0],
    "justification": "",
    "supporting_studies": [
      {{"study": "Longstaff (1995)", "finding": "Average DLOM 23%", "relevance": "High"}},
      {{"study": "FMV Opinions (2023)", "finding": "", "relevance": ""}}
    ],
    "company_factors": [
      {{"factor": "", "impact": "", "weight": "High | Medium | Low"}}
    ],
    "final_recommendation": 0
  }},
  "dloc": {{
    "applicable": true,
    "recommended_discount": 0,
    "range_considered": [0, 0],
    "justification": "",
    "control_premium_data": {{
      "source": "Mergerstat Review 2024",
      "median_premium": 0,
      "implied_dloc": 0
    }},
    "company_factors": [
      {{"factor": "Board representation", "status": "", "impact": ""}}
    ],
    "final_recommendation": 0
  }},
  "combined_application": {{
    "method": "Sequential (industry standard)",
    "order": "Apply DLOC first, then DLOM to resulting value",
    "formula": "Final Value = Base Value × (1 - DLOC) × (1 - DLOM)",
    "total_discount_pct": 0.0,
    "example_calculation": ""
  }}
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 10.1 — RECONCILE_METHODOLOGIES
# ══════════════════════════════════════════════════════════
def p10_reconciliation():
    upsert(
        key   = "reconciliation.methodologies",
        stage = PromptStage.reconciliation,
        user_template = """Compare results from multiple valuation methods, analyze variance, and recommend weighting.

**Input**:
- {{dcf_result}}: {dcf_result}
- {{market_result}}: {market_result}
- {{cost_result}}: {cost_result}

**Task**: variance analysis | reasons for variance (quantified) | weighting recommendation per IVS 105

**Output** (JSON ONLY):
{{
  "variance_analysis": {{
    "dcf_value":         0,
    "market_value":      0,
    "cost_value":        null,
    "difference":        0,
    "difference_percent": 0.0,
    "assessment": "Within acceptable range (<20%) | Material variance | Negligible"
  }},
  "reasons_for_variance": [
    {{
      "factor": "",
      "explanation": "",
      "estimated_impact": "",
      "confidence": "High | Medium | Low"
    }}
  ],
  "recommended_weighting": {{
    "dcf_weight":    0,
    "market_weight": 0,
    "cost_weight":   0,
    "rationale": ""
  }},
  "final_conclusion": {{
    "dcf_weighted":    0,
    "market_weighted": 0,
    "weighted_average": 0,
    "final_value":      0,
    "rounding_note": "Rounded to nearest million",
    "value_range": [0, 0],
    "confidence": "High | Medium | Low — explanation"
  }}
}}"""
    )


# ══════════════════════════════════════════════════════════
# PROMPT 11.1 — WRITE_EXECUTIVE_SUMMARY
# ══════════════════════════════════════════════════════════
def p11_report():
    upsert(
        key         = "report.executive_summary",
        stage       = PromptStage.report,
        temperature = 0.1,
        max_tokens  = 16000,
        user_template = """Write a professional 1–2 page executive summary for a valuation report.

**Input**:
- {{company_name}}: {company_name}
- {{valuation_date}}: {valuation_date}
- {{valuation_purpose}}: {valuation_purpose}
- {{final_valuation}}: {final_valuation}
- {{language}}: {language}

**Cover**: engagement purpose & scope | company overview (1 para) | methodology summary | key assumptions | valuation conclusion | qualifications & limitations

**Output** (JSON ONLY with report_text as formatted plain text):
{{
  "report_text": "EXECUTIVE SUMMARY\\n\\nPURPOSE AND SCOPE\\n\\nThis valuation report presents an estimate of the fair value of [Company Name] as of [Date] for the purpose of [Purpose]. The scope of work included analysis of historical financial performance, industry research, development of financial projections in consultation with management, and application of accepted valuation methodologies in accordance with International Valuation Standards (IVS) and International Financial Reporting Standards (IFRS).\\n\\nCOMPANY OVERVIEW\\n\\n[Company Name] is a [description, industry, geography, founded]. Revenue of approximately [Amount]. [Business model]. [Competitive position].\\n\\nVALUATION METHODOLOGY\\n\\nTwo methodologies employed: (1) DCF — Income Approach, weighted [X]%, and (2) Guideline Public Company — Market Approach, weighted [Y]%. DCF primary given [rationale].\\n\\nKEY ASSUMPTIONS\\n\\n• Revenue growth [X]%–[Y]% based on management guidance and industry benchmarks\\n• Stabilized EBITDA margin [Z]% by [Year]\\n• WACC [W]% reflecting risk profile\\n• Terminal growth [T]%, consistent with long-term GDP expectations\\n\\nVALUATION CONCLUSION\\n\\nEstimated fair value as of [Date]:\\n\\n    [Currency] [Amount] million\\n\\nEnterprise value [Amount]M, less net debt, equals equity value. Implies EV/EBITDA of [X]x on [Year] EBITDA.\\n\\nQUALIFICATIONS AND LIMITATIONS\\n\\nSubject to assumptions and limiting conditions in this report. Conclusion valid as of valuation date only. Actual results may differ materially from projections.",
  "key_metrics_table": {{
    "revenue_latest": 0,
    "ebitda_latest":  0,
    "ebitda_margin":  0.0,
    "ev_ebitda_implied": 0.0,
    "concluded_value": 0
  }},
  "disclaimer": "This report has been prepared in accordance with IVS and IFRS. Opinions expressed are those of the valuation team and are based on information available as of the valuation date."
}}"""
    )


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n🌱 Prompt Pack {VERSION} — جاري التحميل...\n")

    stages = [
        ("1.1  Financial Extraction",       p1_extraction),
        ("2.1  Historical Trend Analysis",  p2_analysis),
        ("3.1  Management Questions",       p3_questions),
        ("4.1  Assumptions from Q&A",       p4_assumptions),
        ("5.1  Methodology Selection",      p5_methodology),
        ("6.1  Industry Research",          p6_research),
        ("7.1  Comparable Companies",       p7_comps),
        ("8.1  DCF Narrative",              p8_dcf),
        ("9.1  Discounts DLOM/DLOC",        p9_discounts),
        ("10.1 Methodology Reconciliation", p10_reconciliation),
        ("11.1 Executive Summary Report",   p11_report),
    ]

    ok = 0
    for label, fn in stages:
        print(f"\nStage {label}")
        try:
            fn()
            ok += 1
        except Exception as e:
            print(f"  ❌  خطأ: {e}")

    try:
        db.commit()
        print(f"\n{'═'*50}")
        print(f"✅  {ok}/{len(stages)} prompts محمّلة بنجاح  |  {VERSION}")
        print(f"{'═'*50}\n")
    except Exception as e:
        db.rollback()
        print(f"\n❌  فشل الحفظ: {e}\n")
    finally:
        db.close()
