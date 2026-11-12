"""Deterministic FCFF DCF. No LLM is allowed to do these calculations."""

from .models import (
    CapitalAssumptions, FinancialYear, ForecastYear, ScenarioAssumptions,
    ScenarioValuation, SensitivityPoint, ValuationOutput,
)


def calculate_wacc(capital: CapitalAssumptions) -> tuple[float, float]:
    """Return (cost_of_equity, weighted_average_cost_of_capital)."""
    cost_of_equity = capital.risk_free_rate + capital.beta * capital.equity_risk_premium
    equity_weight = 1 - capital.debt_weight
    wacc = (equity_weight * cost_of_equity
            + capital.debt_weight * capital.pre_tax_cost_of_debt * (1 - capital.tax_rate))
    return cost_of_equity, wacc


def discount_fcffs(fcffs: list[float], wacc: float) -> float:
    return sum(fcff / ((1 + wacc) ** period) for period, fcff in enumerate(fcffs, start=1))


def value_cash_flows(fcffs: list[float], wacc: float, terminal_growth: float,
                     cash: float, debt: float, shares: float) -> tuple[float, float, float, float]:
    """Returns (PV FCFF, TV, PV TV, value/share). Raises on invalid parameters."""
    if not fcffs or wacc <= terminal_growth or wacc <= -1:
        raise ValueError("DCF requires at least one FCFF and WACC > terminal growth > -100%")
    if shares <= 0:
        raise ValueError("Shares outstanding must be positive")
    pv_fcffs = discount_fcffs(fcffs, wacc)
    tv = fcffs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_tv = tv / (1 + wacc) ** len(fcffs)
    equity = pv_fcffs + pv_tv + cash - debt
    return pv_fcffs, tv, pv_tv, equity / shares


def run_scenario(name: str, assumptions: ScenarioAssumptions, latest: FinancialYear,
                 capital: CapitalAssumptions, base_wacc: float,
                 forecast_years: int) -> ScenarioValuation:
    wacc = base_wacc + assumptions.wacc_adjustment
    if wacc <= assumptions.terminal_growth:
        raise ValueError(f"{name}: WACC ({wacc:.2%}) must exceed terminal growth ({assumptions.terminal_growth:.2%})")
    forecast: list[ForecastYear] = []
    revenue = latest.revenue
    for period in range(1, forecast_years + 1):
        revenue *= (1 + assumptions.revenue_growth)
        ebit = revenue * assumptions.ebit_margin
        da = revenue * assumptions.da_as_pct_of_revenue
        capex = revenue * assumptions.capex_as_pct_of_revenue
        nwc = revenue * assumptions.nwc_investment_as_pct_revenue
        taxes = max(ebit, 0) * capital.tax_rate
        fcff = ebit + da - capex - nwc - taxes
        discount = (1 + wacc) ** (-period)
        forecast.append(ForecastYear(
            year=latest.year + period, revenue=revenue, ebit=ebit,
            depreciation_amortization=da, capex=capex, change_in_nwc=nwc,
            cash_taxes=taxes, fcff=fcff, discount_factor=discount,
            present_value_fcff=fcff * discount,
        ))
    pv_fcff, terminal_value, pv_terminal, per_share = value_cash_flows(
        [row.fcff for row in forecast], wacc, assumptions.terminal_growth,
        latest.cash, latest.debt, latest.shares_outstanding,
    )
    ev = pv_fcff + pv_terminal
    return ScenarioValuation(
        scenario=name, wacc=wacc, terminal_growth=assumptions.terminal_growth,
        forecast=forecast, pv_forecast_fcff=pv_fcff, terminal_value=terminal_value,
        pv_terminal_value=pv_terminal, enterprise_value=ev,
        equity_value=ev + latest.cash - latest.debt,
        value_per_share=per_share,
        reasoning=(
            f"FCFF DCF: EBIT - taxes + D&A - capex - change in NWC; "
            f"WACC {wacc:.2%}; perpetual growth {assumptions.terminal_growth:.2%}. "
            f"Assumption basis: {assumptions.reasoning}"
        ),
    )


def run_valuation(latest: FinancialYear, capital: CapitalAssumptions,
                  scenarios: dict[str, ScenarioAssumptions], forecast_years: int) -> ValuationOutput:
    cost_equity, base_wacc = calculate_wacc(capital)
    results = {
        name: run_scenario(name, scenario, latest, capital, base_wacc, forecast_years)
        for name, scenario in scenarios.items()
    }
    base = results["base"]
    wacc_deltas = [-0.02, -0.01, 0.0, 0.01, 0.02]
    growth_deltas = [-0.01, -0.005, 0.0, 0.005, 0.01]
    sensitivity: list[list[SensitivityPoint]] = []
    for wacc_delta in wacc_deltas:
        row = []
        for growth_delta in growth_deltas:
            wacc = base.wacc + wacc_delta
            growth = base.terminal_growth + growth_delta
            if wacc <= growth:
                value = None
            else:
                _, _, _, value = value_cash_flows(
                    [f.fcff for f in base.forecast], wacc, growth,
                    latest.cash, latest.debt, latest.shares_outstanding,
                )
            row.append(SensitivityPoint(wacc=wacc, terminal_growth=growth, value_per_share=value))
        sensitivity.append(row)
    return ValuationOutput(
        cost_of_equity=cost_equity,
        base_wacc=base_wacc,
        scenarios=results,
        sensitivity=sensitivity,
    )
