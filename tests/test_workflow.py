import unittest
from unittest.mock import patch

from valuation_mas.workflow import run_fallback, valuation_node
from test_valuation import example


class WorkflowRepairTests(unittest.TestCase):
    def test_transient_calculation_corruption_retries_and_succeeds(self):
        """Exercise the validation -> valuation edge with a recoverable bad result."""
        real = valuation_node
        calls = {"n": 0}

        def corrupt_once(state):
            result = real(state)
            calls["n"] += 1
            if calls["n"] == 1 and result["valuation"] is not None:
                result["valuation"].scenarios["base"].equity_value += 400
            return result

        with patch("valuation_mas.workflow.NODES", dict(
            __import__("valuation_mas.workflow", fromlist=["NODES"]).NODES,
            valuation=corrupt_once,
        )):
            state = run_fallback(example())
        # Equity-value verification is added in validation and catches this.
        self.assertEqual(state["status"], "passed")
        self.assertGreaterEqual(calls["n"], 2)
        self.assertEqual(state["retry_counts"].get("valuation"), 1)
        self.assertEqual(len(state["stage_versions"]["valuation"]), 2)
        self.assertTrue(state["revisions"][0].resolved)


if __name__ == "__main__":
    unittest.main()
