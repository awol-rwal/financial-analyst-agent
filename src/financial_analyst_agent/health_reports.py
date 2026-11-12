"""Export human-readable financial-health reports from validated state only."""
from pathlib import Path
from docx import Document


def export_health_word(state, destination: Path) -> Path:
    if state["status"] != "passed":
        raise ValueError("Cannot publish a blocked analysis")
    inp, output = state["input_data"], state["health"]
    doc = Document()
    doc.add_heading("Initial look | Financial health", 0)
    doc.add_paragraph(f"{inp.company_name} ({inp.ticker}) | FY{output.latest_year} | {inp.currency}")
    if inp.is_synthetic_demo:
        doc.add_paragraph("SYNTHETIC DEMO — illustrative data, not investment advice.")
    doc.add_heading("Summary", level=1)
    doc.add_paragraph(output.summary)
    interpretation = state.get("analyst_interpretation")
    if interpretation:
        doc.add_heading("Optional AI analyst interpretation", level=1)
        doc.add_paragraph(interpretation["overview"])
        for heading, key in (("Strengths", "strengths"), ("Risks", "risks"), ("Uncertainties", "uncertainties")):
            if interpretation.get(key):
                doc.add_heading(heading, level=2)
                for item in interpretation[key]:
                    doc.add_paragraph(item, style="List Bullet")
    if state.get("llm_summary"):
        doc.add_paragraph("Optional independent reviewer: " + state["llm_summary"])
    doc.add_heading("Financial metrics", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Light Shading Accent 1"
    for cell, name in zip(table.rows[0].cells, ["Metric", "Value", "Formula", "Source"]):
        cell.text = name
    for name, metric in output.ratios.items():
        value = "N/A" if metric.value is None else (f"{metric.value:.1%}" if metric.unit == "percent" else f"{metric.value:,.3f}")
        for cell, item in zip(table.add_row().cells, [name, value, metric.formula, ", ".join(metric.source_ids)]):
            cell.text = item
    if output.limitations:
        doc.add_heading("Limitations", level=1)
        for item in output.limitations:
            doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Validation findings", level=1)
    for finding in state.get("findings", []):
        doc.add_paragraph(f"{finding.severity.upper()}: {finding.finding}", style="List Bullet")
    doc.add_heading("Sources", level=1)
    for source in state["sources"]:
        doc.add_paragraph(f"{source.source_id}: {source.title} — {source.url}", style="List Bullet")
    doc.add_paragraph("Numbers are calculated from provided data, not independently verified filings.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)
    return destination


def export_health_excel(state, destination: Path) -> Path:
    """Simple audit workbook using the same artifact_tool as the DCF exporter."""
    try:
        from artifact_tool import Workbook, SpreadsheetFile
    except ImportError as exc:
        raise RuntimeError("Excel output requires artifact_tool") from exc
    if state["status"] != "passed":
        raise ValueError("Cannot publish a blocked analysis")
    wb = Workbook.create()
    sheet = wb.worksheets.add("Health Summary")
    sheet.get_range("A1:E1").values = [["Metric", "Value", "Unit", "Formula", "Source IDs"]]
    sheet.get_range("A1:E1").format = {"fill": "#13253E", "font": {"bold": True, "color": "#FFFFFF"}}
    for row, metric in enumerate(state["health"].ratios.values(), start=2):
        sheet.get_range(f"A{row}:E{row}").values = [[metric.name, metric.value, metric.unit,
                                                          metric.formula, ", ".join(metric.source_ids)]]
        if metric.unit == "percent":
            sheet.get_range(f"B{row}").set_number_format("0.0%")
    for col, width in {"A": 25, "B": 16, "C": 23, "D": 49, "E": 25}.items():
        sheet.get_range(f"{col}1:{col}18").format.column_width = width
    sources = wb.worksheets.add("Sources")
    sources.get_range("A1:D1").values = [["Source ID", "Title", "URL", "Type"]]
    for row, source in enumerate(state["sources"], start=2):
        sources.get_range(f"A{row}:D{row}").values = [[source.source_id, source.title,
                                                          source.url, source.source_type.value]]
    sources.get_range("A1:D1").format = {"fill": "#13253E", "font": {"bold": True, "color": "#FFFFFF"}}
    for col, width in {"A": 22, "B": 50, "C": 57, "D": 25}.items():
        sources.get_range(f"{col}1:{col}20").format.column_width = width
    audit = wb.worksheets.add("Validation")
    audit.get_range("A1:C1").values = [["Severity", "Category", "Finding"]]
    for row, finding in enumerate(state.get("findings", []), start=2):
        audit.get_range(f"A{row}:C{row}").values = [[finding.severity, finding.category, finding.finding]]
    audit.get_range("A1:C1").format = {"fill": "#13253E", "font": {"bold": True, "color": "#FFFFFF"}}
    audit.get_range("A1:B20").format.column_width = 18
    audit.get_range("C1:C20").format.column_width = 85
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    SpreadsheetFile.export_xlsx(wb).save(str(destination))
    return destination
