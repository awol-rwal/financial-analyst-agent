"""Formula-driven Excel DCF workbook using artifact_tool.

The Python DCF is the source of truth. Workbook formulas reproduce the same
calculations, so the user can inspect and experiment with the assumptions.
Original input sources are listed in a dedicated Sources sheet.
"""

from pathlib import Path

from .models import ValuationInput
from .workflow import WorkflowState

DARK = "#13253E"
TEAL = "#116878"
PALE = "#EDF5F7"
YELLOW = "#FFF2B2"
BLUE = "#0000FF"
GREEN = "#008000"
BLACK = "#000000"
NUMBER = '#,##0.00;[Red](#,##0.00);-'
PERCENT = '0.0%;[Red](0.0%);-'


def col_letter(index: int) -> str:
    """1-indexed Excel column, supporting more than Z if needed later."""
    result = ""
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def section(sheet, row: int, title: str, last_col: str = "H"):
    sheet.merge_cells(f"A{row}:{last_col}{row}")
    sheet.get_range(f"A{row}").values = [[title]]
    sheet.get_range(f"A{row}:{last_col}{row}").format = {
        "fill": DARK, "font": {"bold": True, "color": "#FFFFFF"},
        "row_height": 25, "vertical_alignment": "center",
    }


def title(sheet, name: str, last_col: str = "H"):
    sheet.merge_cells(f"A1:{last_col}1")
    sheet.get_range("A1").values = [[name]]
    sheet.get_range(f"A1:{last_col}1").format = {
        "fill": TEAL, "font": {"bold": True, "color": "#FFFFFF", "size": 16},
        "row_height": 34, "vertical_alignment": "center",
    }


def build_inputs(wb, input_data: ValuationInput, latest):
    sheet = wb.worksheets.add("Inputs")
    title(sheet, "VALUATION | INPUTS")
    rows = {
        4: ("Company", input_data.company_name),
        5: ("Ticker", input_data.ticker),
        6: ("Valuation date", input_data.valuation_date.isoformat()),
        7: ("Currency", input_data.currency),
        8: ("Units", "Currency and shares in millions; per-share in currency"),
        11: ("Latest fiscal year", latest.year),
        12: ("Revenue (millions)", latest.revenue),
        13: ("EBIT (millions)", latest.ebit),
        14: ("D&A (millions)", latest.depreciation_amortization),
        15: ("Capex (millions)", latest.capex),
        16: ("Change in NWC (millions)", latest.change_in_nwc),
        17: ("Cash (millions)", latest.cash),
        18: ("Debt (millions)", latest.debt),
        19: ("Shares outstanding (millions)", latest.shares_outstanding),
        21: ("Tax rate", input_data.capital.tax_rate),
        22: ("Risk-free rate", input_data.capital.risk_free_rate),
        23: ("Beta", input_data.capital.beta),
        24: ("Equity risk premium", input_data.capital.equity_risk_premium),
        25: ("Pre-tax cost of debt", input_data.capital.pre_tax_cost_of_debt),
        26: ("Debt weight", input_data.capital.debt_weight),
        27: ("Forecast years", input_data.forecast_years),
        30: ("Observed market price", input_data.market_price if input_data.market_price else "Not supplied"),
    }
    for r, (label, value) in rows.items():
        sheet.get_range(f"A{r}:B{r}").values = [[label, value]]
    sheet.get_range("A28:A29").values = [["Calculated WACC"], ["Cost of equity (CAPM)"]]
    sheet.get_range("B28").formulas = [["=(1-B26)*(B22+B23*B24)+B26*B25*(1-B21)"]]
    sheet.get_range("B29").formulas = [["=B22+B23*B24"]]
    section(sheet, 10, "HISTORICAL BASELINE")
    section(sheet, 20, "COST OF CAPITAL")
    sheet.get_range("A4:A30").format.column_width = 37
    sheet.get_range("B4:B30").format.column_width = 32
    sheet.get_range("B11:B27").format.font = {"color": BLUE}
    sheet.get_range("B12:B19").set_number_format(NUMBER)
    for r in (21, 22, 24, 25, 26, 28, 29):
        sheet.get_range(f"B{r}").set_number_format(PERCENT)
    sheet.get_range("B28:B29").format.font = {"color": BLACK}
    sheet.get_range("B21:B27").format.fill = YELLOW
    sheet.get_range("A32").values = [["PROVENANCE: latest financials = Sources sheet. Capital assumptions = source list and supplied rationale."]]
    sheet.get_range("A32:H33").format.wrap_text = True
    return sheet


