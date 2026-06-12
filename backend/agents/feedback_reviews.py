"""Continuous feedback capture and performance review endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.synthesis_core import run_review_draft_from_feedback
from agent_trace import finish_trace, get_trace, start_trace
from agents.feedback_summary_agent import generate_feedback_summary
from confidence_utils import level_from_score
from auth import (
    CurrentUser,
    can_access_employee,
    get_current_user,
    require_admin,
    require_manager_or_admin,
)
from cycle_config import DEFAULT_CYCLE, REQUIRED_GOAL_COUNT
from feedback_cycle import current_review_cycle
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore

router = APIRouter()

CYCLE_STAGES = [
    "Goal Setting",
    "Mid-year Review",
    "Calibration",
    "Year-end Review",
    "Close-out",
]


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


def _author_info(user: CurrentUser, repo: SqliteRepo) -> tuple[str, str]:
    if user.role == "admin":
        return "admin", user.display_name
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="No employee profile linked")
    emp = repo.get_employee_by_id(user.employee_id)
    name = emp["name"] if emp else user.display_name
    return user.employee_id, name


def _is_direct_report(repo: SqliteRepo, manager_employee_id: str, employee_id: str) -> bool:
    return employee_id in {
        r["employee_id"] for r in repo.get_direct_reports(manager_employee_id)
    }


def _can_write_feedback_for_employee(
    repo: SqliteRepo, user: CurrentUser, employee_id: str
) -> bool:
    """Managers may give feedback only to direct reports; HR to any employee."""
    if user.role == "admin":
        return True
    if not user.is_manager or not user.employee_id:
        return False
    if employee_id == user.employee_id:
        return False
    return _is_direct_report(repo, user.employee_id, employee_id)


def _can_view_manager_only_feedback(
    repo: SqliteRepo, user: CurrentUser, employee_id: str
) -> bool:
    if user.role == "admin":
        return True
    if user.is_manager and user.employee_id:
        if employee_id == user.employee_id:
            return True
        return employee_id in {
            r["employee_id"] for r in repo.get_direct_reports(user.employee_id)
        }
    return False


def _feedback_to_response(entry: dict) -> dict:
    vis = entry.get("visibility", "manager_only")
    return {
        "id": entry["id"],
        "entry_id": entry.get("entry_id") or entry["id"],
        "employee_id": entry["employee_id"],
        "author_employee_id": entry.get("author_employee_id", ""),
        "author_name": entry.get("author_name", ""),
        "manager_name": entry.get("author_name", ""),
        "feedback_type": entry.get("feedback_type", "general"),
        "raw_text": entry.get("raw_text", ""),
        "content": entry.get("content") or entry.get("raw_text", ""),
        "context": entry.get("context", ""),
        "sentiment": entry.get("sentiment", "neutral"),
        "tags": entry.get("tags", []),
        "review_cycle": entry.get("review_cycle", ""),
        "is_draft": bool(entry.get("is_draft", 0)),
        "synthesized_commentary": entry.get("synthesized_commentary"),
        "objectivity_score": entry.get("objectivity_score"),
        "visibility": "shared_with_employee" if vis == "shared" else vis,
        "milestone_id": entry.get("milestone_id"),
        "cycle": entry.get("cycle", DEFAULT_CYCLE),
        "created_at": entry.get("created_at", ""),
        "updated_at": entry.get("updated_at", ""),
    }


def _review_to_response(review: dict) -> dict:
    return {
        "id": review["id"],
        "employee_id": review["employee_id"],
        "cycle": review.get("cycle", DEFAULT_CYCLE),
        "review_type": review["review_type"],
        "status": review.get("status", "draft"),
        "employee_self_assessment": review.get("employee_self_assessment", ""),
        "manager_summary": review.get("manager_summary", ""),
        "development_areas": review.get("development_areas", ""),
        "overall_rating": review.get("overall_rating"),
        "submitted_at": review.get("submitted_at"),
        "locked_at": review.get("locked_at"),
        "created_at": review.get("created_at", ""),
        "updated_at": review.get("updated_at", ""),
    }


def _review_has_content(review: dict) -> bool:
    return bool(
        review.get("employee_self_assessment", "").strip()
        or review.get("manager_summary", "").strip()
        or review.get("development_areas", "").strip()
        or review.get("overall_rating")
    )


def compute_cycle_status(repo: SqliteRepo, employee_id: str, cycle: str = DEFAULT_CYCLE) -> dict:
    milestones = repo.get_milestones_by_employee(employee_id)
    calibrated = [m for m in milestones if m.get("status") == "calibrated"]
    suggested = [m for m in milestones if m.get("status") == "suggested"]
    okr_assigned = repo.count_okr_assignments(employee_id, cycle)
    mid_year = repo.get_review(employee_id, "mid_year", cycle)
    year_end = repo.get_review(employee_id, "year_end", cycle)
    feedback_count = repo.count_feedback_for_employee(employee_id)

    if year_end and year_end.get("status") == "locked":
        stage_index = 4
        stage_label = CYCLE_STAGES[4]
    elif year_end and year_end.get("status") == "submitted":
        stage_index = 3
        stage_label = CYCLE_STAGES[3]
    elif year_end and year_end.get("status") == "draft" and _review_has_content(year_end):
        stage_index = 3
        stage_label = CYCLE_STAGES[3]
    elif mid_year and mid_year.get("status") == "submitted":
        stage_index = 2
        stage_label = CYCLE_STAGES[2]
    elif len(calibrated) >= REQUIRED_GOAL_COUNT or (mid_year and _review_has_content(mid_year)):
        stage_index = 1
        stage_label = CYCLE_STAGES[1]
    else:
        stage_index = 0
        stage_label = CYCLE_STAGES[0]

    review_completeness = 0
    if mid_year or year_end:
        parts = 0
        if mid_year and mid_year.get("status") in ("submitted", "locked"):
            parts += 1
        if year_end and year_end.get("status") in ("submitted", "locked"):
            parts += 1
        review_completeness = round((parts / 2) * 100)

    goals_complete = len(calibrated) >= REQUIRED_GOAL_COUNT

    return {
        "cycle": cycle,
        "current_stage_index": stage_index,
        "current_stage": stage_label,
        "stages": CYCLE_STAGES,
        "milestone_count": len(milestones),
        "calibrated_count": len(calibrated),
        "suggested_count": len(suggested),
        "okr_assigned_count": okr_assigned,
        "goals_required": REQUIRED_GOAL_COUNT,
        "goals_complete": goals_complete,
        "feedback_count": feedback_count,
        "mid_year_status": mid_year.get("status") if mid_year else None,
        "year_end_status": year_end.get("status") if year_end else None,
        "review_completeness": review_completeness,
    }


class FeedbackCreate(BaseModel):
    raw_text: str
    feedback_type: str = "continuous"
    visibility: str = "manager_only"
    milestone_id: str | None = None
    cycle: str = DEFAULT_CYCLE
    synthesize: bool = False
    synthesis_id: str | None = None
    synthesized_commentary: str | None = None
    objectivity_score: int | None = None


class FeedbackUpdate(BaseModel):
    visibility: str | None = None
    raw_text: str | None = None


class ReviewUpdate(BaseModel):
    employee_self_assessment: str | None = None
    manager_summary: str | None = None
    development_areas: str | None = None
    overall_rating: int | None = Field(default=None, ge=1, le=5)


@router.get("/employees/{employee_id}/cycle-status")
def get_cycle_status(
    employee_id: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    return compute_cycle_status(repo, employee_id, cycle)


@router.get("/employees/{employee_id}/feedback")
def list_feedback(
    employee_id: str,
    cycle: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    include_private = _can_view_manager_only_feedback(repo, user, employee_id)
    entries = repo.list_feedback_for_employee(
        employee_id,
        include_manager_only=include_private,
        cycle=cycle,
    )
    return [_feedback_to_response(e) for e in entries]


@router.post("/employees/{employee_id}/feedback")
async def create_feedback(
    employee_id: str,
    body: FeedbackCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if not _can_write_feedback_for_employee(repo, user, employee_id):
        raise HTTPException(
            status_code=403,
            detail="Only managers can provide feedback to their direct reports",
        )

    raw = body.raw_text.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Feedback text is required")

    if body.visibility not in ("manager_only", "shared"):
        raise HTTPException(status_code=400, detail="visibility must be manager_only or shared")

    if body.feedback_type not in ("continuous", "peer", "upward"):
        raise HTTPException(status_code=400, detail="Invalid feedback_type")

    if body.milestone_id:
        ms = repo.get_milestone_by_id(body.milestone_id)
        if not ms or ms["employee_id"] != employee_id:
            raise HTTPException(status_code=400, detail="Invalid milestone for this employee")

    author_id, author_name = _author_info(user, repo)
    commentary = body.synthesized_commentary
    score = body.objectivity_score

    if body.synthesis_id:
        syn = repo.get_synthesis(body.synthesis_id)
        if not syn or syn.get("employee_id") != employee_id:
            raise HTTPException(status_code=404, detail="Synthesis not found")
        if syn.get("author_user_id") != user.user_id and user.role != "admin":
            raise HTTPException(status_code=403, detail="Access denied for this synthesis")
        if not syn.get("finalised_at"):
            raise HTTPException(
                status_code=422,
                detail="Synthesis must be finalised before saving feedback",
            )
        commentary = syn.get("commentary") or commentary
        score = syn.get("objectivity_score", score)
    elif body.synthesize:
        raise HTTPException(
            status_code=422,
            detail=(
                "Use POST /api/synthesise, acknowledge bias flags if required, "
                "finalise, then save with synthesis_id"
            ),
        )

    entry = repo.insert_feedback(
        {
            "id": SqliteRepo.new_feedback_id(),
            "employee_id": employee_id,
            "author_employee_id": author_id,
            "author_name": author_name,
            "feedback_type": body.feedback_type,
            "raw_text": raw,
            "synthesized_commentary": commentary,
            "objectivity_score": score,
            "visibility": body.visibility,
            "milestone_id": body.milestone_id,
            "cycle": body.cycle,
        }
    )
    return _feedback_to_response(entry)


@router.patch("/feedback/{feedback_id}")
def update_feedback_entry(
    feedback_id: str,
    body: FeedbackUpdate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    entry = repo.get_feedback_by_id(feedback_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if not _can_write_feedback_for_employee(repo, user, entry["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    if body.visibility is not None:
        if body.visibility not in ("manager_only", "shared"):
            raise HTTPException(status_code=400, detail="Invalid visibility")
        if user.role != "admin" and not user.is_manager:
            if entry["author_employee_id"] != user.employee_id and user.role != "admin":
                require_manager_or_admin(user)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return _feedback_to_response(entry)

    updated = repo.update_feedback(feedback_id, updates)
    return _feedback_to_response(updated or entry)


@router.get("/employees/{employee_id}/reviews")
def list_reviews(
    employee_id: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    reviews = repo.list_reviews_for_employee(employee_id, cycle=cycle)
    if not reviews:
        repo.get_or_create_review(employee_id, "mid_year", cycle)
        repo.get_or_create_review(employee_id, "year_end", cycle)
        reviews = repo.list_reviews_for_employee(employee_id, cycle=cycle)
    return [_review_to_response(r) for r in reviews]


@router.get("/employees/{employee_id}/reviews/{review_type}")
async def get_review(
    employee_id: str,
    review_type: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if review_type not in ("mid_year", "year_end"):
        raise HTTPException(status_code=400, detail="review_type must be mid_year or year_end")
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    review = repo.get_or_create_review(employee_id, review_type, cycle)
    if (
        _can_view_manager_only_feedback(repo, user, employee_id)
        and repo.count_entries(employee_id, current_review_cycle()) > 0
        and not repo.get_feedback_summary(employee_id, current_review_cycle(), review_type)
    ):
        try:
            await generate_feedback_summary(
                employee_id,
                review_type,
                repo,
                vector_store,
                review_cycle=current_review_cycle(),
                user_id=user.user_id,
            )
        except Exception:
            pass
    return _review_to_response(review)


@router.put("/employees/{employee_id}/reviews/{review_type}")
def update_review(
    employee_id: str,
    review_type: str,
    body: ReviewUpdate,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if review_type not in ("mid_year", "year_end"):
        raise HTTPException(status_code=400, detail="review_type must be mid_year or year_end")
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")

    review = repo.get_or_create_review(employee_id, review_type, cycle)
    if review.get("status") == "locked":
        raise HTTPException(status_code=400, detail="Review is locked and cannot be edited")

    updates: dict = {}
    data = body.model_dump(exclude_unset=True)

    is_self = user.employee_id == employee_id
    is_manager_for = _can_view_manager_only_feedback(repo, user, employee_id)

    if "employee_self_assessment" in data:
        if not is_self and user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the employee can edit self-assessment")
        updates["employee_self_assessment"] = data["employee_self_assessment"]

    manager_fields = ("manager_summary", "development_areas")
    if review_type == "year_end":
        manager_fields = (*manager_fields, "overall_rating")
    for field in manager_fields:
        if field in data:
            if not is_manager_for:
                raise HTTPException(status_code=403, detail="Manager or HR access required")
            updates[field] = data[field]

    if review_type == "mid_year" and "overall_rating" in data:
        raise HTTPException(
            status_code=400,
            detail="Overall rating is not used for mid-year reviews",
        )

    if not updates:
        return _review_to_response(review)

    updated = repo.update_review(review["id"], updates)
    return _review_to_response(updated or review)


class MilestoneSelfAssessmentUpdate(BaseModel):
    employee_self_assessment: str


@router.put("/employees/{employee_id}/milestones/{milestone_id}/self-assessment")
def update_milestone_self_assessment(
    employee_id: str,
    milestone_id: str,
    body: MilestoneSelfAssessmentUpdate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")

    is_self = user.employee_id == employee_id
    if not is_self and user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only the employee can update their goal self-assessment",
        )

    text = body.employee_self_assessment.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Self-assessment text is required")

    updated = repo.update_milestone_self_assessment(milestone_id, employee_id, text)
    if not updated:
        raise HTTPException(status_code=404, detail="Milestone not found")

    return {
        "id": updated["id"],
        "employee_id": updated["employee_id"],
        "raw_goal": updated["raw_goal"],
        "smart_goal": updated.get("smart_goal"),
        "employee_self_assessment": updated.get("employee_self_assessment", ""),
        "self_assessment_updated_at": updated.get("self_assessment_updated_at"),
    }


@router.post("/employees/{employee_id}/reviews/{review_type}/draft-from-feedback")
async def draft_review_from_feedback(
    employee_id: str,
    review_type: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if review_type not in ("mid_year", "year_end"):
        raise HTTPException(status_code=400, detail="review_type must be mid_year or year_end")
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    if not _can_write_feedback_for_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Manager or HR access required")

    review = repo.get_or_create_review(employee_id, review_type, cycle)
    if review.get("status") == "locked":
        raise HTTPException(status_code=400, detail="Review is locked")

    entries = repo.get_entries_for_review(employee_id, current_review_cycle())
    if not entries:
        entries = repo.list_feedback_for_employee(
            employee_id, include_manager_only=True, cycle=cycle
        )
    if not entries:
        raise HTTPException(
            status_code=400,
            detail="No continuous feedback entries for this cycle. Add feedback first.",
        )

    summary_row = repo.get_feedback_summary(
        employee_id, current_review_cycle(), review_type
    )
    if not summary_row:
        try:
            await generate_feedback_summary(
                employee_id,
                review_type,
                repo,
                vector_store,
                review_cycle=current_review_cycle(),
                user_id=user.user_id,
            )
            summary_row = repo.get_feedback_summary(
                employee_id, current_review_cycle(), review_type
            )
        except Exception:
            summary_row = None

    try:
        start_trace("review_drafter", employee_id, user.user_id)
        draft = await run_review_draft_from_feedback(
            employee_id,
            review_type,
            cycle,
            entries,
            repo,
            vector_store,
            employee_self_assessment=review.get("employee_self_assessment", ""),
            feedback_summary=summary_row.get("content") if summary_row else None,
        )
        label = "Mid-year" if review_type == "mid_year" else "Year-end"
        entry_count = len(entries)
        has_summary = bool(summary_row and summary_row.get("content"))
        conf_score = 0.35
        if has_summary and entry_count >= 3:
            conf_score = 0.82
        elif has_summary or entry_count >= 2:
            conf_score = 0.62
        elif entry_count >= 1:
            conf_score = 0.48
        level = level_from_score(conf_score)
        reason = (
            f"{entry_count} feedback entries, "
            f"{'AI summary included' if has_summary else 'no AI summary'}"
        )
        trace = get_trace()
        if trace:
            trace.confidence(level, conf_score, reason)
            trace.decision(
                f"{label} review draft generated",
                (draft.get("manager_summary") or "")[:200] or reason,
                sources=["feedback_entries", "feedback_summaries", "milestones"],
            )
        finish_trace(
            repo,
            summary=f"{label} review draft generated",
            confidence={"level": level, "score": conf_score, "reason": reason},
        )
    except Exception as exc:
        finish_trace(repo, status="failed", summary=str(exc)[:120])
        raise HTTPException(status_code=503, detail=f"Draft generation failed: {exc}") from exc

    if not draft.get("manager_summary"):
        raise HTTPException(status_code=422, detail="Could not generate manager summary")

    return {
        "review_type": review_type,
        "cycle": cycle,
        **draft,
    }


@router.post("/employees/{employee_id}/reviews/{review_type}/submit")
def submit_review(
    employee_id: str,
    review_type: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if review_type not in ("mid_year", "year_end"):
        raise HTTPException(status_code=400, detail="review_type must be mid_year or year_end")
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")

    review = repo.get_or_create_review(employee_id, review_type, cycle)
    if review.get("status") == "locked":
        raise HTTPException(status_code=400, detail="Review is already locked")

    is_self = user.employee_id == employee_id
    is_manager_for = _can_view_manager_only_feedback(repo, user, employee_id)

    if is_self and not user.is_manager and user.role != "admin":
        if not review.get("employee_self_assessment", "").strip():
            raise HTTPException(status_code=400, detail="Self-assessment is required before submit")
    elif is_manager_for:
        if not review.get("manager_summary", "").strip():
            raise HTTPException(status_code=400, detail="Manager summary is required before submit")
        if review_type == "year_end" and not review.get("overall_rating"):
            raise HTTPException(
                status_code=400,
                detail="Overall rating is required before submitting the year-end review",
            )
    else:
        raise HTTPException(status_code=403, detail="Cannot submit this review")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    updated = repo.update_review(
        review["id"],
        {"status": "submitted", "submitted_at": now},
    )
    return _review_to_response(updated or review)


@router.post("/employees/{employee_id}/reviews/{review_type}/lock")
def lock_review(
    employee_id: str,
    review_type: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    if review_type not in ("mid_year", "year_end"):
        raise HTTPException(status_code=400, detail="review_type must be mid_year or year_end")

    review = repo.get_review(employee_id, review_type, cycle)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Review must be submitted before locking")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    updated = repo.update_review(
        review["id"],
        {"status": "locked", "locked_at": now},
    )
    return _review_to_response(updated or review)
