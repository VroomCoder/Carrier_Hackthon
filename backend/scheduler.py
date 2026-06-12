"""Proactive feedback summary generation before review windows."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_scheduler = None


async def _auto_summarise_job(db_repo, vector_store) -> None:
    """Generate missing mid-year summaries for employees with feedback."""
    if os.getenv("FEEDBACK_AUTO_SUMMARISE", "true").lower() not in ("1", "true", "yes"):
        return
    from agents.feedback_summary_agent import generate_feedback_summary
    from feedback_cycle import current_review_cycle

    cycle = current_review_cycle()
    try:
        employees = db_repo.search_employees("", limit=500) or []
    except Exception:
        return
    for emp in employees[:50]:
        eid = emp.get("employee_id")
        if not eid or db_repo.count_entries(eid, cycle) == 0:
            continue
        if db_repo.get_feedback_summary(eid, cycle, "mid_year"):
            continue
        try:
            await generate_feedback_summary(
                eid, "mid_year", db_repo, vector_store, review_cycle=cycle
            )
            logger.info("Auto-generated feedback summary for %s", eid)
        except Exception as exc:
            logger.warning("Auto summary failed for %s: %s", eid, exc)


async def _nightly_health_job(db_repo) -> None:
    if os.getenv("ENABLE_HEALTH_SCHEDULER", "true").lower() not in ("1", "true", "yes"):
        return
    from agents.health_scoring_agent import run_health_scoring_for_all

    try:
        result = await run_health_scoring_for_all(db_repo)
        logger.info(
            "Nightly health scoring complete — %s employees scored, %s at risk",
            result.get("scored", 0),
            result.get("at_risk", 0),
        )
    except Exception as exc:
        logger.warning("Nightly health scoring failed: %s", exc)


def start_scheduler(db_repo, vector_store) -> None:
    global _scheduler
    feedback_on = os.getenv("ENABLE_FEEDBACK_SCHEDULER", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    health_on = os.getenv("ENABLE_HEALTH_SCHEDULER", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if not feedback_on and not health_on:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        _scheduler = BackgroundScheduler()

        if feedback_on:

            def run_summarise():
                asyncio.run(_auto_summarise_job(db_repo, vector_store))

            _scheduler.add_job(run_summarise, "interval", hours=24, id="feedback_auto_summarise")

        if health_on:

            def run_health():
                asyncio.run(_nightly_health_job(db_repo))

            _scheduler.add_job(
                run_health,
                "cron",
                hour=6,
                minute=0,
                id="nightly_health_scoring",
                replace_existing=True,
            )

        _scheduler.start()
        logger.info("Background scheduler started (feedback=%s, health=%s)", feedback_on, health_on)
    except ImportError:
        logger.warning("APScheduler not installed — scheduled jobs disabled")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
