import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_trace import finish_trace, get_trace, start_trace
from agents.calibration_core import run_calibration
from confidence_utils import smart_score_to_confidence
from ollama_client import ollama_complete
from auth import (
    CurrentUser,
    can_access_employee,
    get_current_user,
    require_employee_self_or_admin,
    require_goal_management,
)
from cycle_config import REQUIRED_GOAL_COUNT
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore

router = APIRouter()


class SuggestGoalRequest(BaseModel):
    raw_goal: str
    linked_okr_id: str | None = None


class AcceptGoalRequest(BaseModel):
    revised_goal: str | None = None


class DraftGoalSuggestionRequest(BaseModel):
    linked_okr_id: str | None = None
    manager_notes: str = ""


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


def _goal_response(m: dict) -> dict:
    return {
        "id": m["id"],
        "employee_id": m["employee_id"],
        "raw_goal": m["raw_goal"],
        "smart_goal": m.get("smart_goal"),
        "overall_score": m.get("overall_score", 0),
        "status": m.get("status", "suggested"),
        "seniority_tier": m.get("seniority_tier", ""),
        "created_at": m.get("created_at", ""),
        "updated_at": m.get("updated_at", ""),
        "suggested_by": m.get("suggested_by"),
        "manager_suggestion": m.get("manager_suggestion", ""),
        "linked_okr_id": m.get("linked_okr_id"),
        "source_okr_id": m.get("source_okr_id"),
        "employee_self_assessment": m.get("employee_self_assessment", ""),
        "self_assessment_updated_at": m.get("self_assessment_updated_at"),
    }


@router.post("/employees/{employee_id}/goals/suggest")
def suggest_goal(
    employee_id: str,
    body: SuggestGoalRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_goal_management(repo, user, employee_id)

    raw_goal = body.raw_goal.strip()
    if not raw_goal:
        raise HTTPException(status_code=400, detail="Goal suggestion text is required")

    if len(repo.get_milestones_by_employee(employee_id)) >= REQUIRED_GOAL_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {REQUIRED_GOAL_COUNT} goals per employee (including suggestions)",
        )

    if body.linked_okr_id:
        if not repo.has_okr_assignment(employee_id, body.linked_okr_id):
            raise HTTPException(
                status_code=400,
                detail="Link goal to an OKR that is already assigned to this employee",
            )

    if not user.employee_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="No employee profile linked")

    milestone = repo.create_suggested_goal(
        employee_id=employee_id,
        raw_goal=raw_goal,
        suggested_by=user.employee_id or "admin",
        linked_okr_id=body.linked_okr_id,
    )
    return _goal_response(milestone)


@router.post("/employees/{employee_id}/goals/draft-suggestion")
async def draft_goal_suggestion(
    employee_id: str,
    body: DraftGoalSuggestionRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    """AI-draft a SMART goal suggestion for a manager to review before sending."""
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_goal_management(repo, user, employee_id)

    emp = repo.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if len(repo.get_milestones_by_employee(employee_id)) >= REQUIRED_GOAL_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {REQUIRED_GOAL_COUNT} goals per employee (including suggestions)",
        )

    if body.linked_okr_id and not repo.has_okr_assignment(employee_id, body.linked_okr_id):
        raise HTTPException(
            status_code=400,
            detail="Link goal to an OKR that is already assigned to this employee",
        )

    start_trace("goal_suggestion_draft", employee_id, user.user_id)
    trace = get_trace()

    role_context = f"{emp['name']}, {emp['job_title']} in {emp['department']} / {emp['sub_department']}."
    node = repo.get_org_node(emp["department"], emp["sub_department"], emp["job_title"])
    if node:
        role_context += (
            f" Seniority: {node['seniority_tier']}. "
            f"Goals at this level should: {node['focus_description']}"
        )
    if trace:
        trace.load("employee_profile", f"{emp['name']} — {emp['job_title']}")

    assignments = repo.get_okr_assignments_for_employee(employee_id)
    okr_lines = []
    for a in assignments:
        okr_lines.append(f"- [{a['category']}] {a['title']}: {a['description'][:200]}")
    okr_block = "\n".join(okr_lines) if okr_lines else "No OKRs assigned yet."
    if trace and assignments:
        trace.load("assigned_okrs", f"{len(assignments)} assigned OKR(s)", len(assignments))

    linked_okr_block = ""
    if body.linked_okr_id:
        okr = repo.get_okr_by_id(body.linked_okr_id)
        if okr:
            linked_okr_block = (
                f"\nPrimary OKR to align this goal with:\n"
                f"[{okr['category']}] {okr['title']}: {okr['description']}"
            )

    existing = repo.get_milestones_by_employee(employee_id)
    existing_lines = [
        f"- {(m.get('smart_goal') or m.get('raw_goal', ''))[:140]} ({m.get('status', 'suggested')})"
        for m in existing
    ]
    existing_block = (
        "\n".join(existing_lines) if existing_lines else "None yet — this may be their first goal."
    )
    if trace and existing:
        trace.load("milestones", f"{len(existing)} existing goal(s)", len(existing))

    notes = body.manager_notes.strip()
    notes_block = f"\nManager intent / notes:\n{notes}" if notes else ""

    prompt = f"""Draft ONE individual performance goal for the employee below.
The goal will be suggested by their manager; the employee will accept and calibrate it later.

Employee:
{role_context}

Assigned OKRs:
{okr_block}
{linked_okr_block}

Existing goals (do not duplicate; complement gaps):
{existing_block}
{notes_block}

Rules:
- One sentence, specific and measurable (include a number or clear deliverable where possible).
- Appropriate for their role and seniority; aligned to assigned OKRs.
- Action-oriented; avoid vague wording like "improve" without a target.
- Do not invent projects or metrics not implied by the OKRs or manager notes.

Return plain text only — the goal sentence, no JSON or bullet labels."""

    if trace:
        trace.handoff("llm", "Draft manager goal suggestion")

    try:
        suggested = (
            await ollama_complete(
                prompt=prompt,
                system="You help managers write SMART individual goals for direct reports.",
            )
        ).strip()
    except Exception as exc:
        finish_trace(repo, status="failed", summary=str(exc)[:120])
        raise HTTPException(status_code=503, detail="AI goal draft unavailable") from exc

    if not suggested:
        finish_trace(repo, status="failed", summary="Empty LLM response")
        raise HTTPException(status_code=503, detail="AI goal draft unavailable")

    if trace:
        trace.result(f"Drafted {len(suggested)} chars")
    finish_trace(repo, summary="Manager goal suggestion drafted")

    return {"suggested_goal": suggested, "linked_okr_id": body.linked_okr_id}


