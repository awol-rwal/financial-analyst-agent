# Valuation MAS — an auditable company-valuation prototype

A small, readable Python project implementing the workflow we discussed:

```text
Company input + source register
            |
         Research  -- source IDs, priorities, missing evidence
            |
        Extraction -- normalize units; attach source provenance
            |
         Analysis  -- calculate historical trends; inspect forecast rationale
            |
       DCF engine  -- deterministic Python: FCFF, WACC, scenarios, sensitivity
            |
        Validation -- independently recalculate, check evidence/assumptions
            |              |
            |              +-- repairable error: route to responsible step (max 2)
            |              +-- other error: stop and request human correction
            |
    Word + Excel + JSON
```

**This is a functioning MVP, not a production-ready investment research analyst.** It supports a fully offline fictional demonstration, an optional cautious SEC XBRL starter-data importer for US-listed companies, an optional OpenAI qualitative critique, and a LangGraph implementation. It does **not** yet do autonomous news searching, fully read/verify 10-Ks, value all asset classes, or check real-time market prices. Source data and assumptions must be verified before valuing a real company.

## 1. Start here (Windows / VS Code)

Open the project folder in VS Code, then run in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[workflow,test]"
python -m valuation_mas run --input examples/demo_company.json --output outputs/demo
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[workflow,test]'
python -m valuation_mas run --input examples/demo_company.json --output outputs/demo
```

**Output files:**

- `outputs/demo/run.json` — full input, intermediate state, forecast and audit findings.
- `outputs/demo/valuation_report.docx` — readable research report.
- `outputs/demo/valuation_model.xlsx` — formula-driven Excel model with separate assumptions, 3 DCF scenarios, WACC-vs-terminal-growth sensitivity, and provenance.

**Important Excel dependency:** the Excel writer uses `artifact_tool` (available in the environment that built this project). This library may not be available on a normal personal Python installation. The included **example workbook** can still be opened and edited in Excel. If you do not have the library, use `--no-excel` to run the complete analysis and generate JSON/Word without it. The standard output remains correct even if Excel export is skipped. For easy, fully portable Excel export, replacing `export_excel.py` with a widely available XLSX library is the next recommended engineering improvement.

If you cannot install LangGraph, the project still runs:

```bash
python -m valuation_mas run --input examples/demo_company.json --output outputs/demo --backend simple
```

`--backend auto` (the default) uses LangGraph when installed, and otherwise the built-in runner. Both use the *same stage functions*.

## 2. Understand the code

| File | Responsibility |
|---|---|
| `models.py` | Pydantic schemas; data contracts between stages |
| `research.py` | Source inventory, ranking and missing references |
| `extraction.py` | Convert `ones/thousands/millions/billions` to millions; keep provenance |
| `analysis.py` | Compute historical CAGR, margins, capex ratio |
| `valuation.py` | Deterministic FCFF DCF; WACC; bear/base/bull; sensitivity |
| `validation.py` | Independent arithmetic and source/assumption checks |
| `workflow.py` | Stage functions, LangGraph wiring, bounded correction routing |
| `llm.py` | Optional OpenAI structured qualitative critique (never edits numbers) |
| `export_excel.py` | Formula-driven financial workbook with traceability |
| `export_word.py` | Word report from approved structured state |
| `sec.py` | Optional SEC XBRL data import; **creates an incomplete template, not an automatic valuation** |
| `cli.py` | Command line commands and JSON audit export |

The main learning path is **`models.py` → `valuation.py` → `validation.py` → `workflow.py`**. The other files are adapters for inputs or outputs.

## 3. Change a valuation

Duplicate `examples/demo_company.json` and fill it with the company data you want to use. The required structure is:

```json
{
  "company_name": "...",
  "ticker": "...",
  "currency": "USD",
  "valuation_date": "2026-11-11",
  "is_synthetic_demo": false,
  "sources": ["a list of source_id / title / url / source_type entries"],
  "historical_financials": ["a list of source-linked fiscal-year metrics"],
  "capital": {"tax_rate": 0.25, "risk_free_rate": 0.04, "beta": 1.1,
              "equity_risk_premium": 0.055, "pre_tax_cost_of_debt": 0.06,
              "debt_weight": 0.3, "reasoning": "...", "supporting_evidence": []},
  "scenarios": {"bear": {}, "base": {}, "bull": {}},
  "forecast_years": 5
}
```

This abbreviated snippet is **not itself a valid input**. Copy the complete example so every required scenario field is present.

### Data conventions

- Monetary quantities and **shares** are both in *millions* after normalisation. Per-share valuation is in the original currency.
- `capex` is a **positive cash outlay**; `change_in_nwc` is **positive when working capital consumes cash**.
- `ebit` is operating income, not net income, EBITDA or cash from operations.
- `debt` is total debt relevant to enterprise-to-equity reconciliation; check lease liabilities and issuer-specific conventions.
- `debt_weight` is the **target capital-structure fraction of debt** used in WACC, not current liabilities / total assets.
- Source URLs are never invented. The demo uses clearly labelled `demo://` links, not real financial evidence.
- Forecast figures are generated from **explicit scenario assumptions** (annual revenue growth and margin/capital intensity rates). There is no hidden forecast guessing.

