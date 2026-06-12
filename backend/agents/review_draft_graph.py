"""LangGraph — manager review draft (load context → LLM draft)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_trace import get_trace
from agents.synthesis_steps import draft_manager_review, load_review_draft_context


class ReviewDraftState(TypedDict, total=False):
    employee_id: str
    review_type: str
    feedback_entries: list[dict]
    employee_self_assessment: str
    feedback_summary: str | None
    feedback_block: str
    system_prompt: str
    feedback_entries_used: int
    draft: dict


def build_review_draft_graph():
    async def load_context_node(state: ReviewDraftState) -> dict:
        from main import db

        trace = get_trace()
        if trace:
            trace.handoff("langgraph", "Run review draft graph — load context")
        ctx = await load_review_draft_context(
            state["employee_id"],
            state["review_type"],
            state["feedback_entries"],
            db,
            employee_self_assessment=state.get("employee_self_assessment", ""),
            feedback_summary=state.get("feedback_summary"),
        )
        return ctx

    async def draft_node(state: ReviewDraftState) -> dict:
        draft = await draft_manager_review(
            state["feedback_block"],
            state["system_prompt"],
            state["review_type"],
        )
        return {"draft": draft}

    graph = StateGraph(ReviewDraftState)
    graph.add_node("load_context", load_context_node)
    graph.add_node("draft", draft_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "draft")
    graph.add_edge("draft", END)
    return graph.compile()


_compiled: Any = None


def get_review_draft_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_review_draft_graph()
    return _compiled
