"""Extraction: convert inputs into one consistent, traceable financial model."""

from .models import FinancialMetric, FinancialYear, AnalysisInput

# Convert monetary numbers AND shares to millions; per-share outputs stay absolute.
TO_MILLIONS = {"ones": 1 / 1_000_000, "thousands": 1 / 1_000, "millions": 1, "billions": 1_000}
FIELDS = (
    "revenue", "ebit", "depreciation_amortization", "capex", "change_in_nwc",
    "cash", "debt", "shares_outstanding",
)
OPTIONAL_FIELDS = ("current_assets", "current_liabilities", "net_income", "operating_cash_flow", "interest_expense")


def extract(input_data: AnalysisInput) -> tuple[list[FinancialYear], list[FinancialMetric]]:
    years: list[FinancialYear] = []
    metrics: list[FinancialMetric] = []
    for raw in sorted(input_data.historical_financials, key=lambda item: item.year):
        multiplier = TO_MILLIONS[raw.units]
        numbers = {name: getattr(raw, name) * multiplier for name in FIELDS}
        numbers.update({name: getattr(raw, name) * multiplier if getattr(raw, name) is not None else None
                        for name in OPTIONAL_FIELDS})
        years.append(FinancialYear(year=raw.year, source_id=raw.source_id, **numbers))
        for name, value in numbers.items():
            if value is None:
                continue
            metrics.append(FinancialMetric(
                name=name,
                value=value,
                fiscal_year=raw.year,
                unit="millions of shares" if name == "shares_outstanding" else "millions",
                currency="shares" if name == "shares_outstanding" else input_data.currency,
                source_id=raw.source_id,
                page_reference=raw.page_reference,
                reasoning=f"Converted the source value from {raw.units} to millions. {raw.notes}".strip(),
            ))
    return years, metrics
