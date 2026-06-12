"""Shared SMART calibration logic for employee goal acceptance."""

import json
import re

from agent_trace import get_trace
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from ollama_client import ollama_complete


async def run_calibration(
    goal: str,
    employee_id: str,
    db_repo: SqliteRepo,
    vector_store: VectorStore,
    linked_okr_id: str | None = None,
) -> dict:
    seniority_tier = "mid"
    okr_categories: list[str] = []
    role_context = "No employee context provided."

    emp = db_repo.get_employee_by_id(employee_id)
    if emp:
        node = db_repo.get_org_node(
            emp["department"], emp["sub_department"], emp["job_title"]
        )
        if node:
            seniority_tier = node["seniority_tier"]
            focus_description = node["focus_description"]
            okr_categories = node["okr_categories"].split(",")
            role_context = (
                f"{emp['name']}, {emp['job_title']} in {emp['department']} / "
                f"{emp['sub_department']}. Seniority: {seniority_tier}. "
                f"At this level, goals should: {focus_description}"
            )
        trace = get_trace()
        if trace:
            trace.load("employee_profile", f"{emp['name']} — {emp['job_title']}")

    assigned_okr_block = ""
    if linked_okr_id:
        okr = db_repo.get_okr_by_id(linked_okr_id)
        if okr:
            assigned_okr_block = (
                f"\nLinked assigned OKR: [{okr['category']}] "
                f"{okr['title']}: {okr['description']}"
            )

    assignments = db_repo.get_okr_assignments_for_employee(employee_id)
    trace = get_trace()
    if assignments:
        assign_lines = []
        for a in assignments:
            assign_lines.append(
                f"- [{a['category']}] {a['title']}: {a['description'][:180]}"
            )
        okr_context = "Manager-assigned OKRs for this employee:\n" + "\n".join(assign_lines)
        if trace:
            trace.load(
                "assigned_okrs",
                f"{len(assignments)} manager-assigned OKR(s)",
                len(assignments),
            )
    else:
        if trace:
            trace.handoff("okr_search", "No assigned OKRs — semantic search")
        matching_okrs = vector_store.search_okrs(
            goal, n_results=2, status_filter="active", category_boost=okr_categories
        )
        if matching_okrs:
            okr_lines = []
            for okr in matching_okrs:
                okr_full = db_repo.get_okr_by_id(okr.get("okr_id", ""))
                if okr_full:
                    desc = okr_full["description"]
                    if len(desc) > 180:
                        desc = desc[:177] + "..."
                    okr_lines.append(
                        f"- [{okr_full['category']}] {okr_full['title']}: {desc}"
                    )
            okr_context = "\n".join(okr_lines) if okr_lines else "No OKRs configured."
        else:
            okr_context = "No OKRs configured."

    system_prompt = f"""NexaCore performance coach. Evaluate goal vs SMART + assigned OKRs.

Employee: {role_context}
OKRs:
{okr_context}{assigned_okr_block}

Return ONLY JSON:
{{"scores":{{"S":0-100,"M":0-100,"A":0-100,"R":0-100,"T":0-100}},"rewritten_goal":"...","gaps":["..."],"okr_alignment":"...","policy_references":[],"seniority_tier":"{seniority_tier}","role_benchmark":"...","overall":0-100}}"""

    if trace:
        trace.handoff("llm", "SMART scoring")

    raw = await ollama_complete(prompt=goal, system=system_prompt)

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    result = json.loads(cleaned)
    result["policy_references"] = []
    return result
