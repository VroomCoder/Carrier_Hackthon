"""Deterministic employee health scoring from SQLite data."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from cycle_config import REQUIRED_GOAL_COUNT
from feedback_cycle import current_review_cycle

SUGGESTED_ACTIONS: dict[str, str] = {
    "Goals not calibrated": "Schedule a goal-setting conversation with {name}",
    "No recent check-in": "Book a 1:1 coaching session with {name} this week",
    "Insufficient feedback this cycle": "Log at least 2 feedback entries for {name}",
    "Not ready for review": (
        "{name}'s review package is incomplete — check goals, feedback, and summary"
    ),
    "Performance trajectory declining": "Review recent feedback with {name} and agree a support plan",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if " " in value:
            return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _days_since(value: str | None) -> int | None:
    dt = _parse_dt(value)
    if not dt:
        return None
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _score_goal_quality(milestones: list[dict]) -> tuple[float, dict]:
    total = len(milestones)
    calibrated = [m for m in milestones if m.get("status") == "calibrated"]
    needs_work = [m for m in milestones if m.get("status") == "needs_work"]
    suggested = [m for m in milestones if m.get("status") == "suggested"]

    last_updated = None
    for m in milestones:
        u = m.get("updated_at")
        if u and (not last_updated or u > last_updated):
            last_updated = u

    avg_smart = 0.0
    if calibrated:
        avg_smart = sum(m.get("overall_score", 0) or 0 for m in calibrated) / len(calibrated)

    subs = {
        "goals_total": total,
        "goals_calibrated": len(calibrated),
        "goals_needs_work": len(needs_work) + len(suggested),
        "avg_smart_score": round(avg_smart, 1),
        "last_goal_updated": last_updated,
    }

    if total == 0:
        return 0.0, subs
    if not calibrated:
        if needs_work and not suggested:
            return 20.0, subs
        return 30.0, subs
    if len(calibrated) < total:
        return 50.0, subs
    if avg_smart < 60:
        return 60.0, subs
    if avg_smart < 80:
        return 80.0, subs
    return 100.0, subs


def _score_checkin(last_session: dict | None, total_sessions: int) -> tuple[float, dict]:
    last_date = last_session.get("updated_at") if last_session else None
    days = _days_since(last_date)
    subs = {
        "last_checkin_date": last_date,
        "days_since_checkin": days,
        "total_sessions": total_sessions,
    }
    if not last_session or days is None:
        return 0.0, subs
    if days > 90:
        return 20.0, subs
    if days > 30:
        return 50.0, subs
    if days > 14:
        return 75.0, subs
    return 100.0, subs


def _score_feedback(entries: list[dict], review_cycle: str) -> tuple[float, dict]:
    cycle_entries = [
        e for e in entries if e.get("review_cycle") == review_cycle and not e.get("is_draft")
    ]
    count = len(cycle_entries)
    sent_counts = {"positive": 0, "constructive": 0, "neutral": 0}
    last_date = None
    for e in entries:
        s = e.get("sentiment", "neutral")
        if s in sent_counts:
            sent_counts[s] += 1
        elif s == "negative":
            sent_counts["constructive"] += 1
        else:
            sent_counts["neutral"] += 1
        created = e.get("created_at")
        if created and (not last_date or created > last_date):
            last_date = created

    if count == 0:
        score = 0.0
    elif count == 1:
        score = 30.0
    elif count == 2:
        score = 55.0
    elif count == 3:
        score = 70.0
    elif count == 4:
        score = 85.0
    else:
        score = 100.0

    balanced = sent_counts["positive"] > 0 and sent_counts["constructive"] > 0
    if balanced:
        score = min(100.0, score + 10.0)

    subs = {
        "feedback_count_cycle": count,
        "feedback_count_total": len([e for e in entries if not e.get("is_draft")]),
        "last_feedback_date": last_date,
        "days_since_feedback": _days_since(last_date),
        "sentiment_positive": sent_counts["positive"],
        "sentiment_constructive": sent_counts["constructive"],
        "sentiment_neutral": sent_counts["neutral"],
        "has_balanced_feedback": balanced,
    }
    return score, subs


def _score_review_readiness(
    has_calibrated: bool,
    has_feedback_cycle: bool,
    has_summary: bool,
    had_recent_checkin: bool,
) -> tuple[float, dict]:
    points = 0
    if has_calibrated:
        points += 25
    if has_feedback_cycle:
        points += 25
    if has_summary:
        points += 25
    if had_recent_checkin:
        points += 25
    subs = {
        "has_calibrated_goal": has_calibrated,
        "has_feedback_cycle": has_feedback_cycle,
        "has_summary": has_summary,
        "had_recent_checkin": had_recent_checkin,
    }
    return float(points), subs


def _score_trajectory(summary: dict | None) -> tuple[float, dict]:
    if not summary:
        return 50.0, {"trajectory": "insufficient_data", "trajectory_source": "none"}
    traj = summary.get("trajectory", "insufficient_data")
    mapping = {
        "improving": 100.0,
        "steady": 70.0,
        "declining": 20.0,
        "insufficient_data": 40.0,
    }
    return mapping.get(traj, 40.0), {"trajectory": traj, "trajectory_source": "summary"}


def _rag_status(composite: float) -> str:
    if composite >= 70:
        return "on_track"
    if composite >= 45:
        return "needs_attention"
    return "at_risk"


def _at_risk_reasons(
    goal_score: float,
    checkin_score: float,
    feedback_score: float,
    readiness_score: float,
    trajectory: str,
) -> list[str]:
    reasons: list[str] = []
    if goal_score < 40:
        reasons.append("Goals not calibrated")
    if checkin_score < 40:
        reasons.append("No recent check-in")
    if feedback_score < 40:
        reasons.append("Insufficient feedback this cycle")
    if readiness_score < 30:
        reasons.append("Not ready for review")
    if trajectory == "declining":
        reasons.append("Performance trajectory declining")
    return reasons


def compute_employee_health(employee_id: str, db_repo) -> dict:
    """Pure computation — reads SQLite, returns score dict."""
    review_cycle = current_review_cycle()
    milestones = db_repo.get_milestones_by_employee(employee_id)
    goal_score, goal_subs = _score_goal_quality(milestones)

    last_session = db_repo.get_latest_session_for_employee(employee_id)
    total_sessions = db_repo.count_sessions_for_employee(employee_id)
    checkin_score, checkin_subs = _score_checkin(last_session, total_sessions)

    entries = db_repo.get_entries_for_employee(employee_id, include_drafts=False)
    feedback_score, feedback_subs = _score_feedback(entries, review_cycle)

    summary = (
        db_repo.get_feedback_summary(employee_id, review_cycle, "mid_year")
        or db_repo.get_feedback_summary(employee_id, review_cycle, "year_end")
        or db_repo.get_latest_summary(employee_id, "mid_year")
    )
    trajectory_score, traj_subs = _score_trajectory(summary)

    has_calibrated = goal_subs["goals_calibrated"] > 0
    has_feedback_cycle = feedback_subs["feedback_count_cycle"] > 0
    has_summary = summary is not None
    days_checkin = checkin_subs.get("days_since_checkin")
    had_recent_checkin = days_checkin is not None and days_checkin <= 30

    readiness_score, readiness_subs = _score_review_readiness(
        has_calibrated, has_feedback_cycle, has_summary, had_recent_checkin
    )

    composite = round(
        goal_score * 0.30
        + checkin_score * 0.20
        + feedback_score * 0.25
        + readiness_score * 0.15
        + trajectory_score * 0.10,
        1,
    )
    rag = _rag_status(composite)
    reasons = _at_risk_reasons(
        goal_score,
        checkin_score,
        feedback_score,
        readiness_score,
        traj_subs["trajectory"],
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "score_id": f"hs_{uuid.uuid4().hex[:8]}",
        "employee_id": employee_id,
        "composite_score": composite,
        "rag_status": rag,
        "goal_quality_score": goal_score,
        "checkin_score": checkin_score,
        "feedback_score": feedback_score,
        "review_readiness": readiness_score,
        "trajectory_score": trajectory_score,
        **goal_subs,
        **checkin_subs,
        **feedback_subs,
        **readiness_subs,
        **traj_subs,
        "at_risk_reasons": reasons,
        "computed_at": now,
        "review_cycle": review_cycle,
        "_required_goals": REQUIRED_GOAL_COUNT,
    }


def _build_alerts(employees: list[dict], scores: list[dict]) -> list[dict]:
    by_id = {s["employee_id"]: s for s in scores}
    alerts = []
    for emp in employees:
        score = by_id.get(emp["employee_id"])
        if not score or score["rag_status"] == "on_track":
            continue
        reasons = score.get("at_risk_reasons") or []
        if not reasons and score["rag_status"] != "at_risk":
            continue
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
                "rag_status": score["rag_status"],
                "composite_score": score["composite_score"],
                "at_risk_reasons": reasons,
                "suggested_actions": actions,
            }
        )
    alerts.sort(key=lambda a: a["composite_score"])
    return alerts


async def run_health_scoring_for_team(manager_id: str, db_repo) -> dict:
    reports = db_repo.get_direct_reports(manager_id)
    scored_rows = []
    for emp in reports:
        score = compute_employee_health(emp["employee_id"], db_repo)
        db_repo.upsert_health_score(score)
        scored_rows.append(score)

    team_summary = db_repo.get_team_health_summary(manager_id)
    alerts = _build_alerts(reports, scored_rows)
    on_track = sum(1 for s in scored_rows if s["rag_status"] == "on_track")
    needs_attention = sum(1 for s in scored_rows if s["rag_status"] == "needs_attention")
    at_risk = sum(1 for s in scored_rows if s["rag_status"] == "at_risk")
    last_computed = max((s["computed_at"] for s in scored_rows), default=None)

    return {
        "scored": len(scored_rows),
        "at_risk": at_risk,
        "needs_attention": needs_attention,
        "on_track": on_track,
        "alerts": alerts,
        "team_summary": team_summary,
        "last_computed": last_computed,
    }


async def run_health_scoring_for_all(db_repo) -> dict:
    employees = db_repo.list_all_employees()
    at_risk = 0
    for emp in employees:
        score = compute_employee_health(emp["employee_id"], db_repo)
        db_repo.upsert_health_score(score)
        if score["rag_status"] == "at_risk":
            at_risk += 1
    return {"scored": len(employees), "at_risk": at_risk}
