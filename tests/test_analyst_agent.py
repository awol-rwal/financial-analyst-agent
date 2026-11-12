"""Tests of the new hybrid design and user-facing outcomes."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from financial_analyst_agent.analyst_agent import TOOLS, run_simple
from financial_analyst_agent.planner import execute, parse_request

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_initial_look_uses_shared_tools():
    data = parse_request(load("demo_financial_health.json"))
    state = execute(data, backend="simple")
    assert state["workflow_type"] == "initial_look"
    assert state["status"] == "passed"
    assert state["tool_calls"] == ["research", "extraction", "analysis", "health", "validation", "report"]
    assert state["health"].ratios["current_ratio"].value == pytest.approx(460 / 250)
    assert "valuation" not in state


def test_valuation_uses_same_coordinator_and_dcf():
    state = execute(parse_request(load("demo_company.json")), backend="simple")
    assert state["workflow_type"] == "valuation"
    assert state["status"] == "passed"
    assert "valuation" in state["tool_calls"]
    assert "health" not in state["tool_calls"]
    assert state["valuation"].scenarios["base"].value_per_share > 0


def test_legacy_financial_health_alias_works():
    raw = load("demo_financial_health.json")
    raw["workflow"] = "financial_health"
    assert execute(parse_request(raw), backend="simple")["workflow_type"] == "initial_look"


def test_missing_source_blocks_and_does_not_retry():
    raw = load("demo_financial_health.json")
    raw["historical_financials"][-1]["source_id"] = "not_registered"
    state = execute(parse_request(raw), backend="simple")
    assert state["status"] == "blocked"
    assert state["retry_counts"] == {}
    assert "report" not in state["tool_calls"]


def test_recoverable_calculation_error_is_retried():
    request = parse_request(load("demo_financial_health.json"))
    original = TOOLS["calculate"]
    calls = {"n": 0}

    def corrupt_once(state):
        updates = original(state)
        calls["n"] += 1
        if calls["n"] == 1:
            updates["health"].ratios["current_ratio"].value = 900
        return updates

    with patch.dict(TOOLS, {"calculate": corrupt_once}):
        state = run_simple(request)
    assert state["status"] == "passed"
    assert calls["n"] == 2
    assert state["retry_counts"] == {"health": 1}
    assert state["revisions"][0].resolved
