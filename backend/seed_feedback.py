"""Seed continuous feedback entries for demo."""

SEED_FEEDBACK_ENTRIES = [
    {
        "id": "fb_seed_001",
        "employee_id": "NX01007",
        "author_employee_id": "NX01001",
        "author_name": "Shreya Patel",
        "raw_text": (
            "Siddhant led the Q1 platform migration briefing with exceptional clarity. "
            "He pre-circulated a structured risk register 48 hours before the meeting and "
            "managed three conflicting stakeholder priorities without escalation."
        ),
        "context": "Q1 platform migration — board briefing session",
        "feedback_type": "strength",
        "sentiment": "positive",
        "visibility": "manager_only",
        "tags": ["stakeholder management", "leadership", "Q1 delivery"],
        "review_cycle": "FY2025-H1",
        "is_draft": 0,
    },
    {
        "id": "fb_seed_002",
        "employee_id": "NX01007",
        "author_employee_id": "NX01001",
        "author_name": "Shreya Patel",
        "raw_text": (
            "In the March product roadmap presentation to the exec team, Siddhant lost the "
            "thread when challenged on the timeline for the onboarding feature. He recovered, "
            "but the room lost confidence briefly."
        ),
        "context": "Executive product roadmap review — March",
        "feedback_type": "development",
        "sentiment": "constructive",
        "visibility": "manager_only",
        "tags": ["executive presence", "communication", "preparation"],
        "review_cycle": "FY2025-H1",
        "is_draft": 0,
    },
    {
        "id": "fb_seed_003",
        "employee_id": "NX01007",
        "author_employee_id": "NX01001",
        "author_name": "Shreya Patel",
        "raw_text": (
            "The onboarding redesign shipped on time and hit 83% task-completion rate at "
            "launch — above the 78% target. Siddhant drove cross-functional coordination "
            "without escalations."
        ),
        "context": "Onboarding redesign — launch retrospective",
        "feedback_type": "project",
        "sentiment": "positive",
        "visibility": "shared",
        "tags": ["delivery", "cross-functional", "onboarding"],
        "review_cycle": "FY2025-H1",
        "is_draft": 0,
    },
    {
        "id": "fb_seed_004",
        "employee_id": "NX01007",
        "author_employee_id": "NX01001",
        "author_name": "Shreya Patel",
        "raw_text": (
            "Siddhant tends to hold decisions longer than necessary — direct reports "
            "mentioned it in skip-level conversations. He should delegate scope decisions "
            "on sprint planning to team leads given his seniority."
        ),
        "context": "Skip-level check-ins with direct reports",
        "feedback_type": "behaviour",
        "sentiment": "constructive",
        "visibility": "manager_only",
        "tags": ["delegation", "empowerment", "seniority"],
        "review_cycle": "FY2025-H2",
        "is_draft": 0,
    },
    {
        "id": "fb_seed_005",
        "employee_id": "NX01007",
        "author_employee_id": "NX01001",
        "author_name": "Shreya Patel",
        "raw_text": (
            "Siddhant proactively flagged a dependency risk on the Q3 roadmap initiative "
            "6 weeks before it would have caused a delay. This kind of forward-looking "
            "ownership is exactly what we need at the Senior PM level."
        ),
        "context": "Q3 planning cycle — risk review",
        "feedback_type": "strength",
        "sentiment": "positive",
        "visibility": "shared",
        "tags": ["risk management", "initiative", "ownership"],
        "review_cycle": "FY2025-H2",
        "is_draft": 0,
    },
]


def seed_feedback_entries(db_repo, vector_store) -> int:
    """Insert demo feedback if table empty for demo employee."""
    if db_repo.count_feedback_for_employee("NX01007") > 0:
        return 0
    count = 0
    for entry in SEED_FEEDBACK_ENTRIES:
        db_repo.insert_feedback({**entry, "cycle": "FY2025"})
        if not entry.get("is_draft"):
            row = db_repo.get_feedback_by_id(entry["id"])
            if row:
                vector_store.sync_feedback_entry(row)
        count += 1
    return count