Edit the forecast rates in the JSON input rather than editing Python formulas. The Excel scenario sheet provides an alternative interactive what-if model.

## 4. Optional: retrieve official SEC XBRL starter data

For US-listed reporting companies, request a *starter* JSON file:

```bash
python -m valuation_mas fetch-sec --ticker AAPL --email your-real-email@example.com --output outputs/aapl_starter.json
```

SEC requests should use an identifiable contact address. This code uses the SEC ticker directory and `data.sec.gov` companyfacts API. It extracts the fields it can match conservatively. Many real companies need manual adjustment, including debt, capex, diluted shares, working capital, cash flows, unusual accounting, and fiscal dates.

**Any unconfirmed or unavailable number is written as `null`.** This is deliberate: do not fill missing fields with zero merely to make the model run. Review the original filed 10-K and 10-Q, complete every field, add defensible WACC and scenario assumptions, and only then use the `run` command. For Australian companies, the importer will need a separate ASX/annual-report adapter.

## 5. Optional: OpenAI review

```bash
python -m pip install -e ".[llm]"
# Set OPENAI_API_KEY in your terminal environment, then:
python -m valuation_mas run --input examples/demo_company.json --output outputs/demo --llm-review
```

The optional reviewer receives structured scenario assumptions, source IDs and financial summaries. It can issue **qualitative warnings**, such as questionable growth assumptions. It does not search for additional sources, change assumptions, or calculate a valuation. The numeric DCF remains deterministic. Set `OPENAI_MODEL` to change model.

API usage incurs charges. The default demo requires **no API key**.

## 6. Tests

No special test framework is needed to run these tests:

```bash
python -m unittest discover -s tests -v
```

Tests cover WACC, the expected DCF result, scenario ordering, sensitivity, terminal-growth safety, unit normalisation, blocked reports on missing sources/invalid assumptions, independent arithmetic verification, and a transient bad calculation that is corrected through the workflow's validation retry.

## 7. How the correction loop behaves

Validation findings are structured records with: `finding_id`, `severity`, `category`, `evidence`, `reasoning`, `target_agent`, `correction_instruction`, `verification_criteria`, `status`, and `retryable`.

- **Calculation discrepancy**: re-run deterministic valuation, at most twice. If still wrong, fail.
- **Missing/unreliable sources**: route to research *in a future agent-enabled data retriever*; in the current MVP, stop and request a verified source instead of fabricating one.
- **Extraction error**: stop and ask for correction unless a deterministic normalisation resolves it (unit conversion already happens in extraction).
- **Unsupported qualitative assumption**: warn or stop; do not silently substitute the validator's preferred growth rate.

Every stage stores numbered output snapshots in `stage_versions` inside `run.json`, so repeated calculations remain auditable. The `LangGraph` implementation wires conditional routes from validation back to all responsible nodes. The offline runner follows the same routing rules. The tests exercise the valuation retry path.

## 8. Formula reference

For each forecast period:

```text
Revenue[t]     = Revenue[t-1] × (1 + Revenue growth)
EBIT[t]        = Revenue[t] × EBIT margin
Cash taxes[t]  = max(0, EBIT[t]) × Tax rate
FCFF[t]        = EBIT[t] − Cash taxes[t] + D&A[t] − Capex[t] − ΔNWC[t]
Cost of equity = Risk-free rate + Beta × Equity risk premium
WACC           = Equity weight × Cost of equity
                 + Debt weight × Pre-tax cost of debt × (1 − Tax rate)
PV(FCFF)       = Σ FCFF[t] / (1 + WACC)^t
Terminal value = FCFF[last] × (1 + Terminal growth) / (WACC − Terminal growth)
Enterprise     = PV(FCFF) + PV(Terminal value)
Equity         = Enterprise + Cash − Debt
Per-share      = Equity / Shares outstanding
```

The assumption that free cash flow grows at the terminal growth rate indefinitely is particularly sensitive. For firms with materially changing capital structure, negative or cyclical FCFF, financial institutions or commodity exposure, this straightforward DCF can be inappropriate without an industry-specific model.

## 9. What to build next

1. **Production source retrieval**: download original 10-K/10-Q/ASX reports, parse PDFs and/or XBRL, store source excerpts/pages, and reconcile reported line items.
2. **Actual research agents**: bounded web search for news, risks, guidance, competition; never let unverified web content alter model inputs directly.
3. **Human approval**: a simple review screen to approve the exact scenario assumptions before publication.
4. **Industry-aware methods**: comparable-company trading multiples and operating-specific forecasting for banks, mining/commodities and high-growth firms.
5. **Evaluation set**: extraction ground truth; data attribution coverage; assumption auditability; validation recall; reproducibility; cost.

## Security and reliability

SEC text, web pages and PDFs are untrusted inputs (including potential prompt injection). Keep fetched text as *data*, not instructions. In this MVP no web content is executed, and the OpenAI reviewer only sees structured local input. Do not store API keys in JSON, Git or report files. A successful test run validates calculations and structure, **not** the accuracy or completeness of company assumptions.
