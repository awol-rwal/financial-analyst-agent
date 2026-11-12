"""Tests for workflow selection, financial-health formulas and validation routing."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from financial_analyst_agent.health_validation import validate_health
from financial_analyst_agent.financial_workflow import run_simple, health_node, NODES
from financial_analyst_agent.planner import execute, parse_request
from financial_analyst_agent.models import FinancialHealthInput

PATH = Path(__file__).resolve().parents[1] / "examples" / "demo_financial_health.json"


def example():
    return FinancialHealthInput.model_validate_json(PATH.read_text())


def test_workflow_router_preserves_legacy_valuation():
    path = PATH.with_name("demo_company.json")
    request = parse_request(json.loads(path.read_text()))
    assert request.__class__.__name__ == "ValuationInput"
    assert execute(request, backend="simple")["status"] == "passed"


def test_health_ratios_and_provenance():
    state = run_simple(example())
    assert state["status"] == "passed"
    values = state["health"].ratios
    assert values["current_ratio"].value == pytest.approx(460 / 250)
    assert values["interest_coverage"].value == pytest.approx(206 / 15)
    assert values["fcf_proxy"].value == pytest.approx(202 - 75)
    assert values["revenue_growth"].value == pytest.approx(0.10)
    assert values["revenue_growth"].source_ids == ["demo_2024", "demo_2025"]
    assert len(state["stage_versions"]["health"]) == 1


def test_health_missing_optional_data_returns_none():
    input_data = example()
    input_data.historical_financials[-1].current_assets = None
    input_data.historical_financials[-1].operating_cash_flow = None
    state = run_simple(input_data)
    assert state["status"] == "passed"
    assert state["health"].ratios["current_ratio"].value is None
    assert state["health"].ratios["fcf_proxy"].value is None
    assert any(f.severity == "warning" for f in state["findings"])


def test_health_no_source_blocks_publication():
    input_data = example()
    input_data.historical_financials[-1].source_id = "not-registered"
    state = run_simple(input_data)
    assert state["status"] == "blocked"
    assert any(f.category == "research" and f.severity == "error" for f in state["findings"])


def test_health_bad_financial_sign_blocks_publication():
    input_data = example()
    input_data.historical_financials[-1].current_liabilities = -10
    assert run_simple(input_data)["status"] == "blocked"


def test_health_detects_tampered_calculation():
    state = run_simple(example())
    state["health"].ratios["current_ratio"].value = 999
    findings = validate_health(state["input_data"], state["sources"], state["financials"], state["health"])
    assert any(f.retryable and "current_ratio" in f.finding for f in findings)


def test_health_validation_retries_transient_error():
    original = health_node
    calls = {"count": 0}

    def corrupt_first(state):
        update = original(state)
        calls["count"] += 1
        if calls["count"] == 1:
            update["health"].ratios["current_ratio"].value = 999
        return update

    with patch.dict(NODES, {"health": corrupt_first}):
        state = run_simple(example())
    assert calls["count"] == 2
    assert state["status"] == "passed"
    assert len(state["stage_versions"]["health"]) == 2
    assert state["revisions"][0].resolved is True


def test_unsupported_workflow_rejected():
    with pytest.raises(ValueError, match="Unsupported workflow"):
        parse_request({"workflow": "portfolio_analysis"})
