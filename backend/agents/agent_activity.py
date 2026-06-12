"""API for agent activity trace feed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_trace import agent_label
from auth import (
    CurrentUser,
    can_access_employee,
    get_current_user,
    require_employee_access,
)
from db.sqlite_repo import SqliteRepo

router = APIRouter()


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def _normalize_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        item = dict(step)
        item["type"] = item.pop("kind", item.get("type", "result"))
        if item["type"] == "search" and "hits" in item and "hit_count" not in item:
            item["hit_count"] = item["hits"]
        out.append(item)
    return out


@router.get("/agent-activity")
def list_agent_activity(
    employee_id: str | None = Query(None),
    limit: int = Query(15, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if employee_id:
        if not can_access_employee(repo, user, employee_id):
            raise HTTPException(status_code=403, detail="Access denied for this employee")
    elif user.role != "admin":
        employee_id = require_employee_access(repo, user, user.employee_id)
        if not employee_id:
            return []

    rows = repo.list_agent_activity(employee_id, limit=limit)
    return [
        {
            "id": row["id"],
            "agent": row["agent"],
            "agent_label": agent_label(row["agent"]),
            "employee_id": row.get("employee_id"),
            "workflow_id": row.get("workflow_id"),
            "status": row.get("status", "completed"),
            "summary": row.get("summary", ""),
            "duration_ms": row.get("duration_ms", 0),
            "confidence_level": row.get("confidence_level"),
            "confidence_score": row.get("confidence_score"),
            "confidence_reason": row.get("confidence_reason"),
            "rationale": row.get("rationale"),
            "steps": _normalize_steps(row.get("steps", [])),
            "created_at": row.get("created_at", ""),
        }
        for row in rows
    ]
