# Financial Analyst — hybrid agent and tools

An auditable Python financial-analysis project with **one Financial Analyst coordinator**, reusable calculation/data tools, and an **optional independent AI reviewer**. A deterministic executor works without an API key; optional AI interpretation adds commentary without changing financial figures. Two supported outcomes are available: **Initial Look** and **Valuation**.

> **MVP, not production investment research.** The demos use fictional numbers. The system does not yet autonomously research current news, verify every source against its original filing, or obtain live share prices. Source registration is not proof that a document has been read or checked.

## 1. Choose an outcome

| Outcome | Purpose | Input | Results |
|---|---|---|---|
| **Initial Look** (`initial_look`) | Quick overview of historical financial health; **no share-price estimate** | Historical financial statements; optional liquidity, profit and cash-flow fields | Profitability, revenue growth, leverage, liquidity, cash-conversion ratios; missing-data warnings; Word, Excel and JSON |
| **Valuation** (`valuation`) | Estimate intrinsic equity value per share using explicitly supplied assumptions | Historical financial statements **plus** capital assumptions and bear/base/bull scenarios | FCFF DCF, WACC, scenario and sensitivity calculations; Word, Excel and JSON |

**When to use each:** Start with *Initial Look* to understand a company's reported financial position and identify gaps. Choose *Valuation* when you have evidence-based forecasts and a suitable valuation methodology. A strong company can still be an overpriced investment; neither outcome automatically gives buy/sell advice.

`financial_health` is accepted as a backwards-compatible alias for `initial_look`. Older valuation files without a `workflow` key still default to valuation.

## 2. Architecture

```text
                   User-provided company JSON
                              |
                 Financial Analyst coordinator
                 (supported-outcome routing)
                              |
              Shared tools: source inventory ->
                extraction -> historical analysis
                              |
                     Outcome-specific tool
                   /                       \
           Initial Look                 Valuation
         Financial ratios              FCFF DCF
                   \                       /
                 Deterministic validation
                     |            |
                Pass/review   Block or retry
                     |       calculations only
                Optional AI analyst interpretation
                     |
                Optional independent AI reviewer
                     |
                  JSON + Word + Excel
```

**Why this is a hybrid:** `analyst_agent.py` is the single coordinator. Research, extraction, analysis, ratios, DCF and reporting are **tools/modules**, not separate LLM agents. `agent_llm.py` contains an optional analyst-interpretation call and a separately instructed reviewer call. Validation is mandatory **deterministic code**, even if the reviewer is switched off. LangGraph is optional for executing the same ordered tool calls and bounded correction loop.

**Important distinction:** By default the coordinator is a **deterministic tool orchestrator**, not an autonomous LLM that chooses arbitrary tools. With `--llm-analysis`, a single LLM analyst interprets the tool results; its output is commentary only. The independent reviewer is enabled separately using `--llm-review`. Neither can edit, approve or invent financial values. Using the same model for both does not guarantee independent errors.

## 3. Installation and run commands

