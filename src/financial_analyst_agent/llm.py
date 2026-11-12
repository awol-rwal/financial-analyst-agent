"""Optional independent qualitative review with OpenAI structured output.

This LLM sees only the supplied sources/analysis summary. It does NOT browse,
calculate a DCF, change assumptions, or claim to have verified original filings.
It can add warnings, not overrule deterministic failures.
"""

import json
import os
from pydantic import BaseModel, Field

from .models import FinancialAnalysis, ValidationFinding, ValuationInput, ValuationOutput


class CritiqueIssue(BaseModel):
    issue: str
    supporting_evidence: list[str]
    suggested_check: str


class Critique(BaseModel):
    summary: str
    issues: list[CritiqueIssue] = Field(default_factory=list)


def qualitative_review(input_data: ValuationInput, analysis: FinancialAnalysis,
                       valuation: ValuationOutput) -> tuple[str, list[ValidationFinding]]:
    """Requires `pip install -e '.[llm]'` and OPENAI_API_KEY."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install -e '.[llm]'") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY to enable --llm-review")

    # Keep the prompt small and auditable. There are no invented source excerpts.
    context = {
        "company": input_data.company_name,
        "sources": [s.model_dump(mode="json") for s in input_data.sources],
        "analysis": analysis.model_dump(mode="json"),
        "scenario_assumptions": {k: v.model_dump(mode="json") for k, v in input_data.scenarios.items()},
        "scenario_values_per_share": {k: v.value_per_share for k, v in valuation.scenarios.items()},
    }
    client = OpenAI()
    reply = client.responses.parse(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=(
            "You are a sceptical financial research reviewer. ONLY inspect the provided "
            "input data. Do not pretend you searched the web or read documents. "
            "Spot unsupported forecasts, missing source evidence and unexamined risks. "
            "Do not calculate/alter valuation figures. Return a concise summary and "
            "at most 4 evidence-based issues. Do not reveal hidden chain-of-thought."
        ),
        input=json.dumps(context, indent=2),
        text_format=Critique,
    )
    critique = reply.output_parsed
    if critique is None:
        raise RuntimeError("Model returned no structured critique")
    findings = []
    for index, issue in enumerate(critique.issues, start=1):
        findings.append(ValidationFinding(
            finding_id=f"LLM-{index:03d}", category="analysis", severity="warning",
            finding=issue.issue, evidence=issue.supporting_evidence,
            reasoning="Qualitative LLM suggestion; not independently confirmed against filings.",
            target_agent="analysis", correction_instruction=issue.suggested_check,
            verification_criteria="Human verifies the issue using original source documents.",
            retryable=False,
        ))
    return critique.summary, findings
