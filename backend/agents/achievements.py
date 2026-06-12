"""Employee achievements — certifications, accomplishments, training for self-assessment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent_trace import finish_trace, get_trace, start_trace
from auth import CurrentUser, can_access_employee, get_current_user
from db.sqlite_repo import SqliteRepo
from feedback_cycle import current_review_cycle
from ollama_client import ollama_complete

router = APIRouter(tags=["achievements"])

ACHIEVEMENT_TYPES = (
    "certification",
    "accomplishment",
    "training",
    "award",
    "project",
    "other",
)


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def _can_view_private(user: CurrentUser, employee_id: str) -> bool:
    return user.role == "admin" or user.employee_id == employee_id


def _can_write_achievements(user: CurrentUser, employee_id: str) -> bool:
    return user.role == "admin" or user.employee_id == employee_id


def _achievement_response(row: dict) -> dict:
    return {
        "achievement_id": row["achievement_id"],
        "employee_id": row["employee_id"],
        "type": row["type"],
        "title": row["title"],
        "description": row.get("description", ""),
        "issuer_or_context": row.get("issuer_or_context", ""),
        "achieved_at": row.get("achieved_at"),
        "review_cycle": row.get("review_cycle"),
        "linked_milestone_id": row.get("linked_milestone_id"),
        "visibility": row.get("visibility", "manager"),
        "source": row.get("source", "manual"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


class AchievementCreate(BaseModel):
    type: str
    title: str
    description: str = ""
    issuer_or_context: str = ""
    achieved_at: str | None = None
    review_cycle: str | None = None
    linked_milestone_id: str | None = None
    visibility: str = "manager"


class AchievementUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    description: str | None = None
    issuer_or_context: str | None = None
    achieved_at: str | None = None
    review_cycle: str | None = None
    linked_milestone_id: str | None = None
    visibility: str | None = None


class SelfAssessmentSuggestRequest(BaseModel):
    scope: str = Field(description="'goal' or 'overall'")
    milestone_id: str | None = None
    achievement_ids: list[str] = Field(default_factory=list)


@router.get("/employees/{employee_id}/achievements")
def list_employee_achievements(
    employee_id: str,
    review_cycle: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    include_private = _can_view_private(user, employee_id)
    cycle = review_cycle or current_review_cycle()
    rows = repo.list_achievements(employee_id, review_cycle=cycle, include_private=include_private)
    return [_achievement_response(r) for r in rows]


@router.post("/employees/{employee_id}/achievements")
def create_achievement(
    employee_id: str,
    body: AchievementCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not _can_write_achievements(user, employee_id):
        raise HTTPException(status_code=403, detail="Only the employee or HR can add achievements")
    if body.type not in ACHIEVEMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid achievement type")
    if body.visibility not in ("self", "manager"):
        raise HTTPException(status_code=400, detail="visibility must be self or manager")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if body.linked_milestone_id:
        ms = repo.get_milestone_by_id(body.linked_milestone_id)
        if not ms or ms["employee_id"] != employee_id:
            raise HTTPException(status_code=400, detail="Invalid milestone for this employee")
    row = repo.insert_achievement(
        {
            "employee_id": employee_id,
            "type": body.type,
            "title": body.title.strip(),
            "description": body.description.strip(),
            "issuer_or_context": body.issuer_or_context.strip(),
            "achieved_at": body.achieved_at,
            "review_cycle": body.review_cycle or current_review_cycle(),
            "linked_milestone_id": body.linked_milestone_id,
            "visibility": body.visibility,
            "source": "manual",
        }
    )
    return _achievement_response(row)


@router.patch("/employees/{employee_id}/achievements/{achievement_id}")
def update_achievement_entry(
    employee_id: str,
    achievement_id: str,
    body: AchievementUpdate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not _can_write_achievements(user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    existing = repo.get_achievement(achievement_id)
    if not existing or existing["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Achievement not found")
    updates = body.model_dump(exclude_unset=True)
    if "type" in updates and updates["type"] not in ACHIEVEMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid achievement type")
    if updates.get("visibility") and updates["visibility"] not in ("self", "manager"):
        raise HTTPException(status_code=400, detail="Invalid visibility")
    updated = repo.update_achievement(achievement_id, updates)
    return _achievement_response(updated or existing)


@router.delete("/employees/{employee_id}/achievements/{achievement_id}")
def delete_achievement_entry(
    employee_id: str,
    achievement_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not _can_write_achievements(user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    existing = repo.get_achievement(achievement_id)
    if not existing or existing["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Achievement not found")
    repo.delete_achievement(achievement_id)
    return {"deleted": True}


@router.post("/employees/{employee_id}/self-assessment/suggest")
async def suggest_self_assessment(
    employee_id: str,
    body: SelfAssessmentSuggestRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if user.employee_id != employee_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the employee can request self-assessment suggestions")
    if body.scope not in ("goal", "overall"):
        raise HTTPException(status_code=400, detail="scope must be goal or overall")

    emp = repo.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    start_trace("self_assessment_suggest", employee_id, user.user_id)
    trace = get_trace()

    all_achievements = repo.list_achievements(
        employee_id, review_cycle=current_review_cycle(), include_private=True
    )
    if body.achievement_ids:
        selected = [a for a in all_achievements if a["achievement_id"] in body.achievement_ids]
    else:
        selected = all_achievements

    milestone = None
    if body.scope == "goal":
        if not body.milestone_id:
            raise HTTPException(status_code=400, detail="milestone_id required for goal scope")
        milestone = repo.get_milestone_by_id(body.milestone_id)
        if not milestone or milestone["employee_id"] != employee_id:
            raise HTTPException(status_code=404, detail="Milestone not found")
        linked = [
            a
            for a in selected
            if a.get("linked_milestone_id") == body.milestone_id or not a.get("linked_milestone_id")
        ]
        selected = linked[:6]

    if trace:
        trace.load("achievements", f"{len(selected)} achievement(s) for suggestion", len(selected))

    ach_lines = []
    for a in selected[:8]:
        line = f"- [{a['type']}] {a['title']}"
        if a.get("description"):
            line += f": {a['description'][:200]}"
        if a.get("issuer_or_context"):
            line += f" ({a['issuer_or_context']})"
        ach_lines.append(line)
    achievements_block = "\n".join(ach_lines) if ach_lines else "No achievements on file."

    if body.scope == "goal" and milestone:
        goal_text = milestone.get("smart_goal") or milestone.get("raw_goal", "")
        prompt = f"""Write a first-person self-assessment paragraph (4-6 sentences) for this SMART goal.
