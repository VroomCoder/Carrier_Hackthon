"""Team health dashboard API — /api/team-health."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from agents.health_scoring_agent import (
    SUGGESTED_ACTIONS,
    compute_employee_health,
    run_health_scoring_for_all,
    run_health_scoring_for_team,
)
from auth import CurrentUser, can_access_employee, get_current_user
from db.sqlite_repo import SqliteRepo
from feedback_cycle import current_review_cycle

router = APIRouter(prefix="/team-health", tags=["team-health"])

TEAM_STALE_HOURS = 24
EMPLOYEE_STALE_HOURS = 6


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def _can_view_manager_team(repo: SqliteRepo, user: CurrentUser, manager_id: str) -> bool:
    if user.role == "admin":
        return True
    return user.employee_id == manager_id and user.is_manager


def _is_stale(computed_at: str | None, hours: int) -> bool:
    if not computed_at:
        return True
    try:
        if "T" in computed_at:
            dt = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(computed_at[:19], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        age = datetime.now(timezone.utc) - dt
        return age.total_seconds() > hours * 3600
    except ValueError:
        return True


def _score_to_response(score: dict, emp: dict | None = None) -> dict:
    out = {k: v for k, v in score.items() if not k.startswith("_")}
    if emp:
        out.update(
            {
                "name": emp.get("name", ""),
                "job_title": emp.get("job_title", ""),
                "department": emp.get("department", ""),
                "sub_department": emp.get("sub_department", ""),
                "grade": emp.get("grade", ""),
                "location": emp.get("location", ""),
                "work_mode": emp.get("work_mode", ""),
            }
        )
    return out


def _build_team_payload(repo: SqliteRepo, manager_id: str) -> dict:
    reports = repo.get_direct_reports(manager_id)
    scores = repo.get_all_health_scores(manager_id=manager_id)
    score_by_id = {s["employee_id"]: s for s in scores}
    employees = []
    alerts = []
    for emp in reports:
        sc = score_by_id.get(emp["employee_id"])
        if not sc:
            sc = compute_employee_health(emp["employee_id"], repo)
            repo.upsert_health_score(sc)
        card = _score_to_response(sc, emp)
        card["last_feedback_snippet"] = repo.get_latest_shared_feedback_snippet(
            emp["employee_id"]
        )
        employees.append(card)
        if sc["rag_status"] != "on_track":
            reasons = sc.get("at_risk_reasons") or []
            name = emp.get("name", emp["employee_id"])
            actions = [
                SUGGESTED_ACTIONS[r].format(name=name)
                for r in reasons
                if r in SUGGESTED_ACTIONS
            ]
            alerts.append(
                {
                    "employee_id": emp["employee_id"],
                    "name": name,
                    "rag_status": sc["rag_status"],
                    "composite_score": sc["composite_score"],
                    "at_risk_reasons": reasons,
                    "suggested_actions": actions,
                }
            )
    employees.sort(key=lambda e: e.get("composite_score", 0))
    alerts.sort(key=lambda a: a["composite_score"])
    last_computed = max((e.get("computed_at") for e in employees), default=None)
    return {
        "team_summary": repo.get_team_health_summary(manager_id),
        "employees": employees,
        "alerts": alerts,
        "last_computed": last_computed,
    }


@router.get("/team")
async def get_team_health(
    manager_id: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not _can_view_manager_team(repo, user, manager_id):
        raise HTTPException(status_code=403, detail="Access denied")
    reports = repo.get_direct_reports(manager_id)
    if not reports:
        return {
            "team_summary": {
                "total": 0,
                "on_track": 0,
                "needs_attention": 0,
                "at_risk": 0,
                "avg_score": 0,
                "avg_goal_quality": 0,
                "avg_feedback_coverage": 0,
                "avg_checkin_recency": 0,
            },
            "employees": [],
            "alerts": [],
            "last_computed": None,
        }

    cached = repo.get_all_health_scores(manager_id=manager_id)
    stale = not cached or any(_is_stale(s.get("computed_at"), TEAM_STALE_HOURS) for s in cached)
    if stale or len(cached) < len(reports):
        await run_health_scoring_for_team(manager_id, repo)
    return _build_team_payload(repo, manager_id)


@router.get("/employee/{employee_id}")
async def get_employee_health(
    employee_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = repo.get_health_score(employee_id)
    if not row or _is_stale(row.get("computed_at"), EMPLOYEE_STALE_HOURS):
        row = compute_employee_health(employee_id, repo)
        repo.upsert_health_score(row)
    emp = repo.get_employee_by_id(employee_id)
    out = _score_to_response(row, emp)
    out["milestones"] = repo.get_milestones_by_employee(employee_id)
    cycle = current_review_cycle()
    out["feedback_entries"] = repo.get_entries_for_employee(
        employee_id, review_cycle=cycle, include_drafts=False
    )[:5]
    out["feedback_summary"] = (
        repo.get_feedback_summary(employee_id, cycle, "mid_year")
        or repo.get_feedback_summary(employee_id, cycle, "year_end")
    )
    return out


@router.post("/refresh")
async def refresh_team_health(
    manager_id: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not _can_view_manager_team(repo, user, manager_id):
        raise HTTPException(status_code=403, detail="Access denied")
    await run_health_scoring_for_team(manager_id, repo)
    return _build_team_payload(repo, manager_id)


@router.post("/refresh/all")
async def refresh_all_health(
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="HR only")
    return await run_health_scoring_for_all(repo)
