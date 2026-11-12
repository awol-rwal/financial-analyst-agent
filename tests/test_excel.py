"""Optional integration test: generated Excel formulas reproduce Python DCF.

Skipped when artifact_tool is unavailable on the machine running the tests.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from financial_analyst_agent.export_excel import export_excel
from financial_analyst_agent.models import ValuationInput
from financial_analyst_agent.workflow import run_fallback

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_company.json"


class ExcelIntegrationTest(unittest.TestCase):
    def test_excel_reconciles_to_python(self):
        try:
            from artifact_tool import Blob, SpreadsheetFile
        except ImportError:
            self.skipTest("artifact_tool not installed; Python/Word work normally")
        state = run_fallback(ValuationInput.model_validate_json(DEMO.read_text()))
        with TemporaryDirectory() as folder:
            path = export_excel(state, Path(folder) / "model.xlsx")
            workbook = SpreadsheetFile.import_xlsx(Blob.load(str(path)))
            inspected = workbook.inspect({
                "kind": "table", "range": "Summary!B6",
                "include": "values,formulas", "table_max_rows": 1, "table_max_cols": 1,
            })
            report = json.loads(inspected.ndjson.splitlines()[0])
            excel_value = report["values"][0][0]
            python_value = state["valuation"].scenarios["base"].value_per_share
            self.assertAlmostEqual(excel_value, python_value, places=6)


if __name__ == "__main__":
    unittest.main()
