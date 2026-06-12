"""Manager assigns company OKRs to employees (alignment layer, not goals)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import (
    CurrentUser,
    can_access_employee,
    get_current_user,
    require_goal_management,
)
from cycle_config import DEFAULT_CYCLE, REQUIRED_GOAL_COUNT
from db.sqlite_repo import SqliteRepo

router = APIRouter()


class AssignOkrRequest(BaseModel):
    okr_id: str
    cycle: str = DEFAULT_CYCLE


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def _assignment_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "employee_id": row["employee_id"],
        "okr_id": row["okr_id"],
        "assigned_by": row["assigned_by"],
        "cycle": row.get("cycle", DEFAULT_CYCLE),
        "created_at": row.get("created_at", ""),
        "title": row.get("title", ""),
        "description": row.get("description", ""),
        "category": row.get("category", ""),
        "owner": row.get("owner", ""),
    }


@router.get("/employees/{employee_id}/okr-assignments")
def list_okr_assignments(
    employee_id: str,
    cycle: str = DEFAULT_CYCLE,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    rows = repo.get_okr_assignments_for_employee(employee_id, cycle=cycle)
    return [_assignment_response(r) for r in rows]


@router.post("/employees/{employee_id}/okr-assignments")
def assign_okr(
    employee_id: str,
    body: AssignOkrRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_goal_management(repo, user, employee_id)

    okr = repo.get_okr_by_id(body.okr_id)
    if not okr or okr.get("status") != "active":
        raise HTTPException(status_code=404, detail="Company OKR not found")

    count = repo.count_okr_assignments(employee_id, body.cycle)
    if count >= REQUIRED_GOAL_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {REQUIRED_GOAL_COUNT} OKRs can be assigned per employee",
        )
    if repo.has_okr_assignment(employee_id, body.okr_id, body.cycle):
        raise HTTPException(status_code=400, detail="This OKR is already assigned")

    if not user.employee_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="No employee profile linked")

    assigned_by = user.employee_id or "admin"
    row = repo.create_okr_assignment(
        employee_id=employee_id,
        okr_id=body.okr_id,
        assigned_by=assigned_by,
        cycle=body.cycle,
    )
    return _assignment_response(row)


@router.delete("/employees/{employee_id}/okr-assignments/{assignment_id}")
def remove_okr_assignment(
    employee_id: str,
    assignment_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    require_goal_management(repo, user, employee_id)

    if not repo.delete_okr_assignment(assignment_id, employee_id):
        raise HTTPException(status_code=404, detail="OKR assignment not found")
    return {"deleted": True, "id": assignment_id}