def build_scenarios(wb, input_data: ValuationInput):
    sheet = wb.worksheets.add("Scenarios")
    title(sheet, "VALUATION | SCENARIO ASSUMPTIONS")
    sheet.get_range("A4:H4").values = [["Scenario", "Revenue growth", "EBIT margin", "D&A / revenue",
                                         "Capex / revenue", "NWC / revenue", "Terminal growth", "WACC shift"]]
    sheet.get_range("A4:H4").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    for row, name in ((5, "bear"), (6, "base"), (7, "bull")):
        scenario = input_data.scenarios[name]
        sheet.get_range(f"A{row}:H{row}").values = [[
            name.title(), scenario.revenue_growth, scenario.ebit_margin,
            scenario.da_as_pct_of_revenue, scenario.capex_as_pct_of_revenue,
            scenario.nwc_investment_as_pct_revenue, scenario.terminal_growth,
            scenario.wacc_adjustment,
        ]]
        sheet.get_range(f"B{row}:H{row}").set_number_format(PERCENT)
    sheet.get_range("B5:H7").format = {"fill": YELLOW, "font": {"color": BLUE}}
    sheet.get_range("A4:A11").format.column_width = 20
    sheet.get_range("B4:H11").format.column_width = 18
    sheet.get_range("A10").values = [["Editable inputs are blue on pale yellow. Formula cells are never hardcoded results."]]
    sheet.get_range("A12").values = [["Scenario", "Rationale and supporting evidence"]]
    sheet.get_range("A12:B12").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    for i, name in enumerate(("bear", "base", "bull"), start=13):
        s = input_data.scenarios[name]
        sheet.get_range(f"A{i}:B{i}").values = [[name.title(),
            f"{s.reasoning} | Sources: {', '.join(s.supporting_evidence) or 'None specified'}"]]
    sheet.get_range("B13:B15").format.column_width = 65
    sheet.get_range("B13:B15").format.wrap_text = True
    sheet.get_range("B13:B15").format.row_height = 45
    return sheet


def build_dcf(wb, scenario: str, scenario_row: int, latest, years: int):
    name = f"{scenario.title()} DCF"
    sheet = wb.worksheets.add(name)
    last = col_letter(2 + years)
    title(sheet, f"{scenario.upper()} CASE | FCFF DCF", last)
    sheet.get_range("A4:A13").values = [
        ["Metric (millions, except discount factor)"] , ["Revenue"], ["EBIT"], ["D&A"],
        ["Capex"], ["Change in NWC"], ["Cash taxes"], ["Free cash flow to firm"],
        ["Discount factor"], ["Present value of FCFF"],
    ]
    sheet.get_range(f"C4:{last}4").values = [[latest.year + p for p in range(1, years + 1)]]
    sheet.get_range(f"A4:{last}4").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    formulas = [[] for _ in range(9)]
    for p in range(1, years + 1):
        col = col_letter(2 + p)
        prev_col = col_letter(1 + p)
        revenue_base = "Inputs!$B$12" if p == 1 else f"{prev_col}5"
        this_year = [
            f"={revenue_base}*(1+Scenarios!$B${scenario_row})",  # Revenue
            f"={col}5*Scenarios!$C${scenario_row}",  # EBIT
            f"={col}5*Scenarios!$D${scenario_row}",  # D&A
            f"={col}5*Scenarios!$E${scenario_row}",  # Capex
            f"={col}5*Scenarios!$F${scenario_row}",  # NWC investment
            f"=MAX({col}6,0)*Inputs!$B$21",  # cash taxes
            f"={col}6+{col}7-{col}8-{col}9-{col}10",  # FCFF
            f"=1/(1+$B$25)^{p}",  # discount factor
            f"={col}11*{col}12",  # discounted FCFF
        ]
        for r, formula in enumerate(this_year):
            formulas[r].append(formula)
    sheet.get_range(f"C5:{last}13").formulas = formulas
    sheet.get_range(f"C5:{last}13").set_number_format(NUMBER)
    sheet.get_range(f"C12:{last}12").set_number_format("0.000x")
    sheet.get_range("A16:A26").values = [["PV of forecast FCFF"], ["Terminal year FCFF"],
        ["Terminal value"], ["PV of terminal value"], ["Enterprise value"],
        ["Net cash (cash - debt)"], ["Equity value"], ["Shares outstanding (millions)"],
        ["Intrinsic value per share"], ["WACC"], ["Terminal growth"]]
    sheet.get_range("B16:B26").formulas = [
        [f"=SUM(C13:{last}13)"],
        [f"={last}11*(1+B26)"],
        ["=B17/(B25-B26)"],
        [f"=B18*{last}12"],
        ["=B16+B19"],
        ["=Inputs!B17-Inputs!B18"],
        ["=B20+B21"],
        ["=Inputs!B19"],
        ["=B22/B23"],
        [f"=Inputs!$B$28+Scenarios!$H${scenario_row}"],
        [f"=Scenarios!$G${scenario_row}"],
    ]
    sheet.get_range("B16:B24").set_number_format(NUMBER)
    sheet.get_range("B25:B26").set_number_format(PERCENT)
    for r in (11, 13):
        sheet.get_range(f"A{r}:{last}{r}").format.fill = PALE
    for r in (20, 22, 24):
        sheet.get_range(f"A{r}:B{r}").format = {
            "fill": PALE, "font": {"bold": True, "color": BLACK},
        }
    sheet.get_range("B21:B23").format.font = {"color": GREEN}
    sheet.get_range("B25:B26").format.font = {"color": GREEN}
    sheet.get_range("A4:A28").format.column_width = 37
    sheet.get_range(f"B4:{last}28").format.column_width = 16
    sheet.get_range("A28").values = [["FCFF = EBIT - cash tax + D&A - capex - NWC investment. All forecast inputs are on Scenarios."]]
    return sheet


