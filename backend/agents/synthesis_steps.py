"""LLM steps for feedback synthesis (shared by synthesis_core + LangGraph)."""

from __future__ import annotations

import json
import re
from typing import Any

from agent_trace import get_trace
from agents.bias_scan import build_synthesis_system_prompt, enrich_synthesis_result
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from feedback_cycle import current_review_cycle
from llm_client import ollama_complete

MAX_FEEDBACK_CHARS = 2500
MAX_FEEDBACK_ENTRIES = 8
MAX_ENTRY_CHARS = 400


def parse_llm_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return json.loads(cleaned)


def clip_text(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def load_synthesis_context(
    feedback: str,
    employee_id: str | None,
    db_repo: SqliteRepo,
    vector_store: VectorStore,
) -> dict[str, Any]:
    clipped = clip_text(feedback, MAX_FEEDBACK_CHARS)
    employee_profile_block = ""
    if employee_id:
        emp = db_repo.get_employee_by_id(employee_id)
        if emp:
            employee_profile_block = (
                f"Employee: {emp['name']}, {emp['job_title']}, {emp['department']}."
            )
            trace = get_trace()
            if trace:
                trace.load("employee_profile", f"{emp['name']} — {emp['job_title']}")

    trace = get_trace()
    if trace:
        trace.handoff("milestone_rag", "Find goal context for feedback (LangGraph)")

    milestone_context_block = ""
    milestones = vector_store.search_milestones(clipped, employee_id, n_results=1)
    if milestones:
        ms = db_repo.get_milestone_by_id(milestones[0].get("id", ""))
        if ms:
            goal = ms.get("smart_goal") or ms.get("raw_goal", "")
            milestone_context_block = f"Goal context: {clip_text(goal, 200)}"
            if trace:
                trace.load("milestone_embeddings", "1 goal match from semantic search", 1)

    return {
        "feedback": clipped,
        "employee_profile_block": employee_profile_block,
        "milestone_context_block": milestone_context_block,
    }


async def synthesise_commentary(
    feedback: str,
    employee_profile_block: str,
    milestone_context_block: str,
) -> dict[str, Any]:
    system_prompt = build_synthesis_system_prompt(
        employee_profile_block, milestone_context_block
    )
    trace = get_trace()
    if trace:
        trace.handoff("llm", "Synthesise formal commentary (LangGraph)")
    raw = await ollama_complete(prompt=feedback, system=system_prompt)
    return parse_llm_json(raw)


def apply_synthesis_gate(raw_result: dict[str, Any]) -> dict[str, Any]:
    trace = get_trace()
    if trace:
        trace.handoff("bias_gate", "Apply objectivity gate (LangGraph)")
    result = enrich_synthesis_result(raw_result)
    if trace and result.get("gate_blocked"):
        trace.decision(
            "Bias gate active",
            result.get("gate_reason") or "High-severity flags require acknowledgement",
            sources=["bias_taxonomy"],
        )
    return result


def format_feedback_entries(entries: list[dict]) -> str:
    if not entries:
        return "No continuous feedback entries."
    parts = []
    for entry in entries[:MAX_FEEDBACK_ENTRIES]:
        block = (
            f"{entry.get('author_name', 'Manager')}: "
            f"{clip_text(entry['raw_text'], MAX_ENTRY_CHARS)}"
        )
        parts.append(block)
    return "\n\n".join(parts)


async def load_review_draft_context(
    employee_id: str,
    review_type: str,
    feedback_entries: list[dict],
    db_repo: SqliteRepo,
    *,
    employee_self_assessment: str = "",
    feedback_summary: str | None = None,
) -> dict[str, Any]:
    emp = db_repo.get_employee_by_id(employee_id)
    if not emp:
        raise ValueError("Employee not found")

    trace = get_trace()
    if trace:
        trace.load("employee_profile", f"{emp['name']} — {emp['job_title']}")

    milestones = db_repo.get_milestones_by_employee(employee_id)[:5]
    achievements = db_repo.list_achievements(
        employee_id,
        review_cycle=current_review_cycle(),
        include_private=False,
    )
    if trace:
        trace.load(
            "employee_goals",
            f"{len(milestones)} goal(s) for review context",
            len(milestones),
        )
        trace.load(
            "achievements",
            f"{len(achievements)} accomplishment(s) for review context",
            len(achievements),
        )
        trace.load(
            "feedback_entries",
            f"{min(len(feedback_entries), MAX_FEEDBACK_ENTRIES)} feedback entries",
            min(len(feedback_entries), MAX_FEEDBACK_ENTRIES),
        )

    milestone_lines = []
    for ms in milestones:
        goal = clip_text(ms.get("smart_goal") or ms.get("raw_goal", ""), 160)
        line = f"- {goal} ({ms.get('status', 'needs_work')})"
        assessment = ms.get("employee_self_assessment", "").strip()
        if assessment:
            line += f" | self: {clip_text(assessment, 120)}"
        milestone_lines.append(line)
    milestone_block = "\n".join(milestone_lines) if milestone_lines else "No milestones."

    achievement_lines = []
    for a in achievements[:6]:
        line = f"- [{a.get('type', 'other')}] {a.get('title', '')}"
        if a.get("description"):
            line += f": {clip_text(a['description'], 100)}"
        achievement_lines.append(line)
    achievements_block = (
        "\n".join(achievement_lines) if achievement_lines else "No accomplishments on file."
    )

    feedback_block = format_feedback_entries(feedback_entries)
    if feedback_summary and feedback_summary.strip():
        feedback_block = (
            f"[Year-round feedback summary]\n{feedback_summary.strip()}\n\n"
            f"[Individual entries]\n{feedback_block}"
        )

    review_label = "mid-year" if review_type == "mid_year" else "year-end"
    self_block = ""
    if employee_self_assessment.strip():
        self_block = f"\nSelf-assessment: {clip_text(employee_self_assessment, 800)}\n"

    system_prompt = f"""Draft {review_label} manager review for {emp['name']} ({emp['job_title']}).
Goals:
{milestone_block}
Employee accomplishments (manager-visible):
{achievements_block}
{self_block}
Return ONLY JSON:
{{"manager_summary":"4-6 sentences","development_areas":"bullet\\nbullet"}}"""

    return {
        "feedback_block": feedback_block,
        "system_prompt": system_prompt,
        "review_type": review_type,
        "feedback_entries_used": min(len(feedback_entries), MAX_FEEDBACK_ENTRIES),
    }


async def draft_manager_review(feedback_block: str, system_prompt: str, review_type: str) -> dict:
    review_label_short = "mid-year" if review_type == "mid_year" else "year-end"
    trace = get_trace()
    if trace:
        trace.handoff("llm", f"Draft {review_label_short} review (LangGraph)")
    raw = await ollama_complete(prompt=feedback_block, system=system_prompt)
    result = parse_llm_json(raw)
    return {
        "manager_summary": result.get("manager_summary", "").strip(),
        "development_areas": result.get("development_areas", "").strip(),
    }
