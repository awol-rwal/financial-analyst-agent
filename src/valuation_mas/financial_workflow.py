"""Reusable financial-health subgraph with bounded validation feedback.

The legacy valuation workflow lives in workflow.py unchanged. The planner in
planner.py selects one of these known workflows; it never invents an analysis.
"""
from typing import TypedDict

from .analysis import analyze
from .extraction import extract
from .financial_health import evaluate_health
from .health_validation import validate_health
from .models import (AgentRevision, FinancialHealthInput, FinancialHealthOutput,
                     FinancialAnalysis, FinancialYear, FinancialMetric, SourceDocument, ValidationFinding)
from .research import research
from .workflow import _with_version


class HealthState(TypedDict, total=False):
    input_data: FinancialHealthInput
    workflow_type: str
    sources: list[SourceDocument]
    research_notes: list[str]
    financials: list[FinancialYear]
    metrics: list[FinancialMetric]
    analysis: FinancialAnalysis
    health: FinancialHealthOutput
    findings: list[ValidationFinding]
    retry_counts: dict[str, int]
    next_stage: str
    status: str
    report_summary: str
    stage_versions: dict[str, list[dict]]
    revisions: list[AgentRevision]


def research_node(state: HealthState):
    sources, notes = research(state["input_data"])
    return _with_version(state, "research", {"sources": sources, "research_notes": notes})


def extraction_node(state: HealthState):
    years, metrics = extract(state["input_data"])
    return _with_version(state, "extraction", {"financials": years, "metrics": metrics})


def analysis_node(state: HealthState):
    return _with_version(state, "analysis", {"analysis": analyze(state["financials"])})


def health_node(state: HealthState):
    return _with_version(state, "health", {"health": evaluate_health(state["financials"])})


def validation_node(state: HealthState):
    findings = validate_health(state["input_data"], state["sources"],
                               state["financials"], state["health"])
    errors = [f for f in findings if f.severity == "error"]
    counts = dict(state.get("retry_counts", {}))
    revisions = list(state.get("revisions", []))
    repair = next((f for f in errors if f.retryable and counts.get(f.target_agent, 0) < 2), None)
    if repair:
        counts[repair.target_agent] = counts.get(repair.target_agent, 0) + 1
        revisions.append(AgentRevision(
            finding_id=repair.finding_id, agent_name=repair.target_agent,
            changes_made="Requested deterministic recalculation; no financial figure modified.",
            reasoning=repair.reasoning, resolved=False,
        ))
        stage, status = repair.target_agent, "retrying"
    else:
        stage, status = ("stop", "blocked") if errors else ("report", "passed")
        if not errors:
            for r in revisions:
                r.resolved = True
    return _with_version(state, "validation", {
        "findings": findings, "retry_counts": counts, "revisions": revisions,
        "next_stage": stage, "status": status,
    })


def report_node(state: HealthState):
    return _with_version(state, "report", {"report_summary": state["health"].summary})


NODES = {"research": research_node, "extraction": extraction_node,
         "analysis": analysis_node, "health": health_node,
         "validation": validation_node, "report": report_node}
NEXT = {"research": "extraction", "extraction": "analysis", "analysis": "health",
        "health": "validation", "report": "done"}


def run_simple(input_data: FinancialHealthInput) -> HealthState:
    state: HealthState = {"input_data": input_data, "workflow_type": "financial_health",
                          "retry_counts": {}, "stage_versions": {}, "revisions": []}
    stage = "research"
    for _ in range(30):
        if stage in ("stop", "done"):
            return state
        state.update(NODES[stage](state))
        stage = state["next_stage"] if stage == "validation" else NEXT[stage]
    raise RuntimeError("Too many graph steps")


def build_langgraph():
    try:
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError("Install with pip install -e '.[workflow]'") from exc
    graph = StateGraph(HealthState)
    for name, fn in NODES.items():
        graph.add_node(name, fn)
    graph.add_edge(START, "research")
    for a, b in NEXT.items():
        if a != "report":
            graph.add_edge(a, b)
    graph.add_conditional_edges("validation", lambda s: s["next_stage"],
                                {"health": "health", "report": "report", "stop": END})
    graph.add_edge("report", END)
    return graph.compile(checkpointer=InMemorySaver())


def run_health(input_data: FinancialHealthInput, backend: str = "auto") -> HealthState:
    if backend == "simple":
        return run_simple(input_data)
    if backend not in ("auto", "langgraph"):
        raise ValueError("backend must be auto, simple or langgraph")
    try:
        graph = build_langgraph()
    except RuntimeError:
        if backend == "langgraph":
            raise
        return run_simple(input_data)
    return graph.invoke({"input_data": input_data, "workflow_type": "financial_health",
                         "retry_counts": {}, "stage_versions": {}, "revisions": []},
                        {"configurable": {"thread_id": f"health-{input_data.ticker}-{input_data.valuation_date}"}})
