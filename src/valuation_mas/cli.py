"""CLI: run a source-linked DCF or generate an SEC data-import template."""

import argparse
import json
from pathlib import Path
from typing import Any

from .models import FinancialHealthInput
from .planner import parse_request, execute


def serialize(value: Any):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


def run_command(args) -> int:
    data = parse_request(json.loads(Path(args.input).read_text(encoding="utf8")))
    state = execute(data, backend=args.backend)
    # LLM calls are opt-in. The default analysis remains fully offline.
    if state.get("status") == "passed" and args.llm_analysis:
        from .agent_llm import analyst_interpret
        state["analyst_interpretation"] = analyst_interpret(state)
    if state.get("status") == "passed" and args.llm_review:
        from .agent_llm import independent_review
        critique, issues = independent_review(state)
        state["llm_summary"] = critique
        state["findings"] = state.get("findings", []) + issues

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "run.json"
    json_path.write_text(json.dumps(serialize(state), indent=2, ensure_ascii=False), encoding="utf8")
    print(f"Validation: {state['status'].upper()}")
    print(f"Audit JSON: {json_path}")
    for finding in state.get("findings", []):
        print(f"  [{finding.severity.upper()}] {finding.finding_id}: {finding.finding}")

    if state["status"] != "passed":
        print("Publication BLOCKED. Correct the source data/assumptions and rerun.")
        return 2

    print(state["report_summary"])
    if isinstance(data, FinancialHealthInput):
        from .health_reports import export_health_word, export_health_excel
        if not args.no_word:
            print(f"Word report: {export_health_word(state, output_dir / 'initial_look.docx')}")
        if not args.no_excel:
            try:
                print(f"Excel report: {export_health_excel(state, output_dir / 'initial_look.xlsx')}")
            except RuntimeError as exc:
                print(f"Excel skipped: {exc}")
        return 0
    if not args.no_word:
        from .export_word import export_word
        path = export_word(state, output_dir / "valuation_report.docx")
        print(f"Word report: {path}")
    if not args.no_excel:
        from .export_excel import export_excel
        try:
            path = export_excel(state, output_dir / "valuation_model.xlsx")
            print(f"Excel workbook: {path}")
        except RuntimeError as exc:
            print(f"Excel skipped: {exc}")
    return 0


def sec_command(args) -> int:
    from .sec import make_sec_template
    template = make_sec_template(args.ticker, args.email, args.years)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(template, indent=2), encoding="utf8")
    print(f"Saved SEC starter data to {destination}")
    print("IMPORTANT: fill null fields; verify fiscal units, capex, debt, and assumptions against original filings.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Financial Analyst: valuation and initial look")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Run the workflow selected by the input JSON (default: valuation)")
    run_parser.add_argument("--input", required=True, help="Path to company JSON")
    run_parser.add_argument("--output", default="outputs/run", help="Destination folder")
    run_parser.add_argument("--backend", default="auto", choices=["auto", "simple", "langgraph"])
    run_parser.add_argument("--llm-analysis", action="store_true", help="Optional AI analyst interpretation of tool outputs")
    run_parser.add_argument("--llm-review", action="store_true", help="Optional independent AI reviewer for either outcome")
    run_parser.add_argument("--no-word", action="store_true")
    run_parser.add_argument("--no-excel", action="store_true")
    run_parser.set_defaults(func=run_command)

    sec_parser = sub.add_parser("fetch-sec", help="Build a draft JSON from official SEC XBRL company facts")
    sec_parser.add_argument("--ticker", required=True)
    sec_parser.add_argument("--email", required=True, help="Contact for SEC User-Agent header")
    sec_parser.add_argument("--years", default=3, type=int)
    sec_parser.add_argument("--output", default="outputs/sec_template.json")
    sec_parser.set_defaults(func=sec_command)
    args = parser.parse_args()
    raise SystemExit(args.func(args))
