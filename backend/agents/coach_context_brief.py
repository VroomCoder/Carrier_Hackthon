"""Build a full employee context brief for the Growth Coach."""

from __future__ import annotations

from auth import CurrentUser
from cycle_config import DEFAULT_CYCLE, REQUIRED_GOAL_COUNT
from feedback_cycle import current_review_cycle

from agents.feedback_reviews import compute_cycle_status
from agents.health_scoring_agent import compute_employee_health


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _include_private_feedback(user: CurrentUser, employee_id: str) -> bool:
    """Employees see shared feedback only; HR may see all for demo coaching."""
    if user.role == "admin":
        return True
    return False


def _can_view_private_achievements(user: CurrentUser, employee_id: str) -> bool:
    return user.role == "admin" or user.employee_id == employee_id


def _section_profile(emp: dict, node: dict | None) -> str:
    tier = node["seniority_tier"] if node else "unknown"
    focus = node.get("focus_description", "") if node else ""
    lines = [
        f"Name: {emp['name']}",
        f"Role: {emp.get('job_title', '')} · {emp.get('department', '')} / {emp.get('sub_department', '')}",
        f"Grade: {emp.get('grade', '—')} · Seniority: {tier}",
        f"Work mode: {emp.get('work_mode', '—')} · Location: {emp.get('location', '—')}",
        f"Manager: {emp.get('manager_name', '—')}",
    ]
    if focus:
        lines.append(f"Role focus: {_truncate(focus, 200)}")
    return "\n".join(lines)


def _section_goals(milestones: list[dict]) -> str:
    if not milestones:
        return "No goals on file yet."
    calibrated = sum(1 for m in milestones if m.get("status") == "calibrated")
    needs = sum(1 for m in milestones if m.get("status") == "needs_work")
    suggested = sum(1 for m in milestones if m.get("status") == "suggested")
    lines = [
        f"Total: {len(milestones)} · Calibrated: {calibrated} · "
        f"Needs work: {needs} · Suggested: {suggested} "
        f"(target {REQUIRED_GOAL_COUNT} calibrated)",
    ]
    for m in milestones:
        goal_text = _truncate(m.get("smart_goal") or m.get("raw_goal", ""), 120)
        score = m.get("overall_score", 0)
        status = m.get("status", "unknown")
        okr = m.get("linked_okr_id") or m.get("source_okr_id") or "unlinked"
        lines.append(f"  · [{status}] SMART {score}/100 · OKR {okr}: {goal_text}")
    return "\n".join(lines)


def _section_okrs(assignments: list[dict], milestones: list[dict]) -> str:
    if not assignments:
        return "No company OKRs assigned this cycle."
    linked = {
        m.get("linked_okr_id") or m.get("source_okr_id")
        for m in milestones
        if m.get("linked_okr_id") or m.get("source_okr_id")
    }
    lines = []
    for a in assignments:
        okr_id = a.get("okr_id", "")
        supported = "supported by a goal" if okr_id in linked else "no goal linked yet"
        lines.append(
            f"  · [{a.get('category', '')}] {a.get('title', '')} — {supported}"
        )
    unlinked_goals = [
        m for m in milestones
        if not (m.get("linked_okr_id") or m.get("source_okr_id"))
    ]
    if unlinked_goals:
        lines.append(f"  · {len(unlinked_goals)} goal(s) not yet aligned to an assigned OKR")
    return "\n".join(lines)


def _section_feedback(
    entries: list[dict],
    summary: dict | None,
    cycle: str,
) -> str:
    lines = [f"Review cycle: {cycle}"]
    if not entries:
        lines.append("No shared manager feedback entries visible to you this cycle.")
    else:
        by_sentiment: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for e in entries:
            s = e.get("sentiment", "neutral")
            by_sentiment[s] = by_sentiment.get(s, 0) + 1
            t = e.get("feedback_type", "general")
            by_type[t] = by_type.get(t, 0) + 1
        lines.append(
            f"Entries this cycle: {sum(1 for e in entries if e.get('review_cycle') == cycle)} "
            f"· Total shared: {len(entries)}"
        )
        if by_sentiment:
            lines.append(
                "Sentiment: "
                + ", ".join(f"{k}={v}" for k, v in sorted(by_sentiment.items()))
            )
        recurring = [t for t, c in by_type.items() if c >= 2]
        if recurring:
            lines.append(f"Recurring themes (type): {', '.join(recurring)}")
        lines.append("Recent entries:")
        for e in entries[:5]:
            text = _truncate(e.get("raw_text") or e.get("content", ""), 100)
            lines.append(
                f"  · [{e.get('created_at', '')[:10]} | {e.get('feedback_type')} | "
                f"{e.get('sentiment')}] {text}"
            )
    if summary:
        lines.append(f"Feedback summary ({summary.get('review_type', 'mid_year')}):")
        lines.append(f"  Trajectory: {summary.get('trajectory', 'unknown')}")
        lines.append(f"  {_truncate(summary.get('content', ''), 400)}")
        dev = summary.get("development_areas") or []
        if dev:
            lines.append(f"  Development areas: {', '.join(dev[:3])}")
    else:
        lines.append("No AI feedback summary generated yet for this cycle.")
    return "\n".join(lines)


