"""Shared confidence scoring helpers for agent transparency."""

from __future__ import annotations


def level_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def objectivity_to_confidence(objectivity_score: int | None) -> tuple[str, float, str]:
    if objectivity_score is None:
        return "medium", 0.55, "No objectivity score returned from synthesis"
    score = max(0.0, min(1.0, objectivity_score / 100.0))
    return (
        level_from_score(score),
        round(score, 2),
        f"Objectivity score {objectivity_score}/100 from grounded feedback synthesis",
    )


def smart_score_to_confidence(overall: int, status: str) -> tuple[str, float, str]:
    score = max(0.0, min(1.0, overall / 100.0))
    reason = f"SMART overall {overall}/100 → status {status.replace('_', ' ')}"
    return level_from_score(score), round(score, 2), reason


def brief_completeness_confidence(sections: dict) -> tuple[str, float, str]:
    """Coach context brief — confidence from how many sections have real data."""
    if not sections:
        return "low", 0.3, "Empty context brief"
    empty_markers = (
        "No goals",
        "No company OKRs",
        "No shared manager",
        "No prior coach",
        "unavailable",
        "too small",
        "No AI feedback summary",
        "No accomplishments",
    )
    filled = 0
    for key, text in sections.items():
        if key == "policy" and "No policy" in text:
            continue
        if any(m in text for m in empty_markers):
            continue
        filled += 1
    ratio = filled / max(len(sections), 1)
    level = level_from_score(ratio)
    return (
        level,
        round(ratio, 2),
        f"Context brief {filled}/{len(sections)} sections populated with employee data",
    )
