"""One analyst coordinator using reusable financial tools.

This is an *offline*, deterministic tool executor by default. The optional LLM
analyst provides qualitative interpretation, not free-form tool permissions.
An independent reviewer can critique the result after calculation checks pass.

Keeping the workflow deterministic makes it reproducible and testable. Neither
agent can quietly replace source figures or valuation assumptions.
"""
from typing import Any, TypedDict

from .analysis import analyze
from .extraction import extract
from .financial_health import evaluate_health
from .health_validation import validate_health
from .models import AgentRevision, FinancialHealthInput, ValuationInput
from .research import research
from .validation import validate
from .valuation import run_valuation
from .workflow import _with_version


class AnalystState(TypedDict, total=False):
    input_data: FinancialHealthInput | ValuationInput
    workflow_type: str
    sources: list
    research_notes: list
    financials: list
    metrics: list
    analysis: Any
    valuation: Any
    health: Any
    calculation_error: str
    findings: list
    retry_counts: dict
    revisions: list
    next_stage: str
    status: str
    report_summary: str
    stage_versions: dict
    tool_calls: list


def choose_outcome(request: FinancialHealthInput | ValuationInput) -> str:
    """Select only supported user outcomes; no free-form task execution."""
    return "initial_look" if isinstance(request, FinancialHealthInput) else "valuation"


def _record(state: AnalystState, name: str, updates: dict) -> dict:
    """Snapshot each tool's output and keep an ordered, inspectable tool log."""
    result = _with_version(state, name, updates)
    return {**result, "tool_calls": [*state.get("tool_calls", []), name]}


def research_tool(state: AnalystState) -> dict:
    sources, notes = research(state["input_data"])
    return _record(state, "research", {"sources": sources, "research_notes": notes})


def extraction_tool(state: AnalystState) -> dict:
    years, metrics = extract(state["input_data"])
    return _record(state, "extraction", {"financials": years, "metrics": metrics})


def history_tool(state: AnalystState) -> dict:
    return _record(state, "analysis", {"analysis": analyze(state["financials"])})


def calculation_tool(state: AnalystState) -> dict:
    if state["workflow_type"] == "initial_look":
        return _record(state, "health", {"health": evaluate_health(state["financials"])})

    try:
        latest = max(state["financials"], key=lambda year: year.year)
        model = run_valuation(latest, state["input_data"].capital,
                              state["input_data"].scenarios,
                              state["input_data"].forecast_years)
        update = {"valuation": model, "calculation_error": ""}
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        update = {"valuation": None, "calculation_error": str(exc)}
    return _record(state, "valuation", update)


def verification_tool(state: AnalystState) -> dict:
    """Deterministic checks are ALWAYS run, independently of the LLM reviewer."""
    if state["workflow_type"] == "initial_look":
        findings = validate_health(state["input_data"], state["sources"],
                                   state["financials"], state["health"])
        allowed_retry = "health"
    else:
        findings = validate(state["input_data"], state["sources"],
                            state["financials"], state["analysis"],
                            state.get("valuation"), state.get("calculation_error", ""))
        allowed_retry = "valuation"

    errors = [item for item in findings if item.severity == "error"]
    counts = dict(state.get("retry_counts", {}))
    revisions = list(state.get("revisions", []))
    # Automatic retries are limited to reproducible computation errors.
    # Research, extracted financials and assumptions require human correction.
    repair = next((f for f in errors if f.retryable and f.target_agent == allowed_retry
                   and counts.get(allowed_retry, 0) < 2), None)
    if repair:
        counts[allowed_retry] = counts.get(allowed_retry, 0) + 1
        revisions.append(AgentRevision(
            finding_id=repair.finding_id,
            agent_name=allowed_retry,
            changes_made="Requested a deterministic recalculation; no inputs were changed.",
            reasoning=repair.reasoning, resolved=False,
        ))
        next_stage, status = "calculate", "retrying"
    elif errors:
        next_stage, status = "stop", "blocked"
    else:
        next_stage, status = "report", "passed"
        for revision in revisions:
            revision.resolved = True
    return _record(state, "validation", {
        "findings": findings, "retry_counts": counts, "revisions": revisions,
        "status": status, "next_stage": next_stage,
    })


def report_tool(state: AnalystState) -> dict:
    if state["workflow_type"] == "initial_look":
        summary = state["health"].summary
    else:
        base = state["valuation"].scenarios["base"]
        summary = (f"{state['input_data'].company_name}: base-case FCFF DCF "
                   f"{base.value_per_share:.2f} {state['input_data'].currency}/share. "
                   f"{state['analysis'].summary}")
    return _record(state, "report", {"report_summary": summary})


# These are tools, NOT separate LLM agents. Only the coordinator calls them.
TOOLS = {
    "research": research_tool,
    "extract": extraction_tool,
    "history": history_tool,
    "calculate": calculation_tool,
    "verify": verification_tool,
    "report": report_tool,
}
NEXT = {"research": "extract", "extract": "history", "history": "calculate",
        "calculate": "verify", "report": "done"}


def _initial_state(request: FinancialHealthInput | ValuationInput) -> AnalystState:
    return {"input_data": request, "workflow_type": choose_outcome(request),
            "retry_counts": {}, "revisions": [], "stage_versions": {}, "tool_calls": []}


def run_simple(request: FinancialHealthInput | ValuationInput) -> AnalystState:
    """Simple execution is the easiest place to understand the workflow."""
    state = _initial_state(request)
    stage = "research"
    for _ in range(30):
        if stage in ("done", "stop"):
            return state
        state.update(TOOLS[stage](state))
        stage = state["next_stage"] if stage == "verify" else NEXT[stage]
    raise RuntimeError("Exceeded maximum workflow steps")


def build_langgraph():
    """Optional LangGraph runner with the same tools and bounded correction loop."""
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError as exc:
        raise RuntimeError("Install the workflow extra: pip install -e '.[workflow]'") from exc
    graph = StateGraph(AnalystState)
    for name, tool in TOOLS.items():
        graph.add_node(name, tool)
    graph.add_edge(START, "research")
    for start, end in NEXT.items():
        if end != "done":
            graph.add_edge(start, end)
    graph.add_conditional_edges("verify", lambda state: state["next_stage"],
                                {"calculate": "calculate", "report": "report", "stop": END})
    graph.add_edge("report", END)
    return graph.compile()


def run(request: FinancialHealthInput | ValuationInput, backend: str = "auto") -> AnalystState:
    """All user outcomes use the same analyst coordinator and tools."""
    if backend == "simple":
        return run_simple(request)
    if backend not in {"auto", "langgraph"}:
        raise ValueError("backend must be auto, simple or langgraph")
    try:
        graph = build_langgraph()
    except RuntimeError:
        if backend == "langgraph":
            raise
        return run_simple(request)
    return graph.invoke(_initial_state(request))
