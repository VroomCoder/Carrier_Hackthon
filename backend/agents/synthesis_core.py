"""Shared feedback synthesis logic for API and persistence."""

from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore


async def run_synthesis(
    feedback: str,
    employee_id: str | None,
    db_repo: SqliteRepo,
    vector_store: VectorStore,
) -> dict:
    del db_repo, vector_store  # graph loads repos from main
    from agents.synthesis_graph import get_synthesis_graph

    graph = get_synthesis_graph()
    final = await graph.ainvoke(
        {
            "feedback": feedback,
            "employee_id": employee_id,
        }
    )
    return final["result"]


async def run_review_draft_from_feedback(
    employee_id: str,
    review_type: str,
    cycle: str,
    feedback_entries: list[dict],
    db_repo: SqliteRepo,
    vector_store: VectorStore,
    *,
    employee_self_assessment: str = "",
    feedback_summary: str | None = None,
) -> dict:
    del cycle, db_repo, vector_store  # cycle unused; graph uses main.db
    from agents.review_draft_graph import get_review_draft_graph

    graph = get_review_draft_graph()
    final = await graph.ainvoke(
        {
            "employee_id": employee_id,
            "review_type": review_type,
            "feedback_entries": feedback_entries,
            "employee_self_assessment": employee_self_assessment,
            "feedback_summary": feedback_summary,
        }
    )
    return {
        **final["draft"],
        "feedback_entries_used": final.get("feedback_entries_used", 0),
    }
