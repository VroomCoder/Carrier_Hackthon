"""
LangGraph pilot — feedback summary pipeline (cluster → draft → evaluate → retry).

Orchestration only; LLM calls remain on llm_client via feedback_summary_steps.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agent_trace import get_trace
from agents.feedback_summary_steps import (
    cluster_themes,
    draft_summary,
    evaluate_summary,
)


class FeedbackSummaryState(TypedDict, total=False):
    employee_id: str
    review_type: str
    cycle: str
    emp: dict
    entries: list[dict]
    themes: list[dict]
    draft: dict
    quality: dict
    attempt: int
    self_corrections: int
    quality_score: float
    confidence: str
    approved: bool
    correction_issues: list[str]


def _route_after_evaluate(state: FeedbackSummaryState) -> str:
    if state.get("approved"):
        return "done"
    if state.get("attempt", 0) >= 3:
        return "done"
    return "draft"


def build_feedback_summary_graph():
    """Compile the feedback summary LangGraph."""

    async def cluster_node(state: FeedbackSummaryState) -> dict:
        trace = get_trace()
        if trace:
            trace.handoff("cluster", "LLM theme clustering (LangGraph)")
        themes = await cluster_themes(state["entries"])
        return {"themes": themes}

    async def draft_node(state: FeedbackSummaryState) -> dict:
        trace = get_trace()
        corrections = state.get("self_corrections", 0)
        issues = state.get("correction_issues") or None
        if corrections > 0:
            if trace:
                trace.handoff("draft", f"Self-correction retry {corrections} (LangGraph)")
        elif trace:
            trace.handoff("draft", "LLM summary draft (LangGraph)")
        draft = await draft_summary(
            state["emp"],
            state["entries"],
            state["themes"],
            state["review_type"],
            state["cycle"],
            correction_issues=issues,
        )
        return {
            "draft": draft,
            "confidence": draft.get("confidence", state.get("confidence", "medium")),
        }

    async def evaluate_node(state: FeedbackSummaryState) -> dict:
        attempt = state.get("attempt", 0) + 1
        trace = get_trace()
        if trace:
            trace.handoff("evaluate", f"Quality check attempt {attempt} (LangGraph)")
        quality = await evaluate_summary(state["draft"], len(state["entries"]))
        approved = bool(quality.get("approved"))
        quality_score = float(quality.get("overall", 0))
        issues = quality.get("issues") or []
        updates: dict = {
            "attempt": attempt,
            "quality": quality,
            "quality_score": quality_score,
            "approved": approved,
            "correction_issues": issues,
        }
        if not approved and attempt >= 3:
            updates["confidence"] = "low"
        elif not approved and attempt < 3:
            updates["self_corrections"] = state.get("self_corrections", 0) + 1
        return updates

    graph = StateGraph(FeedbackSummaryState)
    graph.add_node("cluster", cluster_node)
    graph.add_node("draft", draft_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_edge(START, "cluster")
    graph.add_edge("cluster", "draft")
    graph.add_edge("draft", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        _route_after_evaluate,
        {"draft": "draft", "done": END},
    )
    return graph.compile()


_compiled_graph = None


def get_feedback_summary_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_feedback_summary_graph()
    return _compiled_graph
