"""Session-based auth: HR (admin role) or employee login; manager derived from org hierarchy."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from db.sqlite_repo import SqliteRepo

SESSION_HOURS = 24
EMPLOYEE_DEMO_PIN = "employee"
ADMIN_DEMO_PIN = "admin"


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


@dataclass
class CurrentUser:
    user_id: str
    employee_id: str | None
    role: str
    display_name: str
    is_manager: bool = False


def user_is_manager(repo: SqliteRepo, employee_id: str | None) -> bool:
    if not employee_id:
        return False
    return len(repo.get_direct_reports(employee_id)) > 0


def build_current_user(repo: SqliteRepo, user: dict) -> CurrentUser:
    employee_id = user.get("employee_id")
    is_manager = user["role"] == "employee" and user_is_manager(repo, employee_id)
    return CurrentUser(
        user_id=user["user_id"],
        employee_id=employee_id,
        role=user["role"],
        display_name=user["display_name"],
        is_manager=is_manager,
    )


def get_accessible_employee_ids(repo: SqliteRepo, user: CurrentUser) -> list[str] | None:
    """Return allowed employee IDs, or None for unrestricted (HR)."""
    if user.role == "admin":
        return None
    if not user.employee_id:
        return []
    if user.is_manager:
        ids = [user.employee_id]
        for report in repo.get_direct_reports(user.employee_id):
            ids.append(report["employee_id"])
        return ids
    return [user.employee_id]


def can_access_employee(repo: SqliteRepo, user: CurrentUser, employee_id: str) -> bool:
    allowed = get_accessible_employee_ids(repo, user)
    if allowed is None:
        return True
    return employee_id in allowed


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="HR access required")


def require_manager_or_admin(user: CurrentUser) -> None:
    if user.role != "admin" and not user.is_manager:
        raise HTTPException(status_code=403, detail="Manager or HR access required")


def is_direct_report(repo: SqliteRepo, manager_employee_id: str, employee_id: str) -> bool:
    return employee_id in {
        r["employee_id"] for r in repo.get_direct_reports(manager_employee_id)
    }


def can_manage_employee_goals(
    repo: SqliteRepo, user: CurrentUser, employee_id: str
) -> bool:
    """Managers may set OKRs/goals for direct reports; HR for any employee."""
    if user.role == "admin":
        return True
    if not user.is_manager or not user.employee_id:
        return False
    return is_direct_report(repo, user.employee_id, employee_id)


def require_employee_self_or_admin(
    user: CurrentUser, employee_id: str
) -> None:
    if user.role == "admin":
        return
    if user.employee_id != employee_id:
        raise HTTPException(
            status_code=403,
            detail="Only the employee can accept and calibrate their own goals",
        )


def require_goal_management(
    repo: SqliteRepo, user: CurrentUser, employee_id: str
) -> None:
    if not can_manage_employee_goals(repo, user, employee_id):
        raise HTTPException(
            status_code=403,
            detail="Only managers can assign OKRs or suggest goals for their direct reports",
        )


def require_employee_access(
    repo: SqliteRepo, user: CurrentUser, employee_id: str | None
) -> str | None:
    """Validate employee_id access; default to self for employee logins."""
    if user.role == "admin":
        return employee_id
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="No employee profile linked to this account")
    if employee_id:
        if not can_access_employee(repo, user, employee_id):
            raise HTTPException(status_code=403, detail="Access denied for this employee")
        return employee_id
    return user.employee_id


def require_coach_employee_id(
    repo: SqliteRepo, user: CurrentUser, employee_id: str | None
) -> str | None:
    """Growth Coach is self-only for employee logins (including managers)."""
    if user.role == "admin":
        return employee_id
    if not user.employee_id:
        raise HTTPException(
            status_code=403,
            detail="No employee profile linked to this account",
        )
    if employee_id and employee_id != user.employee_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Growth Coach is for your own development only. "
                "Use Team health and feedback tools to support direct reports."
            ),
        )
    return user.employee_id


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()


def resolve_user_from_token(repo: SqliteRepo, token: str) -> CurrentUser | None:
    session = repo.get_auth_session(token)
    if not session:
        return None
    user = repo.get_app_user_by_id(session["user_id"])
    if not user:
        return None
    return build_current_user(repo, user)


def get_current_user_optional(
    authorization: Annotated[str | None, Header()] = None,
    repo: SqliteRepo = Depends(get_db_repo),
) -> CurrentUser | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    return resolve_user_from_token(repo, token)


def get_current_user(
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
    return user


def user_payload(user: CurrentUser) -> dict:
    return {
        "user_id": user.user_id,
        "role": user.role,
        "display_name": user.display_name,
        "employee_id": user.employee_id,
        "is_manager": user.is_manager,
    }


def authenticate_admin(repo: SqliteRepo, pin: str) -> dict | None:
    return repo.authenticate_user("user_admin", pin)


def authenticate_employee(repo: SqliteRepo, employee_id: str, pin: str) -> dict | None:
    if pin != EMPLOYEE_DEMO_PIN:
        return None
    emp = repo.get_employee_by_id(employee_id.strip())
    if not emp:
        return None
    user_id = f"emp_{employee_id}"
    user_record = {
        "user_id": user_id,
        "employee_id": employee_id,
        "role": "employee",
        "display_name": emp["name"],
        "pin": EMPLOYEE_DEMO_PIN,
    }
    repo.upsert_app_user(user_record)
    return user_record


APP_USERS_SEED = [
    {
        "user_id": "user_admin",
        "employee_id": None,
        "role": "admin",
        "display_name": "HR",
        "pin": ADMIN_DEMO_PIN,
    },
]


def seed_app_users(repo: SqliteRepo) -> int:
    repo.migrate_legacy_manager_users()
    if repo.count_app_users() == 0:
        for user in APP_USERS_SEED:
            repo.upsert_app_user(user)
        return len(APP_USERS_SEED)
    admin = repo.get_app_user_by_id("user_admin")
    if admin and admin.get("display_name") != "HR":
        repo.upsert_app_user({**admin, "display_name": "HR"})
    return 0