def _section_achievements(achievements: list[dict]) -> str:
    if not achievements:
        return "No accomplishments or certifications recorded this cycle."
    lines = [f"Total: {len(achievements)} item(s) on file:"]
    type_labels = {
        "certification": "Cert",
        "accomplishment": "Accomplishment",
        "training": "Training",
        "award": "Award",
        "project": "Project",
        "other": "Other",
    }
    for a in achievements[:8]:
        label = type_labels.get(a.get("type", ""), a.get("type", ""))
        title = a.get("title", "")
        ctx = a.get("issuer_or_context", "")
        when = (a.get("achieved_at") or "")[:10]
        desc = _truncate(a.get("description", ""), 80)
        line = f"  · [{label}] {title}"
        if when:
            line += f" ({when})"
        if ctx:
            line += f" — {ctx}"
        if desc:
            line += f": {desc}"
        lines.append(line)
    return "\n".join(lines)


def _section_health(health: dict) -> str:
    lines = [
        f"Composite: {round(health.get('composite_score', 0))}/100 · "
        f"Status: {health.get('rag_status', 'unknown')}",
        f"  Goals {round(health.get('goal_quality_score', 0))} · "
        f"Check-ins {round(health.get('checkin_score', 0))} · "
        f"Feedback {round(health.get('feedback_score', 0))} · "
        f"Review readiness {round(health.get('review_readiness', 0))} · "
        f"Trajectory {round(health.get('trajectory_score', 0))}",
    ]
    reasons = health.get("at_risk_reasons") or []
    if reasons:
        lines.append(f"  Focus areas: {', '.join(reasons)}")
    return "\n".join(lines)


def _section_cycle(cycle_status: dict) -> str:
    return (
        f"Cycle stage: {cycle_status.get('current_stage', 'Unknown')} "
        f"({cycle_status.get('calibrated_count', 0)}/{cycle_status.get('goals_required', 4)} "
        f"goals calibrated · review completeness {cycle_status.get('review_completeness', 0)}%)"
    )


def _section_session_history(recent: list[dict]) -> str:
    if not recent:
        return "No prior coach sessions recorded."
    lines = ["Prior discussion snippets:"]
    for msg in recent[-6:]:
        role = msg.get("role", "user")
        content = _truncate(msg.get("content", ""), 120)
        if content:
            lines.append(f"  · [{role}] {content}")
    return "\n".join(lines)


def _section_peer_context(db_repo, emp: dict, node: dict | None, health: dict) -> str:
    if not node:
        return "Peer context: unavailable (no org role mapping)."
    tier = node["seniority_tier"]
    dept = emp.get("department", "")
    peers: list[str] = []
    for e in db_repo.list_all_employees():
        if e["employee_id"] == emp["employee_id"]:
            continue
        if e.get("department") != dept:
            continue
        peer_node = db_repo.get_org_node(
            e["department"], e["sub_department"], e["job_title"]
        )
        if peer_node and peer_node.get("seniority_tier") == tier:
            peers.append(e["employee_id"])
    if len(peers) < 3:
        return "Peer context: group too small for anonymised comparison."
    scores: list[float] = []
    cal_rates: list[float] = []
    for pid in peers[:25]:
        hs = db_repo.get_health_score(pid)
        if hs:
            scores.append(float(hs.get("composite_score", 0)))
        ms = db_repo.get_milestones_by_employee(pid)
        if ms:
            cal = sum(1 for m in ms if m.get("status") == "calibrated")
            cal_rates.append(cal / len(ms))
    if not scores:
        return "Peer context: no peer health scores computed yet."
    avg_score = sum(scores) / len(scores)
    my_score = float(health.get("composite_score", 0))
    delta = my_score - avg_score
    comparison = "above" if delta > 5 else "below" if delta < -5 else "near"
    lines = [
        f"Anonymised peers ({len(peers)} at {tier} in {dept}): "
        f"avg health {avg_score:.0f}/100 (you: {my_score:.0f}, {comparison} average)",
    ]
    if cal_rates:
        lines.append(f"Avg peer goal calibration rate: {100 * sum(cal_rates) / len(cal_rates):.0f}%")
    return lines[0] + (f"\n{lines[1]}" if len(lines) > 1 else "")


def _format_policy_hits(policy_hits: list[dict], max_chars: int = 900) -> str:
    if not policy_hits:
        return "No policy excerpts matched this question."
    parts: list[str] = []
    used = 0
    for hit in policy_hits:
        title = hit.get("doc_title") or hit.get("section_title") or "Policy"
        text = _truncate(hit.get("text", ""), 280)
        line = f"  · [{title}] {text}"
        if used + len(line) > max_chars:
            break
        parts.append(line)
        used += len(line)
    return "\n".join(parts) if parts else "No policy excerpts matched this question."


