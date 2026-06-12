"""LLM steps for feedback summary (shared by agent + LangGraph nodes)."""

from __future__ import annotations

import json
import re

from llm_client import llm_complete


def parse_summary_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return json.loads(cleaned)


def _entry_lines(entries: list[dict]) -> str:
    lines = []
    for i, e in enumerate(entries):
        lines.append(
            f"[{i}] ({e.get('created_at', '')[:10]} | {e.get('feedback_type')} | "
            f"{e.get('sentiment')}) {e.get('raw_text') or e.get('content', '')}"
        )
    return "\n".join(lines)


async def cluster_themes(entries: list[dict]) -> list[dict]:
    numbered = _entry_lines(entries)
    system = """You are an expert HR analyst reviewing continuous feedback entries.
Identify 3-5 recurring themes. Return ONLY valid JSON:
{"themes":[{"name":"...","description":"...","entry_indices":[0,1],"dominant_sentiment":"positive|constructive|mixed"}]}"""
    try:
        raw = await llm_complete(prompt=numbered, system=system)
        data = parse_summary_json(raw)
        themes = data.get("themes", [])
        if themes:
            return themes
    except (json.JSONDecodeError, Exception):
        pass
    return [
        {
            "name": "General feedback",
            "description": "Overall patterns from continuous feedback entries.",
            "entry_indices": list(range(len(entries))),
            "dominant_sentiment": "mixed",
        }
    ]


async def draft_summary(
    emp: dict,
    entries: list[dict],
    themes: list[dict],
    review_type: str,
    review_cycle: str,
    correction_issues: list[str] | None = None,
) -> dict:
    review_label = "mid-year" if review_type == "mid_year" else "year-end"
    length_hint = "4-6 sentences" if review_type == "mid_year" else "6-8 sentences"
    issues_block = ""
    if correction_issues:
        issues_block = (
            f"\nFix these issues from the previous draft: {json.dumps(correction_issues)}"
        )
    system = f"""Senior HR Business Partner preparing a {review_label} review summary.
Write {length_hint}. Ground every claim in entries. Return ONLY JSON:
{{"summary":"...","strengths":["..."],"development_areas":["..."],"trajectory":"improving|steady|declining|insufficient_data","notable_pattern":"... or null","confidence":"high|medium|low","confidence_reason":"..."}}{issues_block}"""
    user = (
        f"Employee: {emp['name']}, {emp['job_title']}, {emp['department']}\n"
        f"Cycle: {review_cycle}, {len(entries)} entries, {len(themes)} themes\n"
        f"Themes: {json.dumps(themes)}\n\nEntries:\n{_entry_lines(entries)}"
    )
    raw = await llm_complete(prompt=user, system=system)
    return parse_summary_json(raw)


async def evaluate_summary(draft: dict, entry_count: int) -> dict:
    system = """Quality evaluator for HR appraisal documentation. Return ONLY JSON:
{"scores":{"evidence_grounding":0-10,"balance":0-10,"professionalism":0-10,"actionability":0-10,"completeness":0-10},"overall":0-10,"issues":[],"approved":true|false}
Approve if overall >= 7."""
    user = f"Summary to evaluate ({entry_count} source entries):\n{json.dumps(draft)}"
    raw = await llm_complete(prompt=user, system=system)
    return parse_summary_json(raw)
