"""Orchestration. The same node functions run in LangGraph or offline fallback.

Graph: research -> extraction -> analysis -> valuation -> validation -> report.
Validation may route to the responsible stage if an automatically repairable
error exists. Otherwise it blocks publication and exposes the finding.
"""

from typing import TypedDict

from .analysis import analyze
from .extraction import extract
from .models import (
    AgentRevision, FinancialAnalysis, FinancialMetric, FinancialYear, SourceDocument,
    ValidationFinding, ValuationInput, ValuationOutput,
)
from .research import research
from .validation import validate
from .valuation import run_valuation


class WorkflowState(TypedDict, total=False):
    input_data: ValuationInput
    sources: list[SourceDocument]
    research_notes: list[str]
    financials: list[FinancialYear]
    metrics: list[FinancialMetric]
    analysis: FinancialAnalysis
    valuation: ValuationOutput | None
    calculation_error: str
    findings: list[ValidationFinding]
    retry_counts: dict[str, int]
    next_stage: str
    status: str
    report_summary: str
    stage_versions: dict[str, list[dict]]
    revisions: list[AgentRevision]


def _with_version(state: WorkflowState, stage: str, update: dict) -> dict:
    """Keep immutable, numbered snapshots instead of overwriting the audit trail."""
    history = {key: list(value) for key, value in state.get("stage_versions", {}).items()}
    snapshots = history.setdefault(stage, [])
    def plain(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [plain(item) for item in value]
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        return value
    snapshots.append({"version": len(snapshots) + 1, "output": plain(update)})
    return {**update, "stage_versions": history}


def research_node(state: WorkflowState) -> dict:
    sources, notes = research(state["input_data"])
    return _with_version(state, "research", {"sources": sources, "research_notes": notes})


def extraction_node(state: WorkflowState) -> dict:
    financials, metrics = extract(state["input_data"])
    return _with_version(state, "extraction", {"financials": financials, "metrics": metrics})


def analysis_node(state: WorkflowState) -> dict:
    return _with_version(state, "analysis", {"analysis": analyze(state["financials"])})


def valuation_node(state: WorkflowState) -> dict:
    try:
        latest = max(state["financials"], key=lambda year: year.year)
        model = run_valuation(latest, state["input_data"].capital,
                              state["input_data"].scenarios,
                              state["input_data"].forecast_years)
        update = {"valuation": model, "calculation_error": ""}
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        update = {"valuation": None, "calculation_error": str(exc)}
    return _with_version(state, "valuation", update)


def validation_node(state: WorkflowState) -> dict:
    findings = validate(
        state["input_data"], state["sources"], state["financials"],
        state["analysis"], state.get("valuation"), state.get("calculation_error", ""),
    )
    errors = [finding for finding in findings if finding.severity == "error"]
    revisions = list(state.get("revisions", []))
    if not errors:
        for revision in revisions:
            # These records represent deterministic retry attempts, not new assumptions.
            revision.resolved = True
    counts = dict(state.get("retry_counts", {}))
    if not errors:
        return _with_version(state, "validation", {"findings": findings, "retry_counts": counts,
                "revisions": revisions, "next_stage": "report", "status": "passed"})

    # Only retry when a deterministic repair is actually available. Never
    # silently revise an investment assumption or questionable source value.
    repair = next((f for f in errors if f.retryable and counts.get(f.target_agent, 0) < 2), None)
    if repair is not None:
        counts[repair.target_agent] = counts.get(repair.target_agent, 0) + 1
        revisions.append(AgentRevision(
            finding_id=repair.finding_id, agent_name=repair.target_agent,
            changes_made="Requested repeat computation; no assumption changed.",
            reasoning=repair.reasoning, resolved=False,
        ))
        return _with_version(state, "validation", {"findings": findings, "retry_counts": counts,
                "revisions": revisions, "next_stage": repair.target_agent, "status": "retrying"})
    return _with_version(state, "validation", {"findings": findings, "retry_counts": counts,
            "revisions": revisions, "next_stage": "stop", "status": "blocked"})


def report_node(state: WorkflowState) -> dict:
    analysis = state["analysis"]
    base = state["valuation"].scenarios["base"]
    return _with_version(state, "report", {"report_summary": (
        f"{state['input_data'].company_name}: base-case FCFF DCF "
        f"{base.value_per_share:.2f} {state['input_data'].currency}/share. "
        f"{analysis.summary}"
    )})


NODES = {
    "research": research_node,
    "extraction": extraction_node,
    "analysis": analysis_node,
    "valuation": valuation_node,
    "validation": validation_node,
    "report": report_node,
}

NEXT = {
    "research": "extraction",
    "extraction": "analysis",
    "analysis": "valuation",
    "valuation": "validation",
    "report": "done",
}


def run_fallback(input_data: ValuationInput) -> WorkflowState:
    """Straightforward runnable version; no LangGraph dependency needed."""
    state: WorkflowState = {"input_data": input_data, "retry_counts": {}, "stage_versions": {}, "revisions": []}
    stage = "research"
    steps = 0
    while stage not in ("done", "stop"):
        if steps > 30:
            raise RuntimeError("Workflow exceeded 30 steps; possible routing error")
        state.update(NODES[stage](state))
        stage = state["next_stage"] if stage == "validation" else NEXT[stage]
        steps += 1
    return state


def build_langgraph():
    """Construct a real LangGraph workflow when installed on the user's machine."""
    try:
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError("Install with: pip install -e '.[workflow]'") from exc

    builder = StateGraph(WorkflowState)
    for name, fn in NODES.items():
        builder.add_node(name, fn)
    builder.add_edge(START, "research")
    for a, b in NEXT.items():
        if a != "report":
            builder.add_edge(a, b)
    builder.add_conditional_edges("validation", lambda state: state["next_stage"], {
        "research": "research", "extraction": "extraction",
        "analysis": "analysis", "valuation": "valuation",
        "report": "report", "stop": END,
    })
    builder.add_edge("report", END)
    return builder.compile(checkpointer=InMemorySaver())


def run(input_data: ValuationInput, backend: str = "auto") -> WorkflowState:
    if backend == "simple":
        return run_fallback(input_data)
    if backend not in ("auto", "langgraph"):
        raise ValueError("backend must be auto, simple, or langgraph")
    try:
        graph = build_langgraph()
    except RuntimeError:
        if backend == "langgraph":
            raise
        return run_fallback(input_data)
    return graph.invoke(
        {"input_data": input_data, "retry_counts": {}, "stage_versions": {}, "revisions": []},
        {"configurable": {"thread_id": f"{input_data.ticker}-{input_data.valuation_date}"}},
        # Repeated validation passes are bounded; this just gives enough graph steps.
        # In LangGraph call, there are at most 2 repairs per target.
    )
