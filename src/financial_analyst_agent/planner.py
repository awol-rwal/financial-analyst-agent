"""Supported user-facing outcomes. Requests do not invent arbitrary workflows."""

from .models import FinancialHealthInput, ValuationInput
from .analyst_agent import run

SUPPORTED_WORKFLOWS = ("valuation", "initial_look", "financial_health")


def parse_request(raw: dict) -> FinancialHealthInput | ValuationInput:
    """Old valuation JSON has no workflow; financial_health is a legacy alias."""
    task = raw.get("workflow", "valuation")
    if task == "valuation":
        return ValuationInput.model_validate(raw)
    if task in ("initial_look", "financial_health"):
        return FinancialHealthInput.model_validate(raw)
    raise ValueError(f"Unsupported workflow: {task!r}. Available: {', '.join(SUPPORTED_WORKFLOWS)}")


def execute(request: FinancialHealthInput | ValuationInput, backend: str = "auto"):
    return run(request, backend=backend)