Use ONLY the goal and achievements below. Be specific; do not invent facts.

Goal: {goal_text}

Achievements this cycle:
{achievements_block}

Return plain text only, no JSON."""
    else:
        milestones = repo.get_milestones_by_employee(employee_id)[:5]
        goal_lines = [
            f"- {(m.get('smart_goal') or m.get('raw_goal', ''))[:120]}"
            for m in milestones
        ]
        goals_block = "\n".join(goal_lines) if goal_lines else "No goals on file."
        prompt = f"""Write a first-person overall self-assessment (5-8 sentences) for {emp['name']} ({emp['job_title']}).
Cover progress on goals, key accomplishments, and development focus. Use ONLY the data below.

Goals:
{goals_block}

Achievements this cycle:
{achievements_block}

Return plain text only, no JSON."""

    if trace:
        trace.handoff("llm", "Draft self-assessment from achievements")

    try:
        suggested = (await ollama_complete(prompt=prompt, system="You help employees write honest self-assessments.")).strip()
    except Exception as exc:
        finish_trace(repo, status="failed", summary=str(exc)[:120])
        raise HTTPException(status_code=503, detail="AI suggestion unavailable") from exc

    if trace:
        trace.result(f"Generated {len(suggested)} chars")
    finish_trace(repo, summary="Self-assessment suggestion generated")

    return {"suggested_text": suggested, "achievements_used": len(selected)}
