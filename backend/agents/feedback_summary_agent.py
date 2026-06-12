"""
FeedbackSummaryAgent — agentic behaviour checklist:

✓ Autonomous multi-step execution (cluster → draft → evaluate → optional retry)
✓ Tool use — LLM-driven theme clustering over year-round entries
✓ Self-correction loop — quality evaluation with up to 2 retries
✓ Goal-directed — produce appraisal-ready summary from continuous feedback
✓ Memory use — SQLite entries across cycles; semantic search available
✓ Orchestration — LangGraph state machine (see feedback_summary_graph.py)

Proactive scheduling: see scheduler.py (runs before review windows).
"""

from __future__ import annotations

import uuid

from agent_trace import finish_trace, get_trace, start_trace
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from feedback_cycle import compute_review_cycle, current_review_cycle


async def generate_feedback_summary(
    employee_id: str,
    review_type: str,
    db_repo: SqliteRepo,
    vector_store: VectorStore,
    review_cycle: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Full agentic pipeline for continuous feedback summarisation."""
    del vector_store  # reserved for future semantic retrieval in graph nodes

    if review_type not in ("mid_year", "year_end"):
        raise ValueError("review_type must be mid_year or year_end")

    cycle = review_cycle or current_review_cycle()
    start_trace("feedback_summary", employee_id, user_id)
    trace = get_trace()
    if trace:
        trace.handoff("retrieve", "Load submitted feedback entries")

    entries = db_repo.get_entries_for_review(employee_id, cycle)
    if not entries:
        finish_trace(db_repo, summary="No feedback entries for cycle")
        return {"summary": None, "reason": "no_feedback", "entry_count": 0, "review_cycle": cycle}

    emp = db_repo.get_employee_by_id(employee_id)
    if not emp:
        finish_trace(db_repo, status="failed", summary="Employee not found")
        raise ValueError("Employee not found")

    if trace:
        trace.load("feedback_entries", f"{len(entries)} entries for {cycle}", len(entries))
        trace.handoff("langgraph", "Run feedback summary graph")

    from agents.feedback_summary_graph import get_feedback_summary_graph

    graph = get_feedback_summary_graph()
    final_state = await graph.ainvoke(
        {
            "employee_id": employee_id,
            "review_type": review_type,
            "cycle": cycle,
            "emp": emp,
            "entries": entries,
            "attempt": 0,
            "self_corrections": 0,
            "confidence": "medium",
        }
    )

    draft = final_state["draft"]
    themes = final_state["themes"]
    self_corrections = final_state.get("self_corrections", 0)
    quality_score = float(final_state.get("quality_score", 0))
    confidence = final_state.get("confidence", draft.get("confidence", "medium"))

    summary_id = f"fs_{uuid.uuid4().hex[:8]}"
    theme_names = [t.get("name", "") for t in themes if t.get("name")]
    conf_score_map = {"high": 0.85, "medium": 0.6, "low": 0.35}
    conf_score = conf_score_map.get(confidence, 0.55)
    conf_reason = (
        f"Quality score {quality_score:.2f}, {self_corrections} self-corrections, "
        f"{len(entries)} source entries"
    )
    if trace:
        trace.confidence(confidence, conf_score, conf_reason)
        trace.decision(
            f"Feedback summary draft ({review_type.replace('_', ' ')})",
            f"Trajectory: {draft.get('trajectory', 'insufficient_data')}; "
            f"themes: {', '.join(theme_names[:4]) or 'none'}",
            sources=["feedback_entries"],
        )

    db_repo.upsert_feedback_summary(
        {
            "summary_id": summary_id,
            "employee_id": employee_id,
            "review_cycle": cycle,
            "review_type": review_type,
            "content": draft.get("summary", ""),
            "entry_count": len(entries),
            "themes": theme_names,
            "strengths": draft.get("strengths", []),
            "development_areas": draft.get("development_areas", []),
            "trajectory": draft.get("trajectory", "insufficient_data"),
            "notable_pattern": draft.get("notable_pattern") or "",
            "quality_score": quality_score,
            "confidence": confidence,
            "self_corrections": self_corrections,
            "status": "draft",
        }
    )

    finish_trace(
        db_repo,
        summary=f"Feedback summary ({review_type}) — {len(entries)} entries, score {quality_score}",
        confidence={"level": confidence, "score": conf_score, "reason": conf_reason},
    )

    return {
        "summary_id": summary_id,
        "summary": draft.get("summary", ""),
        "strengths": draft.get("strengths", []),
        "development_areas": draft.get("development_areas", []),
        "trajectory": draft.get("trajectory", "insufficient_data"),
        "notable_pattern": draft.get("notable_pattern"),
        "themes": theme_names,
        "entry_count": len(entries),
        "quality_score": quality_score,
        "confidence": confidence,
        "review_cycle": cycle,
        "review_type": review_type,
        "self_corrections": self_corrections,
    }


def entry_review_cycle_from_date(created_at: str | None) -> str:
    return compute_review_cycle(created_at)
