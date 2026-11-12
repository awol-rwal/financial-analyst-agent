"""Financial-health validation is distinct from DCF-specific checks."""

from math import isclose, isfinite
from .models import FinancialHealthInput, FinancialHealthOutput, FinancialYear, SourceDocument, ValidationFinding
from .financial_health import evaluate_health


def validate_health(input_data: FinancialHealthInput, sources: list[SourceDocument],
                    years: list[FinancialYear], output: FinancialHealthOutput) -> list[ValidationFinding]:
    results: list[ValidationFinding] = []

    def add(category: str, severity: str, message: str, evidence: list[str],
            instruction: str, *, retryable: bool = False):
        results.append(ValidationFinding(
            finding_id=f"HEALTH-{len(results)+1:03d}", category=category,
            severity=severity, finding=message, evidence=evidence,
            reasoning="Explicit consistency or completeness check, without guessing missing financials.",
            target_agent={"research": "research", "extraction": "extraction",
                          "calculation": "health"}[category], correction_instruction=instruction,
            verification_criteria="Correction restores source-linked, independently recomputable data.",
            retryable=retryable,
        ))

    ids = [source.source_id for source in sources]
    if len(set(ids)) != len(ids):
        add("research", "error", "Duplicate source IDs", ids, "Assign unique source IDs")
    for year in years:
        if year.source_id not in ids:
            add("research", "error", f"FY{year.year} references missing source", [year.source_id],
                "Register the original document")
        if year.revenue <= 0 or year.shares_outstanding <= 0:
            add("extraction", "error", f"FY{year.year} requires positive revenue and shares", [year.source_id],
                "Correct source values and units")
        for key in ("cash", "debt", "capex", "depreciation_amortization", "current_assets",
                    "current_liabilities", "interest_expense"):
            value = getattr(year, key)
            if value is not None and (not isfinite(value) or value < 0):
                add("extraction", "error", f"FY{year.year} {key} is invalid", [year.source_id],
                    "Review the original financial statement")
        if year.current_assets is not None and year.current_liabilities is not None:
            if year.current_liabilities == 0:
                add("extraction", "warning", f"FY{year.year}: current ratio undefined (zero liabilities)",
                    [year.source_id], "Confirm reporting and disclose undefined ratio")
        if year.operating_cash_flow is not None and not isfinite(year.operating_cash_flow):
            add("extraction", "error", f"FY{year.year} cash flow is not finite", [year.source_id],
                "Correct parsed cash flow")
    # Independent calculation catches tampering rather than trusting the same output.
    expected = evaluate_health(years)
    for name, metric in expected.ratios.items():
        actual = output.ratios.get(name)
        if actual is None or actual.unit != metric.unit or actual.source_ids != metric.source_ids or (
            (metric.value is None) != (actual.value is None)
        ) or (metric.value is not None and actual.value is not None and
              not isclose(metric.value, actual.value, rel_tol=1e-9, abs_tol=1e-8)):
            add("calculation", "error", f"{name} does not reconcile", metric.source_ids,
                "Rerun the deterministic financial-health engine", retryable=True)
    for prior, current in zip(sorted(years, key=lambda x: x.year), sorted(years, key=lambda x: x.year)[1:]):
        if current.year != prior.year + 1:
            add("extraction", "warning", f"Gap between FY{prior.year} and FY{current.year}",
                [prior.source_id, current.source_id], "Supply missing fiscal years if available")
    if input_data.is_synthetic_demo:
        add("research", "warning", "Synthetic demonstration; not investment evidence", [],
            "Replace with verified company filings")
    if output.limitations:
        add("extraction", "warning", f"{len(output.limitations)} metrics unavailable", [],
            "Add documented optional financial statement fields where available")
    return results
