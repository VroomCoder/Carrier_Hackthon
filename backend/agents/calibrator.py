import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_trace import finish_trace, get_trace, start_trace
from agents.calibration_core import run_calibration
from confidence_utils import smart_score_to_confidence
from auth import (
    CurrentUser,
    can_access_employee,
    get_current_user,
    require_employee_access,
    require_employee_self_or_admin,
)
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore

router = APIRouter()


class CalibrateRequest(BaseModel):
    goal: str
    employee_id: str | None = None
    milestone_id: str | None = None


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


@router.post("/calibrate")
async def calibrate(
    body: CalibrateRequest,
    user: CurrentUser = Depends(get_current_user),
    db_repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    """Employee re-calibrates an existing goal (needs_work or calibrated)."""
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="Goal is required")
    if not body.milestone_id:
        raise HTTPException(
            status_code=400,
            detail="Use goal accept for new suggestions. Re-calibrate requires milestone_id.",
        )

    employee_id = require_employee_access(db_repo, user, body.employee_id) or ""
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")
    require_employee_self_or_admin(user, employee_id)

    existing = db_repo.get_milestone_by_id(body.milestone_id)
    if not existing or existing["employee_id"] != employee_id:
        raise HTTPException(status_code=404, detail="Goal not found")
    if existing.get("status") == "suggested":
        raise HTTPException(
            status_code=400,
            detail="Accept the manager suggestion first, then re-calibrate if needed",
        )

    was_calibrated = existing.get("status") == "calibrated"

    start_trace("calibrator", employee_id, user.user_id)

    try:
        result = await run_calibration(
            goal,
            employee_id,
            db_repo,
            vector_store,
            linked_okr_id=existing.get("linked_okr_id"),
        )
    except json.JSONDecodeError as exc:
        finish_trace(db_repo, status="failed", summary="LLM parse error")
        raise HTTPException(
            status_code=422,
            detail="Failed to parse LLM response as JSON",
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
            f"{'Proposed revision' if was_calibrated else 'Goal marked'} — {status.replace('_', ' ')}",
            f"SMART overall {overall}/100"
            + (f"; gaps: {', '.join(gaps[:3])}" if gaps else ""),
            sources=["milestones", "okr_embeddings", "policy_chunks"],
        )

    finish_trace(
        db_repo,
        summary=(
            f"Revision submitted — score {overall} ({status.replace('_', ' ')})"
            if was_calibrated
            else f"Re-calibrated — score {overall} ({status.replace('_', ' ')})"
        ),
        confidence={"level": level, "score": conf_score, "reason": reason},
    )

    milestone = {
        **existing,
        "raw_goal": goal,
        "smart_goal": result.get("rewritten_goal", ""),
        "score_s": scores.get("S", 0),
        "score_m": scores.get("M", 0),
        "score_a": scores.get("A", 0),
        "score_r": scores.get("R", 0),
        "score_t": scores.get("T", 0),
        "overall_score": overall,
        "okr_alignment": result.get("okr_alignment", ""),
        "seniority_tier": result.get("seniority_tier", existing.get("seniority_tier", "")),
        "status": status,
    }
    db_repo.upsert_milestone(milestone)
    vector_store.sync_milestone(milestone)

    return {
        "scores": scores,
        "rewritten_goal": result.get("rewritten_goal", ""),
        "gaps": result.get("gaps", []),
        "okr_alignment": result.get("okr_alignment", ""),
        "policy_references": [],
        "seniority_tier": milestone["seniority_tier"],
        "role_benchmark": result.get("role_benchmark", ""),
        "overall": overall,
        "milestone_id": body.milestone_id,
        "status": status,
    }
