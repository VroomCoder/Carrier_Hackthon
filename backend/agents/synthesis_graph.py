"""LangGraph — feedback synthesis (load context → LLM → bias gate)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_trace import get_trace
from agents.synthesis_steps import (
    apply_synthesis_gate,
    load_synthesis_context,
    synthesise_commentary,
)


class SynthesisState(TypedDict, total=False):
    feedback: str
    employee_id: str | None
    employee_profile_block: str
    milestone_context_block: str
    raw_result: dict
    result: dict


def build_synthesis_graph():
    async def load_context_node(state: SynthesisState) -> dict:
        from main import db, vs

        trace = get_trace()
        if trace:
            trace.handoff("langgraph", "Run synthesis graph — load context")
        ctx = await load_synthesis_context(
            state["feedback"],
            state.get("employee_id"),
            db,
            vs,
        )
        return ctx

    async def synthesise_node(state: SynthesisState) -> dict:
        raw = await synthesise_commentary(
            state["feedback"],
            state.get("employee_profile_block", ""),
            state.get("milestone_context_block", ""),
        )
        return {"raw_result": raw}

    def gate_node(state: SynthesisState) -> dict:
        result = apply_synthesis_gate(state["raw_result"])
        return {"result": result}

    graph = StateGraph(SynthesisState)
    graph.add_node("load_context", load_context_node)
    graph.add_node("synthesise", synthesise_node)
    graph.add_node("apply_gate", gate_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "synthesise")
    graph.add_edge("synthesise", "apply_gate")
    graph.add_edge("apply_gate", END)
    return graph.compile()


_compiled: Any = None


def get_synthesis_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_synthesis_graph()
    return _compiled
