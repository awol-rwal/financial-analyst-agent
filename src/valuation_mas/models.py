"""Data contracts passed between workflow stages.

Keep models here: changing one field then updates validation everywhere.
All monetary figures are converted to *millions* in the extraction stage.
Shares outstanding are in *millions of shares*.
"""

from datetime import date as Date
from enum import Enum
from math import isfinite

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceType(str, Enum):
    SEC = "regulatory_filing"
    COMPANY = "company_report"
    NEWS = "reputable_news"
    SYNTHETIC = "synthetic_demo"
    OTHER = "other"


class SourceDocument(BaseModel):
    source_id: str
    title: str
    url: str
    source_type: SourceType
    date: Date | None = None
    notes: str = ""


class RawFinancialYear(BaseModel):
    """Numbers as entered/found in source documents, before unit conversion."""

    year: int
    revenue: float
    ebit: float
    depreciation_amortization: float
    capex: float  # Positive spending, not a negative cash-flow statement sign.
    change_in_nwc: float  # Positive means investment in working capital.
    cash: float
    debt: float
    shares_outstanding: float
    source_id: str
    units: str = "millions"  # USD/AUD units: ones, thousands, millions, billions
    page_reference: str = ""
    notes: str = ""

    @field_validator("units")
    @classmethod
    def valid_units(cls, value: str) -> str:
        if value not in {"ones", "thousands", "millions", "billions"}:
            raise ValueError("units must be ones, thousands, millions, or billions")
        return value


class CapitalAssumptions(BaseModel):
    tax_rate: float = Field(ge=0, le=1)
    risk_free_rate: float = Field(ge=0)
    beta: float = Field(ge=0)
    equity_risk_premium: float = Field(ge=0)
    pre_tax_cost_of_debt: float = Field(ge=0)
    debt_weight: float = Field(ge=0, le=1)
    reasoning: str
    supporting_evidence: list[str] = Field(default_factory=list)


class ScenarioAssumptions(BaseModel):
    revenue_growth: float = Field(gt=-1, lt=2)
    ebit_margin: float = Field(ge=-1, le=1)
    da_as_pct_of_revenue: float = Field(ge=0, le=1)
    capex_as_pct_of_revenue: float = Field(ge=0, le=1)
    nwc_investment_as_pct_revenue: float = Field(ge=-1, le=1)
    terminal_growth: float = Field(gt=-1, lt=1)
    wacc_adjustment: float = 0
    reasoning: str
    supporting_evidence: list[str] = Field(default_factory=list)


class ValuationInput(BaseModel):
    company_name: str
    ticker: str
    currency: str = "USD"
    valuation_date: Date
    is_synthetic_demo: bool = False
    sources: list[SourceDocument]
    historical_financials: list[RawFinancialYear]
    capital: CapitalAssumptions
    scenarios: dict[str, ScenarioAssumptions]
    forecast_years: int = Field(default=5, ge=1, le=10)
    market_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_structure(self):
        if not self.historical_financials:
            raise ValueError("At least one historical financial year is required")
        if set(self.scenarios) != {"bear", "base", "bull"}:
            raise ValueError("Exactly three scenarios are required: bear, base, bull")
        years = [item.year for item in self.historical_financials]
        if len(set(years)) != len(years):
            raise ValueError("Duplicate fiscal years")
        return self


class FinancialMetric(BaseModel):
    name: str
    value: float
    fiscal_year: int
    unit: str
    currency: str
    source_id: str
    page_reference: str
    metric_type: str = "reported"
    reasoning: str


class FinancialYear(BaseModel):
    year: int
    revenue: float
    ebit: float
    depreciation_amortization: float
    capex: float
    change_in_nwc: float
    cash: float
    debt: float
    shares_outstanding: float
    source_id: str


class FinancialAnalysis(BaseModel):
    latest_year: int
    latest_revenue_growth: float | None
    historical_revenue_cagr: float | None
    latest_ebit_margin: float
    latest_capex_ratio: float
    summary: str
    reasoning: str
    supporting_evidence: list[str]


class ForecastYear(BaseModel):
    year: int
    revenue: float
    ebit: float
    depreciation_amortization: float
    capex: float
    change_in_nwc: float
    cash_taxes: float
    fcff: float
    discount_factor: float
    present_value_fcff: float


class ScenarioValuation(BaseModel):
    scenario: str
    wacc: float
    terminal_growth: float
    forecast: list[ForecastYear]
    pv_forecast_fcff: float
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    value_per_share: float
    reasoning: str


class SensitivityPoint(BaseModel):
    wacc: float
    terminal_growth: float
    value_per_share: float | None  # None is shown for invalid WACC <= g.


class ValuationOutput(BaseModel):
    cost_of_equity: float
    base_wacc: float
    scenarios: dict[str, ScenarioValuation]
    sensitivity: list[list[SensitivityPoint]]


class ValidationFinding(BaseModel):
    finding_id: str
    category: str  # research | extraction | analysis | calculation
    severity: str  # error | warning
    finding: str
    evidence: list[str]
    reasoning: str
    target_agent: str
    correction_instruction: str
    verification_criteria: str
    retryable: bool = False
    status: str = "open"


class AgentRevision(BaseModel):
    finding_id: str
    agent_name: str
    changes_made: str
    reasoning: str
    resolved: bool


def ensure_finite(obj: BaseModel) -> None:
    """Catch NaN/inf, including values which slipped through outside Pydantic."""
    def walk(value):
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("Non-finite number in structured data")
        if isinstance(value, dict):
            for x in value.values():
                walk(x)
        elif isinstance(value, list):
            for x in value:
                walk(x)
    walk(obj.model_dump(mode="python"))
