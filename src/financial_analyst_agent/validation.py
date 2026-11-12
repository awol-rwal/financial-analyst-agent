"""Independent checks of source traceability, assumptions and DCF arithmetic.

An error blocks publication. A warning is recorded in the report for review.
The validator never changes a financial input just because it dislikes it.
"""

from math import isclose, isfinite

from .models import (
    FinancialAnalysis, FinancialYear, SourceDocument,
    ValidationFinding, ValuationInput, ValuationOutput,
)


def _finding(number: int, *, category: str, severity: str, message: str,
             evidence: list[str], instruction: str, criteria: str,
             retryable: bool = False) -> ValidationFinding:
    return ValidationFinding(
        finding_id=f"VAL-{number:03d}", category=category,
        severity=severity, finding=message, evidence=evidence,
        reasoning="This condition requires an explicit check; the validator does not guess replacement figures.",
        target_agent={"research": "research", "extraction": "extraction",
                      "analysis": "analysis", "calculation": "valuation"}[category],
        correction_instruction=instruction, verification_criteria=criteria,
        retryable=retryable,
    )


def validate(input_data: ValuationInput, sources: list[SourceDocument],
             financials: list[FinancialYear], analysis: FinancialAnalysis,
             valuation: ValuationOutput | None, calculation_error: str = "") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    def add(category, severity, message, evidence, instruction, criteria, retryable=False):
        findings.append(_finding(len(findings) + 1, category=category, severity=severity,
                                 message=message, evidence=evidence, instruction=instruction,
                                 criteria=criteria, retryable=retryable))

    ids = [source.source_id for source in sources]
    if len(ids) != len(set(ids)):
        add("research", "error", "Source IDs are not unique.", ids,
            "Assign a unique ID to each document.", "All source IDs unique")
    known_ids = set(ids)
    for year in financials:
        if year.source_id not in known_ids:
            add("research", "error", f"FY{year.year} has no registered source.", [year.source_id],
                "Supply the source document and its URL.", "Metric source_id appears in sources")
        if year.revenue <= 0:
            add("extraction", "error", f"FY{year.year} has nonpositive revenue.", [year.source_id],
                "Check units and extraction sign.", "Revenue > 0")
        if year.shares_outstanding <= 0:
            add("extraction", "error", f"FY{year.year} has nonpositive shares.", [year.source_id],
                "Correct share count and units.", "Shares outstanding > 0")
        if year.capex < 0 or year.depreciation_amortization < 0 or year.cash < 0 or year.debt < 0:
            add("extraction", "error", f"FY{year.year} has invalid sign for capex, D&A, cash, or debt.",
                [year.source_id], "Inspect source statement and use positive magnitudes.",
                "Capex, D&A, cash and debt are nonnegative")
        for key in ("revenue", "ebit", "cash", "debt", "shares_outstanding"):
            if not isfinite(getattr(year, key)):
                add("extraction", "error", f"FY{year.year} {key} is not finite.", [year.source_id],
                    "Correct parsing of the number.", "All financial numbers are finite")

    if input_data.is_synthetic_demo:
        add("research", "warning", "Synthetic demonstration company; not suitable for an investment decision.",
            ["Synthetic example figures"], "Replace with audited/source-verified inputs.",
            "Real input data and URLs are supplied")

    years = sorted(financials, key=lambda x: x.year)
    for previous, current in zip(years, years[1:]):
        if current.year != previous.year + 1:
            add("extraction", "warning", f"Gap in history: FY{previous.year} to FY{current.year}.",
                [previous.source_id, current.source_id], "Supply missing years or document the gap.",
                "Historical reporting periods explained")

    for name, scenario in input_data.scenarios.items():
        if not scenario.reasoning.strip():
            add("analysis", "error", f"{name} scenario lacks an assumption rationale.", [],
                "Provide a justification, with evidence.", "Nonempty scenario reasoning")
        for ref in scenario.supporting_evidence:
            if ref not in known_ids:
                add("analysis", "warning", f"{name} assumption cites unregistered evidence {ref}.", [ref],
                    "Register the source or update the reference.", "Evidence ID exists")
    if analysis.historical_revenue_cagr is not None:
        base_growth = input_data.scenarios["base"].revenue_growth
        historical = analysis.historical_revenue_cagr
        if base_growth > historical + 0.10:
            add("analysis", "warning", "Base revenue growth exceeds historical CAGR by >10 percentage points.",
                analysis.supporting_evidence,
                "Verify a specific business reason and evidence for the acceleration.",
                "Material growth change is explained by evidence")

    if calculation_error:
        add("calculation", "error", f"Unable to compute DCF: {calculation_error}", [],
            "Fix invalid model assumptions or calculation inputs; do not guess new rates.",
            "DCF completes with WACC > terminal growth")
    elif valuation is not None:
        # Independently reconstruct the math rather than calling the DCF engine.
        # This can catch a regression in the actual valuation implementation.
        latest = max(financials, key=lambda x: x.year)
        for name, result in valuation.scenarios.items():
            scenario = input_data.scenarios[name]
            try:
                if result.wacc <= result.terminal_growth:
                    raise ValueError("WACC must exceed terminal growth")
                values = []
                last_revenue = latest.revenue
                for period, row in enumerate(result.forecast, start=1):
                    expected_revenue = last_revenue * (1 + scenario.revenue_growth)
                    expected_ebit = expected_revenue * scenario.ebit_margin
                    expected_da = expected_revenue * scenario.da_as_pct_of_revenue
                    expected_capex = expected_revenue * scenario.capex_as_pct_of_revenue
                    expected_nwc = expected_revenue * scenario.nwc_investment_as_pct_revenue
                    expected_tax = max(0, expected_ebit) * input_data.capital.tax_rate
                    expected_fcff = expected_ebit - expected_tax + expected_da - expected_capex - expected_nwc
                    for label, expected, actual in (
                        ("revenue", expected_revenue, row.revenue),
                        ("EBIT", expected_ebit, row.ebit),
                        ("D&A", expected_da, row.depreciation_amortization),
                        ("capex", expected_capex, row.capex),
                        ("NWC investment", expected_nwc, row.change_in_nwc),
                        ("cash tax", expected_tax, row.cash_taxes),
                        ("FCFF", expected_fcff, row.fcff),
                    ):
                        if not isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-8):
                            add("calculation", "error", f"{name}: year {period} {label} does not reconcile.",
                                [f"Expected={expected:.6f}", f"Actual={actual:.6f}"],
                                "Recompute cashflows with the tested engine.",
                                "All forecast figures independently reconcile", retryable=True)
                    values.append(expected_fcff)
                    last_revenue = expected_revenue
                expected_pv = sum(cash / (1 + result.wacc) ** t
                                  for t, cash in enumerate(values, start=1))
                expected_terminal = values[-1] * (1 + result.terminal_growth) / (
                    result.wacc - result.terminal_growth)
                expected_pv_terminal = expected_terminal / (1 + result.wacc) ** len(values)
                expected_ev = expected_pv + expected_pv_terminal
                expected_per_share = (expected_ev + latest.cash - latest.debt) / latest.shares_outstanding
            except (ValueError, ZeroDivisionError, OverflowError) as exc:
                add("calculation", "error", f"{name}: {exc}", [],
                    "Correct formula/inputs and rerun valuation.", "Valuation inputs are valid")
                continue
            checks = {
                "PV of forecast FCFF": (expected_pv, result.pv_forecast_fcff),
                "terminal value": (expected_terminal, result.terminal_value),
                "PV of terminal value": (expected_pv_terminal, result.pv_terminal_value),
                "enterprise value": (expected_ev, result.enterprise_value),
                "equity value": (expected_ev + latest.cash - latest.debt, result.equity_value),
                "value per share": (expected_per_share, result.value_per_share),
            }
            for metric_name, (expected, actual) in checks.items():
                if not isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-8):
                    add("calculation", "error", f"{name}: {metric_name} does not reconcile.",
                        [f"Expected={expected:.6f}", f"Actual={actual:.6f}"],
                        "Recompute the model using the tested deterministic engine.",
                        "Independent recalculation matches", retryable=True)

        scenario_values = [valuation.scenarios[name].value_per_share for name in ("bear", "base", "bull")]
        if not scenario_values == sorted(scenario_values):
            add("analysis", "warning", "Scenario valuations are not bear <= base <= bull.",
                [str(v) for v in scenario_values],
                "Check scenario assumptions and whether unusual ordering is economically justified.",
                "Ordering is documented or revised")

    return findings
