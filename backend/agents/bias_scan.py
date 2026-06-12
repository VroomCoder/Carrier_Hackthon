"""Bias taxonomy, lightweight scan, and synthesis gate helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from llm_client import llm_complete

BIAS_TAXONOMY = """
Scan the input for ALL of the following bias types:

1. Halo effect
   One strong positive trait causes the rater to view all
   other traits positively. Signal: consistently glowing
   language across unrelated competencies.

2. Horns effect
   One negative trait disproportionately colours the overall
   assessment. Signal: a single failure referenced repeatedly.

3. Recency bias
   Over-weighting events from the last 4-6 weeks vs the full
   review period. Signal: specific recent events dominate;
   earlier contributions absent.

4. Affinity bias
   Favouring someone due to perceived similarity to the rater
   (background, communication style, interests).
   Signal: "just like me" language, comfort-based praise.

5. Gendered language
   Language that would be applied differently based on gender.
   Signal: words like "aggressive," "emotional," "bossy,"
   "nurturing," "ambitious" used in gendered contexts.

6. Attribution bias
   Attributing success to external factors (luck, team, timing)
   while attributing failures to the individual's character.
   Signal: "the team delivered" for wins, "she failed to" for losses.
   Also the reverse: attributing individual success to personal
   brilliance while ignoring structural support.

7. Performance-potential confusion
   Rating someone on what they could become rather than what
   they actually delivered in the review period.
   Signal: "has great potential," "could be a future leader"
   substituting for evidence of current performance.

8. In-group favouritism
   Rating members of the rater's own team, function, or social
   group more favourably than equivalent contributors elsewhere.
   Signal: language that assumes shared context or rapport
   not available to outsiders.
"""

SEVERITY_BY_TYPE: dict[str, str] = {
    "Halo effect": "high",
    "Horns effect": "high",
    "Gendered language": "high",
    "Attribution bias": "high",
    "Recency bias": "medium",
    "In-group favouritism": "medium",
    "Affinity bias": "low",
    "Performance-potential confusion": "low",
}

CHECK_BIAS_SYSTEM = """You are a bias detection assistant for HR feedback writing.
Scan the text for bias. Return ONLY valid JSON:
{ "flags": [{ "type": str, "passage": str,
              "suggestion": str, "severity": "high|medium|low" }],
  "score": 0-100 }
Be concise. Flag only clear, confident detections."""


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return json.loads(cleaned)


def _normalize_flag(flag: dict[str, Any]) -> dict[str, Any]:
    ftype = str(flag.get("type") or "Unknown bias").strip()
    severity = str(flag.get("severity") or "").lower()
    if severity not in ("high", "medium", "low"):
        severity = SEVERITY_BY_TYPE.get(ftype, "medium")
    return {
        "type": ftype,
        "passage": str(flag.get("passage") or "").strip(),
        "suggestion": str(flag.get("suggestion") or "").strip(),
        "severity": severity,
    }


def normalize_flags(flags: list | None) -> list[dict[str, Any]]:
    if not flags:
        return []
    return [_normalize_flag(f) for f in flags if isinstance(f, dict)]


def compute_gate(result: dict[str, Any]) -> tuple[bool, str | None]:
    score = int(result.get("score") or 100)
    flags = normalize_flags(result.get("flags"))
    high = [f for f in flags if f.get("severity") == "high" and f.get("passage")]
    if score < 70 and high:
        type_names = ", ".join(sorted({f.get("type", "bias") for f in high}))
        reason = (
            f"{type_names} detected in {len(high)} passage(s). "
            "Please review the suggested rewrites before finalising."
        )
        return True, reason
    return False, None


def build_synthesis_system_prompt(
    employee_profile_block: str = "",
    milestone_context_block: str = "",
) -> str:
    return f"""HR Business Partner at NexaCore.
{employee_profile_block}
{milestone_context_block}

Turn raw feedback into formal commentary (3-4 sentences).
{BIAS_TAXONOMY}

Severity rules:
  high   → halo, horns, gendered language, attribution bias
  medium → recency, in-group favouritism
  low    → affinity, performance-potential confusion

Return ONLY JSON:
{{"commentary":"...","score":0-100,"flags":[{{"type":"Bias type name","passage":"exact quoted text","suggestion":"neutral rewrite","severity":"high|medium|low"}}],"policy_references":[]}}"""


def enrich_synthesis_result(result: dict[str, Any]) -> dict[str, Any]:
    result["flags"] = normalize_flags(result.get("flags"))
    result["policy_references"] = result.get("policy_references") or []
    gate_blocked, gate_reason = compute_gate(result)
    result["gate_blocked"] = gate_blocked
    result["gate_reason"] = gate_reason
    return result


async def run_bias_check(text: str) -> dict[str, Any]:
    """Lightweight text-only bias scan for real-time nudges."""
    prompt = text.strip()[:2000]
    if not prompt:
        return {"flags": [], "score": 100}
    raw = await llm_complete(prompt=prompt, system=CHECK_BIAS_SYSTEM)
    data = _parse_json(raw)
    flags = normalize_flags(data.get("flags"))
    score = int(data.get("score") or 100)
    return {"flags": flags, "score": max(0, min(100, score))}


def high_severity_passages(flags: list[dict[str, Any]]) -> list[str]:
    return [
        f["passage"]
        for f in normalize_flags(flags)
        if f.get("severity") == "high" and f.get("passage")
    ]