def build_summary(wb, input_data: ValuationInput, state: WorkflowState):
    sheet = wb.worksheets.get_item("Summary")
    title(sheet, "COMPANY VALUATION | RESULTS")
    sheet.get_range("A3:B3").values = [[input_data.company_name, input_data.valuation_date.isoformat()]]
    sheet.get_range("A4:B4").values = [["Case", "Intrinsic value per share"]]
    sheet.get_range("A4:B4").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    for row, name in ((5, "Bear"), (6, "Base"), (7, "Bull")):
        sheet.get_range(f"A{row}").values = [[name]]
        sheet.get_range(f"B{row}").formulas = [[f"='{name} DCF'!B24"]]
    sheet.get_range("B5:B7").set_number_format(NUMBER)
    sheet.get_range("B5:B7").format.font = {"color": GREEN}
    sheet.get_range("A9:A11").values = [["Cost of equity (CAPM)"], ["Base WACC"],
                                       ["Terminal value proportion (base)"]]
    sheet.get_range("B9:B11").formulas = [["=Inputs!B29"], ["=Inputs!B28"],
                                         ["='Base DCF'!B19/'Base DCF'!B20"]]
    sheet.get_range("B9:B11").set_number_format(PERCENT)
    sheet.get_range("A13").values = [["VALIDATION RESULT"]]
    sheet.get_range("B13").values = [[state["status"].upper()]]
    sheet.get_range("A15").values = [["Important: workbook estimates are scenario-based, not investment advice."]]
    if input_data.is_synthetic_demo:
        sheet.get_range("A17").values = [["DEMONSTRATION: ALL COMPANY FIGURES AND REFERENCES ARE SYNTHETIC."]]
    sheet.get_range("A3:A20").format.column_width = 48
    sheet.get_range("B3:B20").format.column_width = 31
    return sheet


def build_sensitivity(wb, years: int):
    sheet = wb.worksheets.add("Sensitivity")
    title(sheet, "BASE CASE | WACC × TERMINAL GROWTH", "G")
    sheet.get_range("A3").values = [["Each cell recalculates DCF with fixed base-case FCFF forecast."]]
    sheet.get_range("B4").values = [["WACC / g"]]
    sheet.get_range("B4:G4").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    changes_wacc = [-0.02, -0.01, 0, 0.01, 0.02]
    changes_growth = [-0.01, -0.005, 0, 0.005, 0.01]
    for i, delta in enumerate(changes_growth, start=3):
        col = col_letter(i)
        sheet.get_range(f"{col}4").formulas = [[f"='Base DCF'!$B$26+({delta})"]]
    for i, delta in enumerate(changes_wacc, start=5):
        sheet.get_range(f"B{i}").formulas = [[f"='Base DCF'!$B$25+({delta})"]]
    formulas = []
    last = col_letter(2 + years)
    for row in range(5, 10):
        row_formulas = []
        for c in range(3, 8):
            col = col_letter(c)
            present_values = "+".join(
                f"'Base DCF'!${col_letter(2+p)}$11/(1+$B{row})^{p}"
                for p in range(1, years + 1)
            )
            terminal = (f"('Base DCF'!${last}$11*(1+{col}$4)/($B{row}-{col}$4))"
                        f"/(1+$B{row})^{years}")
            value = (f"({present_values}+{terminal}+Inputs!$B$17-Inputs!$B$18)"
                     f"/Inputs!$B$19")
            row_formulas.append(f'=IF($B{row}<={col}$4,"N/A",{value})')
        formulas.append(row_formulas)
    sheet.get_range("C5:G9").formulas = formulas
    sheet.get_range("B5:B9").set_number_format(PERCENT)
    sheet.get_range("C4:G4").set_number_format(PERCENT)
    sheet.get_range("C5:G9").set_number_format(NUMBER)
    sheet.get_range("E7").format = {"fill": YELLOW, "font": {"bold": True, "color": BLACK}}
    sheet.get_range("A4:A10").format.column_width = 8
    sheet.get_range("B4:G10").format.column_width = 17
    return sheet


