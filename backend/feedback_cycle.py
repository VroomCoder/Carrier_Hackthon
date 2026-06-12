"""Review cycle helpers for continuous feedback."""

from __future__ import annotations

from datetime import datetime, timezone


def compute_review_cycle(date_str: str | None = None) -> str:
    """
    Jan–Jun → FY{year}-H1, Jul–Dec → FY{year}-H2.
    """
    if date_str:
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            elif " " in date_str:
                dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            else:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    half = "H1" if dt.month <= 6 else "H2"
    return f"FY{dt.year}-{half}"


def current_review_cycle() -> str:
    return compute_review_cycle(None)
