"""Unit tests use Python's standard unittest, so they run without pytest."""

import copy
import json
from pathlib import Path
import unittest

from financial_analyst_agent.extraction import extract
from financial_analyst_agent.models import ValuationInput
from financial_analyst_agent.validation import validate
from financial_analyst_agent.valuation import calculate_wacc, run_valuation, value_cash_flows
from financial_analyst_agent.workflow import run_fallback

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_company.json"


def example():
    return ValuationInput.model_validate_json(DEMO.read_text())


class ValuationTests(unittest.TestCase):
    def test_wacc(self):
        cost_equity, wacc = calculate_wacc(example().capital)
        self.assertAlmostEqual(cost_equity, 0.1005)
        self.assertAlmostEqual(wacc, 0.08385)

    def test_expected_valuation(self):
        inp = example()
        latest = extract(inp)[0][-1]
        result = run_valuation(latest, inp.capital, inp.scenarios, inp.forecast_years)
        self.assertAlmostEqual(result.scenarios["base"].value_per_share, 23.9541637623, places=6)
        self.assertLess(result.scenarios["bear"].value_per_share, result.scenarios["base"].value_per_share)
        self.assertLess(result.scenarios["base"].value_per_share, result.scenarios["bull"].value_per_share)
        self.assertAlmostEqual(result.sensitivity[2][2].value_per_share,
                               result.scenarios["base"].value_per_share)

    def test_terminal_growth_safety(self):
        with self.assertRaisesRegex(ValueError, "WACC"):
            value_cash_flows([10, 12, 14], 0.04, 0.06, 30, 40, 10)

    def test_full_workflow(self):
        state = run_fallback(example())
        self.assertEqual(state["status"], "passed")
        self.assertIsNotNone(state["valuation"])
        self.assertTrue(any(f.severity == "warning" for f in state["findings"]))
        self.assertTrue(all(f.severity != "error" for f in state["findings"]))

    def test_missing_source_blocks_publication(self):
        inp = example()
        inp.historical_financials[-1].source_id = "missing_id"
        state = run_fallback(inp)
        self.assertEqual(state["status"], "blocked")
        self.assertTrue(any(f.category == "research" and f.severity == "error"
                            for f in state["findings"]))

    def test_invalid_wacc_blocks_publication(self):
        inp = example()
        inp.scenarios["base"].terminal_growth = 0.20
        state = run_fallback(inp)
        self.assertEqual(state["status"], "blocked")
        self.assertIn("WACC", state["calculation_error"])

    def test_units_conversion(self):
        inp = example()
        inp.historical_financials[-1].units = "thousands"
        inp.historical_financials[-1].revenue = 1_210_000
        years, metrics = extract(inp)
        self.assertAlmostEqual(years[-1].revenue, 1210.0)
        self.assertEqual(metrics[-1].unit, "millions of shares")

    def test_independent_validation_finds_tampered_fcff(self):
        state = run_fallback(example())
        broken = copy.deepcopy(state["valuation"])
        broken.scenarios["base"].forecast[0].fcff += 100
        findings = validate(state["input_data"], state["sources"], state["financials"],
                            state["analysis"], broken)
        self.assertTrue(any(f.severity == "error" and "FCFF" in f.finding for f in findings))


if __name__ == "__main__":
    unittest.main()
