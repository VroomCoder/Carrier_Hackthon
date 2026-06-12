"""Continuous feedback CRUD, stats, and summary agent API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agents.feedback_reviews import _can_view_manager_only_feedback, _can_write_feedback_for_employee
from agents.feedback_summary_agent import generate_feedback_summary
from auth import CurrentUser, can_access_employee, get_current_user
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from feedback_cycle import current_review_cycle

router = APIRouter(prefix="/feedback", tags=["continuous-feedback"])


class FeedbackEntryCreate(BaseModel):
    employee_id: str
    content: str
    context: str = ""
    feedback_type: str = "general"
    sentiment: str = "neutral"
    visibility: str = "manager_only"
    tags: list[str] = Field(default_factory=list)
    is_draft: bool = False
    manager_name: str | None = None
    synthesis_id: str | None = None


class FeedbackEntryUpdate(BaseModel):
    content: str | None = None
    context: str | None = None
    feedback_type: str | None = None
    sentiment: str | None = None
    visibility: str | None = None
    tags: list[str] | None = None
    is_draft: bool | None = None


class SummariseRequest(BaseModel):
    employee_id: str
    review_type: str
    review_cycle: str | None = None


class CheckBiasRequest(BaseModel):
    text: str


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


def _author_for_user(user: CurrentUser, repo: SqliteRepo) -> tuple[str, str]:
    if user.role == "admin":
        return "admin", user.display_name
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="No employee profile linked")
    emp = repo.get_employee_by_id(user.employee_id)
    return user.employee_id, emp["name"] if emp else user.display_name


def _entry_response(entry: dict) -> dict:
    vis = entry.get("visibility", "manager_only")
    return {
        "entry_id": entry.get("entry_id") or entry.get("id"),
        "id": entry.get("id"),
        "employee_id": entry["employee_id"],
        "manager_name": entry.get("manager_name") or entry.get("author_name"),
        "author_name": entry.get("author_name"),
        "content": entry.get("content") or entry.get("raw_text"),
        "raw_text": entry.get("raw_text"),
        "context": entry.get("context", ""),
        "feedback_type": entry.get("feedback_type", "general"),
        "sentiment": entry.get("sentiment", "neutral"),
        "visibility": "shared_with_employee" if vis == "shared" else vis,
        "tags": entry.get("tags", []),
        "review_cycle": entry.get("review_cycle", ""),
        "is_draft": entry.get("is_draft", False),
        "synthesized_commentary": entry.get("synthesized_commentary"),
        "objectivity_score": entry.get("objectivity_score"),
        "created_at": entry.get("created_at", ""),
        "updated_at": entry.get("updated_at", ""),
    }


def _summary_response(row: dict) -> dict:
    return {
        "summary_id": row["summary_id"],
        "employee_id": row["employee_id"],
        "review_cycle": row["review_cycle"],
        "review_type": row["review_type"],
        "content": row["content"],
        "entry_count": row.get("entry_count", 0),
        "themes": row.get("themes", []),
        "strengths": row.get("strengths", []),
        "development_areas": row.get("development_areas", []),
        "trajectory": row.get("trajectory"),
        "notable_pattern": row.get("notable_pattern"),
        "quality_score": row.get("quality_score", 0),
        "confidence": row.get("confidence", "medium"),
        "generated_at": row.get("generated_at", ""),
        "status": row.get("status", "draft"),
        "self_corrections": row.get("self_corrections", 0),
    }


@router.post("/entries")
def create_entry(
    body: FeedbackEntryCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if not can_access_employee(repo, user, body.employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    if not _can_write_feedback_for_employee(repo, user, body.employee_id):
        raise HTTPException(status_code=403, detail="Only managers can log feedback")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    author_id, author_name = _author_for_user(user, repo)
    commentary = None
    score = None
    if body.synthesis_id:
        syn = repo.get_synthesis(body.synthesis_id)
        if not syn or syn.get("employee_id") != body.employee_id:
            raise HTTPException(status_code=404, detail="Synthesis not found")
        if syn.get("author_user_id") != user.user_id and user.role != "admin":
            raise HTTPException(status_code=403, detail="Access denied for this synthesis")
        if not syn.get("finalised_at"):
            raise HTTPException(
                status_code=422,
                detail="Synthesis must be finalised before saving feedback",
            )
        commentary = syn.get("commentary")
        score = syn.get("objectivity_score")

    entry = repo.create_feedback_entry(
        {
            "employee_id": body.employee_id,
            "author_employee_id": author_id,
            "author_name": body.manager_name or author_name,
            "raw_text": content,
            "context": body.context.strip(),
            "feedback_type": body.feedback_type,
            "sentiment": body.sentiment,
            "visibility": body.visibility,
            "tags": body.tags,
            "is_draft": body.is_draft,
            "synthesized_commentary": commentary,
            "objectivity_score": score,
        }
    )
    if not body.is_draft:
        vector_store.sync_feedback_entry(entry)
    return _entry_response(entry)


@router.get("/entries")
def list_entries(
    employee_id: str,
    review_cycle: str | None = None,
    feedback_type: str | None = None,
    sentiment: str | None = None,
    include_drafts: bool = False,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    include_private = _can_view_manager_only_feedback(repo, user, employee_id)
    entries = repo.get_entries_for_employee(
        employee_id,
        review_cycle=review_cycle,
        feedback_type=feedback_type,
        sentiment=sentiment,
        include_drafts=include_drafts,
    )
    if not include_private:
        entries = [e for e in entries if e.get("visibility") == "shared"]
    grouped: dict[str, list] = {}
    for e in entries:
        rc = e.get("review_cycle", "unknown")
        grouped.setdefault(rc, []).append(_entry_response(e))
    return {
        "entries": [_entry_response(e) for e in entries],
        "grouped": grouped,
        "total": len(entries),
    }


@router.get("/entries/{entry_id}")
def get_entry(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    entry = repo.get_feedback_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not can_access_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    if entry.get("visibility") != "shared" and not _can_view_manager_only_feedback(
        repo, user, entry["employee_id"]
    ):
        raise HTTPException(status_code=403, detail="Entry not visible")
    return _entry_response(entry)


@router.put("/entries/{entry_id}")
def update_entry(
    entry_id: str,
    body: FeedbackEntryUpdate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    entry = repo.get_feedback_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not _can_write_feedback_for_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    updates = body.model_dump(exclude_unset=True)
    updated = repo.update_feedback_entry(entry_id, updates)
    if updated and not updated.get("is_draft"):
        vector_store.sync_feedback_entry(updated)
    return _entry_response(updated or entry)


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    entry = repo.get_feedback_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not _can_write_feedback_for_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    repo.delete_feedback_entry(entry_id)
    vector_store.remove_feedback_entry(entry_id)
    return {"deleted": True, "entry_id": entry_id}


@router.post("/entries/{entry_id}/submit")
def submit_entry(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    entry = repo.get_feedback_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not _can_write_feedback_for_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    updated = repo.update_feedback_entry(entry_id, {"is_draft": False})
    if updated:
        vector_store.sync_feedback_entry(updated)
    return _entry_response(updated or entry)


@router.post("/entries/{entry_id}/share")
def share_entry(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    entry = repo.get_feedback_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not _can_write_feedback_for_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    updated = repo.update_feedback_entry(entry_id, {"visibility": "shared_with_employee"})
    if updated and not updated.get("is_draft"):
        vector_store.sync_feedback_entry(updated)
    return _entry_response(updated or entry)


@router.post("/summarise")
async def summarise_feedback(
    body: SummariseRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if not can_access_employee(repo, user, body.employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        result = await generate_feedback_summary(
            body.employee_id,
            body.review_type,
            repo,
            vector_store,
            review_cycle=body.review_cycle,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Summary agent failed: {exc}") from exc
    if result.get("summary") is None:
        return result
    return result


@router.get("/summary")
def get_summary(
    employee_id: str,
    review_cycle: str | None = None,
    review_type: str = Query("mid_year"),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    cycle = review_cycle or current_review_cycle()
    row = repo.get_feedback_summary(employee_id, cycle, review_type)
    if not row:
        return None
    return _summary_response(row)


@router.post("/summary/{summary_id}/finalise")
def finalise_summary(
    summary_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    row = repo.finalise_feedback_summary(summary_id)
    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")
    if not _can_write_feedback_for_employee(repo, user, row["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")
    return _summary_response(row)


@router.get("/stats")
def feedback_stats(
    employee_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return repo.feedback_stats(employee_id, current_review_cycle())


@router.post("/check-bias")
async def check_bias(
    body: CheckBiasRequest,
    user: CurrentUser = Depends(get_current_user),
):
    from agents.bias_scan import run_bias_check

    text = body.text.strip()
    if len(text) < 10:
        return {"flags": [], "score": 100}
    try:
        return await run_bias_check(text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