def build_sources(wb, input_data: ValuationInput, state: WorkflowState):
    sheet = wb.worksheets.add("Sources")
    title(sheet, "SOURCE REGISTER | AUDIT TRAIL", "E")
    sheet.get_range("A3:E3").values = [["ID", "Document", "Source type", "URL", "Notes"]]
    sheet.get_range("A3:E3").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    for r, source in enumerate(state["sources"], start=4):
        sheet.get_range(f"A{r}:E{r}").values = [[
            source.source_id, source.title, source.source_type.value, source.url, source.notes
        ]]
    row = 5 + len(state["sources"])
    section(sheet, row, "MODEL ASSUMPTION PROVENANCE", "E")
    sheet.get_range(f"A{row+1}:B{row+1}").values = [["Capital", input_data.capital.reasoning]]
    for idx, name in enumerate(("bear", "base", "bull"), start=row + 2):
        sc = input_data.scenarios[name]
        sheet.get_range(f"A{idx}:B{idx}").values = [[name.title(), sc.reasoning]]
    sheet.get_range("A3:A20").format.column_width = 28
    sheet.get_range("B3:B20").format.column_width = 38
    sheet.get_range("C3:C20").format.column_width = 22
    sheet.get_range("D3:D20").format.column_width = 60
    sheet.get_range("E3:E20").format.column_width = 36
    sheet.get_range(f"A4:E{row+4}").format.wrap_text = True
    return sheet


def build_audit(wb, state: WorkflowState):
    sheet = wb.worksheets.add("Audit")
    title(sheet, "VALIDATION FINDINGS", "G")
    sheet.get_range("A3:G3").values = [["ID", "Severity", "Category", "Finding",
                                         "Evidence", "Next action", "Status"]]
    sheet.get_range("A3:G3").format = {"fill": DARK, "font": {"bold": True, "color": "#FFFFFF"}}
    for r, finding in enumerate(state.get("findings", []), start=4):
        sheet.get_range(f"A{r}:G{r}").values = [[
            finding.finding_id, finding.severity, finding.category, finding.finding,
            "; ".join(finding.evidence), finding.correction_instruction, finding.status,
        ]]
    for col, width in {"A": 12, "B": 12, "C": 18, "D": 56, "E": 32, "F": 48, "G": 12}.items():
        sheet.get_range(f"{col}3:{col}40").format.column_width = width
    sheet.get_range("A4:G40").format.wrap_text = True
    return sheet


def export_excel(state: WorkflowState, destination: Path) -> Path:
    try:
        from artifact_tool import Workbook, SpreadsheetFile
    except ImportError as exc:
        raise RuntimeError("Excel output requires artifact_tool. The JSON and DOCX outputs work without it.") from exc
    if state.get("valuation") is None or state["status"] != "passed":
        raise ValueError("A failed validation must not create a published valuation workbook")
    input_data = state["input_data"]
    latest = max(state["financials"], key=lambda year: year.year)
    wb = Workbook.create()
    wb.worksheets.add("Summary")  # Place summary first, but fill references after other sheets exist.
    build_inputs(wb, input_data, latest)
    build_scenarios(wb, input_data)
    for name, row in (("bear", 5), ("base", 6), ("bull", 7)):
        build_dcf(wb, name, row, latest, input_data.forecast_years)
    build_sensitivity(wb, input_data.forecast_years)
    build_sources(wb, input_data, state)
    build_audit(wb, state)
    build_summary(wb, input_data, state)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    SpreadsheetFile.export_xlsx(wb).save(str(destination))
    return destination
