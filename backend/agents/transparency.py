"""Transparency APIs — coverage, workflow traces, explainability."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_trace import AGENT_LABELS, agent_label
from auth import CurrentUser, can_access_employee, get_current_user
from db.sqlite_repo import SqliteRepo

router = APIRouter(prefix="/transparency", tags=["transparency"])

TRACKED_AGENTS = (
    "coach",
    "calibrator",
    "synthesiser",
    "review_drafter",
    "feedback_summary",
)


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


@router.get("/coverage")
def confidence_coverage(
    employee_id: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if employee_id and not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return repo.get_transparency_coverage(employee_id)


@router.get("/workflows")
def list_workflows(
    employee_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=30),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if employee_id and not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return repo.list_workflow_runs(employee_id, limit=limit)


@router.get("/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    run = repo.get_workflow_run(workflow_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if run.get("employee_id") and not can_access_employee(
        repo, user, run["employee_id"]
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    traces = repo.list_agent_activity_by_workflow(workflow_id)
    return {
        **run,
        "traces": [
            {
                "id": t["id"],
                "agent": t["agent"],
                "agent_label": agent_label(t["agent"]),
                "status": t.get("status"),
                "summary": t.get("summary", ""),
                "duration_ms": t.get("duration_ms", 0),
                "confidence_level": t.get("confidence_level"),
                "confidence_score": t.get("confidence_score"),
                "confidence_reason": t.get("confidence_reason"),
                "rationale": t.get("rationale"),
                "created_at": t.get("created_at", ""),
            }
            for t in traces
        ],
    }


@router.get("/agents")
def list_tracked_agents():
    return {
        "agents": [
            {"id": a, "label": AGENT_LABELS.get(a, a.replace("_", " ").title())}
            for a in TRACKED_AGENTS
        ]
    }
