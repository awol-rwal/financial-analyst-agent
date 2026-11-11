"""Financial analysis: compute history, not unsupported forecast guesses."""

from .models import FinancialAnalysis, FinancialYear


def analyze(years: list[FinancialYear]) -> FinancialAnalysis:
    ordered = sorted(years, key=lambda item: item.year)
    first, latest = ordered[0], ordered[-1]
    growth = None
    cagr = None
    if len(ordered) > 1 and ordered[-2].revenue > 0:
        growth = latest.revenue / ordered[-2].revenue - 1
    span = latest.year - first.year
    if span > 0 and first.revenue > 0 and latest.revenue > 0:
        cagr = (latest.revenue / first.revenue) ** (1 / span) - 1
    margin = latest.ebit / latest.revenue if latest.revenue else 0.0
    capex_ratio = latest.capex / latest.revenue if latest.revenue else 0.0
    return FinancialAnalysis(
        latest_year=latest.year,
        latest_revenue_growth=growth,
        historical_revenue_cagr=cagr,
        latest_ebit_margin=margin,
        latest_capex_ratio=capex_ratio,
        summary=(
            f"FY{latest.year}: revenue {latest.revenue:,.1f}m; EBIT margin {margin:.1%}; "
            f"capex/revenue {capex_ratio:.1%}."
        ),
        reasoning=(
            "Historical ratios are calculated from source-linked financials. "
            "Forecast scenario assumptions are supplied separately; no LLM-generated "
            "number is silently introduced into the DCF."
        ),
        supporting_evidence=[year.source_id for year in ordered],
    )