def build_personalised_greeting(emp: dict, brief_text: str, health: dict, cycle_status: dict) -> str:
    """Deterministic opening line from brief highlights — no extra LLM call."""
    name = emp.get("name", "there").split()[0]
    calibrated = cycle_status.get("calibrated_count", 0)
    required = cycle_status.get("goals_required", REQUIRED_GOAL_COUNT)
    score = round(health.get("composite_score", 0))
    rag = health.get("rag_status", "needs_attention")
    reasons = health.get("at_risk_reasons") or []
    trajectory = health.get("trajectory", "insufficient_data")

    parts = [f"Hi {name} — I'm your Growth Coach."]
    parts.append(
        f"You have {calibrated} of {required} goals calibrated and your cycle health is {score}/100 ({rag.replace('_', ' ')})."
    )
    if trajectory == "improving":
        parts.append("Your feedback trajectory is improving — good momentum.")
    elif trajectory == "declining":
        parts.append("Your recent feedback suggests an area to focus on — I can help you plan next steps.")
    elif reasons:
        parts.append(f"Worth noting: {reasons[0].lower()}.")
    parts.append("I already have your goals, OKRs, feedback, and cycle context — what would you like to work on?")
    return " ".join(parts)


def build_coach_context_brief(
    employee_id: str,
    user: CurrentUser,
    db_repo,
    vector_store,
    last_message: str = "",
) -> dict:
    """
    Assemble full working memory for one coach turn.
    Returns {brief_text, greeting, employee_id, sections}.
    """
    emp = db_repo.get_employee_by_id(employee_id)
    if not emp:
        return {
            "employee_id": employee_id,
            "brief_text": "No employee profile found.",
            "greeting": "Hi — I'm your Growth Coach. How can I help you today?",
            "sections": {},
        }

    cycle = current_review_cycle()
    node = db_repo.get_org_node(
        emp["department"], emp["sub_department"], emp["job_title"]
    )
    milestones = db_repo.get_milestones_by_employee(employee_id)
    assignments = db_repo.get_okr_assignments_for_employee(employee_id, DEFAULT_CYCLE)
    include_private = _include_private_feedback(user, employee_id)
    all_entries = db_repo.get_entries_for_employee(employee_id, include_drafts=False)
    if not include_private:
        all_entries = [e for e in all_entries if e.get("visibility") == "shared"]
    cycle_entries = [e for e in all_entries if e.get("review_cycle") == cycle]

    summary = (
        db_repo.get_feedback_summary(employee_id, cycle, "mid_year")
        or db_repo.get_feedback_summary(employee_id, cycle, "year_end")
    )
    health_row = db_repo.get_health_score(employee_id)
    health = health_row if health_row else compute_employee_health(employee_id, db_repo)
    cycle_status = compute_cycle_status(db_repo, employee_id, DEFAULT_CYCLE)
    recent_msgs = db_repo.get_recent_messages(employee_id, limit=8)

    achievements = db_repo.list_achievements(
        employee_id,
        review_cycle=cycle,
        include_private=_can_view_private_achievements(user, employee_id),
    )

    query = last_message.strip() or "performance goals feedback development review"
    policy_hits = vector_store.search_policy(query, n_results=3)

    sections = {
        "profile": _section_profile(emp, node),
        "cycle": _section_cycle(cycle_status),
        "goals": _section_goals(milestones),
        "okrs": _section_okrs(assignments, milestones),
        "feedback": _section_feedback(cycle_entries or all_entries[:8], summary, cycle),
        "achievements": _section_achievements(achievements),
        "health": _section_health(health),
        "session_history": _section_session_history(recent_msgs),
        "peer_context": _section_peer_context(db_repo, emp, node, health),
        "policy": _format_policy_hits(policy_hits),
    }

    brief_text = f"""=== EMPLOYEE CONTEXT BRIEF (ground truth — do not invent facts) ===

[PROFILE]
{sections['profile']}

[CYCLE STATUS]
{sections['cycle']}

[GOALS & MILESTONES]
{sections['goals']}

[OKR ALIGNMENT]
{sections['okrs']}

[MANAGER FEEDBACK — shared entries & summary]
{sections['feedback']}

[ACCOMPLISHMENTS & CERTIFICATIONS]
{sections['achievements']}

[HEALTH SCORE]
{sections['health']}

[PRIOR COACH SESSIONS]
{sections['session_history']}

[PEER CONTEXT — anonymised]
{sections['peer_context']}

[POLICY EXCERPTS — relevant to current question]
{sections['policy']}

=== END BRIEF ==="""

    greeting = build_personalised_greeting(emp, brief_text, health, cycle_status)

    return {
        "employee_id": employee_id,
        "brief_text": brief_text,
        "greeting": greeting,
        "sections": sections,
    }