@router.post("/employees/{employee_id}/goals/{goal_id}/accept")
async def accept_goal(
    employee_id: str,
    goal_id: str,
    body: AcceptGoalRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_employee_self_or_admin(user, employee_id)

    milestone = repo.get_milestone_by_id(goal_id)
    if not milestone or milestone["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Goal not found")
    if milestone.get("status") != "suggested":
        raise HTTPException(
            status_code=400,
            detail="Only suggested goals can be accepted. Calibrated goals use re-calibrate.",
        )

    goal_text = (body.revised_goal or milestone["raw_goal"]).strip()
    if not goal_text:
        raise HTTPException(status_code=400, detail="Goal text is required")

    start_trace("calibrator", employee_id, user.user_id)

    try:
        result = await run_calibration(
            goal_text,
            employee_id,
            repo,
            vector_store,
            linked_okr_id=milestone.get("linked_okr_id"),
        )
    except json.JSONDecodeError as exc:
        finish_trace(repo, status="failed", summary="LLM parse error")
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse LLM response as JSON",
        ) from exc

    scores = result.get("scores", {})
    overall = result.get("overall", 0)
    status = "calibrated" if overall >= 75 else "needs_work"
    level, conf_score, reason = smart_score_to_confidence(overall, status)
    trace = get_trace()
    if trace:
        trace.confidence(level, conf_score, reason)
        gaps = result.get("gaps") or []
        trace.decision(
            f"Accepted goal — {status.replace('_', ' ')}",
            f"SMART overall {overall}/100"
            + (f"; gaps: {', '.join(gaps[:3])}" if gaps else ""),
            sources=["milestones", "okr_embeddings", "policy_chunks"],
        )

    finish_trace(
        repo,
        summary=f"Goal accepted — score {overall} ({status.replace('_', ' ')})",
        confidence={"level": level, "score": conf_score, "reason": reason},
    )

    updated = {
        **milestone,
        "raw_goal": goal_text,
        "smart_goal": result.get("rewritten_goal", ""),
        "score_s": scores.get("S", 0),
        "score_m": scores.get("M", 0),
        "score_a": scores.get("A", 0),
        "score_r": scores.get("R", 0),
        "score_t": scores.get("T", 0),
        "overall_score": overall,
        "okr_alignment": result.get("okr_alignment", ""),
        "seniority_tier": result.get("seniority_tier", milestone.get("seniority_tier", "")),
        "status": status,
    }
    repo.upsert_milestone(updated)
    vector_store.sync_milestone(updated)

    return {
        **_goal_response(updated),
        "scores": scores,
        "gaps": result.get("gaps", []),
        "role_benchmark": result.get("role_benchmark", ""),
        "overall": overall,
    }


@router.put("/employees/{employee_id}/goals/{goal_id}/revise")
def revise_suggested_goal(
    employee_id: str,
    goal_id: str,
    body: SuggestGoalRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_employee_self_or_admin(user, employee_id)

    milestone = repo.get_milestone_by_id(goal_id)
    if not milestone or milestone["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Goal not found")
    if milestone.get("status") != "suggested":
        raise HTTPException(status_code=400, detail="Only pending suggestions can be revised")

    raw_goal = body.raw_goal.strip()
    if not raw_goal:
        raise HTTPException(status_code=400, detail="Goal text is required")

    updated = {**milestone, "raw_goal": raw_goal}
    repo.upsert_milestone(updated)
    return _goal_response(repo.get_milestone_by_id(goal_id) or updated)


@router.delete("/employees/{employee_id}/goals/{goal_id}")
def delete_goal(
    employee_id: str,
    goal_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")

    milestone = repo.get_milestone_by_id(goal_id)
    if not milestone or milestone["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Goal not found")

    status = milestone.get("status", "")
    if status == "suggested":
        require_goal_management(repo, user, employee_id)
    elif user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only managers can remove pending suggestions",
        )

    if not repo.delete_milestone(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    try:
        vector_store.milestone_embeddings.delete(ids=[goal_id])
    except Exception:
        pass
    return {"deleted": True, "id": goal_id}