From the project root in VS Code, using Python 3.11 or newer:

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,workflow]"
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,workflow]'
```

**Outcome A — Initial Look**

```bash
python -m valuation_mas run --input examples/demo_financial_health.json --output outputs/initial_look
```

Outputs: `run.json`, `initial_look.docx`, and `initial_look.xlsx` when Excel export is available.

**Outcome B — Valuation**

```bash
python -m valuation_mas run --input examples/demo_company.json --output outputs/valuation
```

Outputs: `run.json`, `valuation_report.docx`, and `valuation_model.xlsx` when Excel export is available.

**Important about Excel:** Both Excel exporters currently depend on `artifact_tool`, which may not be available on your laptop through normal pip installation. The program catches this and still generates the JSON audit and Word report. To skip the attempted Excel export, add `--no-excel`. Replacing the exporters with `openpyxl` is a sensible next improvement.

**No LangGraph required:** add `--backend simple` to either command. `--backend auto` uses LangGraph when installed and otherwise falls back to the simple runner.

## 4. Optional AI analysis and independent review

```bash
python -m pip install -e '.[llm]'
# Set OPENAI_API_KEY in your environment (never commit credentials)
python -m valuation_mas run --input examples/demo_company.json --output outputs/valuation --llm-analysis --llm-review --no-excel
```

Both flags also work with `initial_look`.

- `--llm-analysis`: one financial analyst model produces a structured overview, strengths, risks and uncertainties from **already computed** data.
- `--llm-review`: an independently prompted reviewer challenges unsupported interpretations or missing evidence, returning **warnings for human verification**. It does not change data or silently assert numerical correctness.
- Run either flag separately or both. Calls cost API tokens. Set `OPENAI_MODEL` (or separate `OPENAI_ANALYST_MODEL` and `OPENAI_REVIEWER_MODEL`) to choose models.

No live web research is performed by either LLM. Uploaded source text must always be treated as untrusted data. A reviewer warning is not a verified fact, and absence of warnings is not proof of accuracy. Optional AI commentary is included in the JSON and Word output.

## 5. Understand the code

| File | Role |
|---|---|
| `analyst_agent.py` | **Start here.** One coordinator, shared tool registry, task-specific calculation selection, deterministic feedback routing |
| `planner.py` | Parse and validate the two outcomes (including the legacy alias) |
| `research.py` | Inventory supplied sources and provenance; not live web research |
| `extraction.py` | Normalise reported amounts/units; keep source identifiers |
| `analysis.py` | Historical revenue, margins and capex analysis |
| `financial_health.py` | Initial Look ratios; missing values remain unavailable |
| `valuation.py` | Deterministic FCFF DCF, WACC, scenarios and sensitivity |
| `validation.py` / `health_validation.py` | Outcome-specific independent arithmetic and data checks |
| `agent_llm.py` | Optional LLM analyst interpretation and separately prompted reviewer |
| `health_reports.py`, `export_word.py`, `export_excel.py` | Word and Excel output |
| `models.py` | Pydantic input/output contracts |
| `cli.py` | CLI and JSON export |
| `workflow.py`, `financial_workflow.py`, `llm.py` | Older implementations retained for import/test compatibility; new CLI uses `analyst_agent.py` |

For a first code walkthrough: **`planner.py` → `analyst_agent.py` → `financial_health.py` / `valuation.py` → validators → `agent_llm.py`**.

## 6. Data, validation and corrections

All currency and share counts are normalised to **millions** during extraction. `capex` is a positive cash expense and positive `change_in_nwc` uses cash. The DCF uses FCFF; the Initial Look `fcf_proxy` is simply operating cash flow minus capex and **is not FCFF**. Ratios with missing inputs or zero denominators are shown as unavailable, never filled in with invented zeros.

- **Deterministic calculation discrepancies:** retry the relevant calculation tool at most twice, record each attempt in `run.json`.
- **Invalid/missing source IDs or input financials:** block report publication; correct the input rather than silently alter figures.
- **Assumption uncertainty and qualitative concerns:** warn and require human review. The reviewer cannot approve assumptions automatically.
- **Traceability:** `run.json` includes source IDs, validation findings, `tool_calls`, `stage_versions`, retry counts and optional AI commentary.

The company JSON examples include invented `demo://` sources. To use real companies, replace them with verified financial disclosures and explicitly justify forecasting assumptions. The optional `fetch-sec` command produces an **incomplete** XBRL-derived starter file for US companies:

```bash
python -m valuation_mas fetch-sec --ticker AAPL --email you@example.com --output outputs/aapl_starter.json
```

You must review and complete this file before using it for real valuation.

## 7. Tests

```bash
python -m pytest -q
```

The suite covers both outcomes, the legacy workflow name, unit normalisation, DCF and ratio formulas, blocked source errors, deterministic correction retries, and workbook reconciliation. These tests do **not** establish real-world financial accuracy.

## 8. Planned next improvements

1. Automated, verifiable retrieval and extraction of actual company filings, including ASX and SEC documents.
2. Standard `openpyxl` Excel export for easy installation on local computers.
3. Human approval gates for significant forecasts and uncertain extraction decisions.
4. Reusable industry/peer-comparison tools and financial-method selection beyond FCFF DCF.
5. Benchmarked analyst/reviewer performance, especially agreement errors and evidence citation accuracy.

The Python module is still named `valuation_mas` to avoid breaking previous imports. The command `financial-analyst-mas` is also available after installation; you can rename the module in a later breaking release if you want.
