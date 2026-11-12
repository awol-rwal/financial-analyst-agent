"""Deterministic financial-health analysis.

All numbers arrive from extraction in currency *millions*. Undefined ratios
are explicitly None, rather than invented, zero-filled or silently divided.
"""

from math import isfinite
from .models import FinancialYear, FinancialHealthOutput, RatioMetric


def evaluate_health(years: list[FinancialYear]) -> FinancialHealthOutput:
    ordered = sorted(years, key=lambda year: year.year)
    if not ordered:
        raise ValueError("At least one fiscal year is needed")
    current = ordered[-1]
    prior = ordered[-2] if len(ordered) > 1 else None
    ratios: dict[str, RatioMetric] = {}
    limitations: list[str] = []

    def add(name: str, numerator: float | None, denominator: float | None,
            formula: str, unit: str = "ratio", sources: list[str] | None = None):
        """Record the formula and provenance even when inputs are unavailable."""
        value = None
        if numerator is not None and denominator is not None and denominator != 0:
            value = numerator / denominator
            if not isfinite(value):
                value = None
        if value is None:
            limitations.append(f"{name}: insufficient inputs or zero denominator ({formula})")
        ratios[name] = RatioMetric(
            name=name, value=value, formula=formula, unit=unit,
            source_ids=sources or [current.source_id],
            reasoning="Computed mechanically from extracted fiscal-year financials."
            if value is not None else "Not calculated: missing inputs or invalid denominator.",
        )

    add("ebit_margin", current.ebit, current.revenue, "EBIT / revenue", "percent")
    add("capex_to_revenue", current.capex, current.revenue, "Capex / revenue", "percent")
    add("net_margin", current.net_income, current.revenue, "Net income / revenue", "percent")
    add("current_ratio", current.current_assets, current.current_liabilities,
        "Current assets / current liabilities")
    add("interest_coverage", current.ebit, current.interest_expense, "EBIT / interest expense")
    add("cash_conversion", current.operating_cash_flow, current.net_income,
        "Operating cash flow / net income")
    add("debt_to_ebit", current.debt, current.ebit, "Total debt / EBIT")

    # These are *absolute monetary metrics*, not ratios. CFO - capex is a simple
    # cash-flow proxy; it does not represent FCFF or an independently audited FCF.
    fcf = (current.operating_cash_flow - current.capex
           if current.operating_cash_flow is not None else None)
    ratios["fcf_proxy"] = RatioMetric(
        name="fcf_proxy", value=fcf, unit="currency_millions",
        formula="Operating cash flow - capital expenditure",
        source_ids=[current.source_id],
        reasoning="A cash-flow proxy; not the FCFF DCF measure." if fcf is not None
        else "Not calculated: operating cash flow unavailable.",
    )
    if fcf is None:
        limitations.append("fcf_proxy: operating cash flow not supplied")
    add("revenue_growth", current.revenue - prior.revenue if prior else None,
        prior.revenue if prior else None,
        "(Current revenue - previous revenue) / previous revenue", "percent",
        [prior.source_id, current.source_id] if prior else [current.source_id])

    known = sum(metric.value is not None for metric in ratios.values())
    return FinancialHealthOutput(
        latest_year=current.year, ratios=ratios, limitations=limitations,
        summary=(f"FY{current.year} financial health: {known}/{len(ratios)} metrics available. "
                 "Unprovided metrics remain unavailable; no investment rating is inferred."),
    )
