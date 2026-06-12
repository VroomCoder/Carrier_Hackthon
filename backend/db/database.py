import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()


def get_db() -> sqlite3.Connection:
    path = os.getenv("SQLITE_PATH", "./data/pmcoach.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Run all CREATE TABLE IF NOT EXISTS statements."""
    conn = get_db()
    conn.executescript("""

    CREATE TABLE IF NOT EXISTS employees (
        employee_id     TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        email           TEXT,
        department      TEXT,
        sub_department  TEXT,
        job_title       TEXT,
        grade           TEXT,
        manager_id      TEXT,
        manager_name    TEXT,
        location        TEXT,
        join_date       TEXT,
        employment_type TEXT,
        leave_balance   INTEGER,
        work_mode       TEXT,
        phone_extension TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department);
    CREATE INDEX IF NOT EXISTS idx_emp_name ON employees(name COLLATE NOCASE);
    CREATE INDEX IF NOT EXISTS idx_emp_manager ON employees(manager_id);

    CREATE VIRTUAL TABLE IF NOT EXISTS employees_fts USING fts5(
        employee_id UNINDEXED,
        name, department, sub_department, job_title, location, work_mode,
        content=employees, content_rowid=rowid
    );

    CREATE TRIGGER IF NOT EXISTS emp_fts_insert AFTER INSERT ON employees BEGIN
        INSERT INTO employees_fts(rowid, employee_id, name, department,
            sub_department, job_title, location, work_mode)
        VALUES (new.rowid, new.employee_id, new.name, new.department,
            new.sub_department, new.job_title, new.location, new.work_mode);
    END;

    CREATE TRIGGER IF NOT EXISTS emp_fts_update AFTER UPDATE ON employees BEGIN
        INSERT INTO employees_fts(employees_fts, rowid, employee_id, name,
            department, sub_department, job_title, location, work_mode)
        VALUES('delete', old.rowid, old.employee_id, old.name, old.department,
            old.sub_department, old.job_title, old.location, old.work_mode);
        INSERT INTO employees_fts(rowid, employee_id, name, department,
            sub_department, job_title, location, work_mode)
        VALUES (new.rowid, new.employee_id, new.name, new.department,
            new.sub_department, new.job_title, new.location, new.work_mode);
    END;

    CREATE TABLE IF NOT EXISTS org_nodes (
        node_id           TEXT PRIMARY KEY,
        department        TEXT NOT NULL,
        business_unit     TEXT NOT NULL,
        designation       TEXT NOT NULL,
        seniority_tier    TEXT NOT NULL,
        focus_description TEXT NOT NULL,
        okr_categories    TEXT NOT NULL,
        status            TEXT NOT NULL DEFAULT 'active',
        created_at        TEXT DEFAULT (datetime('now')),
        updated_at        TEXT DEFAULT (datetime('now')),
        UNIQUE(department, business_unit, designation)
    );

    CREATE INDEX IF NOT EXISTS idx_org_dept   ON org_nodes(department);
    CREATE INDEX IF NOT EXISTS idx_org_status ON org_nodes(status);

    CREATE TABLE IF NOT EXISTS okrs (
        okr_id      TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        description TEXT NOT NULL,
        category    TEXT NOT NULL,
        owner       TEXT DEFAULT '',
        cycle       TEXT DEFAULT 'FY2025',
        status      TEXT NOT NULL DEFAULT 'active',
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_okr_status   ON okrs(status);
    CREATE INDEX IF NOT EXISTS idx_okr_category ON okrs(category);

    CREATE TABLE IF NOT EXISTS milestones (
        id             TEXT PRIMARY KEY,
        employee_id    TEXT NOT NULL,
        raw_goal       TEXT NOT NULL,
        smart_goal     TEXT,
        score_s        INTEGER DEFAULT 0,
        score_m        INTEGER DEFAULT 0,
        score_a        INTEGER DEFAULT 0,
        score_r        INTEGER DEFAULT 0,
        score_t        INTEGER DEFAULT 0,
        overall_score  INTEGER DEFAULT 0,
        okr_alignment  TEXT DEFAULT '',
        seniority_tier TEXT DEFAULT '',
        status         TEXT DEFAULT 'needs_work',
        created_at     TEXT DEFAULT (datetime('now')),
        updated_at     TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
    );

    CREATE INDEX IF NOT EXISTS idx_ms_employee ON milestones(employee_id);

    CREATE TABLE IF NOT EXISTS sessions (
        session_id  TEXT PRIMARY KEY,
        employee_id TEXT,
        messages    TEXT NOT NULL DEFAULT '[]',
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS policy_documents (
        doc_id       TEXT PRIMARY KEY,
        filename     TEXT NOT NULL,
        title        TEXT NOT NULL,
        description  TEXT DEFAULT '',
        chunk_count  INTEGER DEFAULT 0,
        status       TEXT DEFAULT 'active',
        uploaded_at  TEXT DEFAULT (datetime('now')),
        updated_at   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS app_users (
        user_id       TEXT PRIMARY KEY,
        employee_id   TEXT,
        role          TEXT NOT NULL CHECK(role IN ('employee', 'manager', 'admin')),
        display_name  TEXT NOT NULL,
        pin           TEXT NOT NULL,
        created_at    TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS auth_sessions (
        token         TEXT PRIMARY KEY,
        user_id       TEXT NOT NULL,
        expires_at    TEXT NOT NULL,
        created_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES app_users(user_id)
    );

    CREATE TABLE IF NOT EXISTS feedback_entries (
        id                   TEXT PRIMARY KEY,
        employee_id          TEXT NOT NULL,
        author_employee_id   TEXT NOT NULL,
        author_name          TEXT NOT NULL,
        feedback_type        TEXT NOT NULL DEFAULT 'continuous'
            CHECK(feedback_type IN ('continuous', 'peer', 'upward')),
        raw_text             TEXT NOT NULL,
        synthesized_commentary TEXT,
        objectivity_score    INTEGER,
        visibility           TEXT NOT NULL DEFAULT 'manager_only'
            CHECK(visibility IN ('manager_only', 'shared')),
        milestone_id         TEXT,
        cycle                TEXT DEFAULT 'FY2025',
        created_at           TEXT DEFAULT (datetime('now')),
        updated_at           TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
        FOREIGN KEY (milestone_id) REFERENCES milestones(id)
    );

    CREATE INDEX IF NOT EXISTS idx_fb_employee ON feedback_entries(employee_id);
    CREATE INDEX IF NOT EXISTS idx_fb_author ON feedback_entries(author_employee_id);

    CREATE TABLE IF NOT EXISTS performance_reviews (
        id                       TEXT PRIMARY KEY,
        employee_id              TEXT NOT NULL,
        cycle                    TEXT NOT NULL DEFAULT 'FY2025',
        review_type              TEXT NOT NULL
            CHECK(review_type IN ('mid_year', 'year_end')),
        status                   TEXT NOT NULL DEFAULT 'draft'
            CHECK(status IN ('draft', 'submitted', 'locked')),
        employee_self_assessment TEXT DEFAULT '',
        manager_summary          TEXT DEFAULT '',
        development_areas        TEXT DEFAULT '',
        overall_rating           INTEGER,
        submitted_at             TEXT,
        locked_at                TEXT,
        created_at               TEXT DEFAULT (datetime('now')),
        updated_at               TEXT DEFAULT (datetime('now')),
        UNIQUE(employee_id, cycle, review_type),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
    );

    CREATE INDEX IF NOT EXISTS idx_rev_employee ON performance_reviews(employee_id);

    CREATE TABLE IF NOT EXISTS employee_okr_assignments (
        id           TEXT PRIMARY KEY,
        employee_id  TEXT NOT NULL,
        okr_id       TEXT NOT NULL,
        assigned_by  TEXT NOT NULL,
        cycle        TEXT DEFAULT 'FY2025',
        created_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
        FOREIGN KEY (okr_id) REFERENCES okrs(okr_id),
        UNIQUE(employee_id, okr_id, cycle)
    );

    CREATE INDEX IF NOT EXISTS idx_okr_assign_employee ON employee_okr_assignments(employee_id);

    """)
    _migrate_schema(conn)
    conn.commit()
    conn.close()


def _migrate_schema(conn) -> None:
    """Add columns introduced after initial deploy."""
    milestone_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(milestones)").fetchall()
    }
    if "employee_self_assessment" not in milestone_cols:
        conn.execute(
            "ALTER TABLE milestones ADD COLUMN employee_self_assessment TEXT DEFAULT ''"
        )
    if "self_assessment_updated_at" not in milestone_cols:
        conn.execute(
            "ALTER TABLE milestones ADD COLUMN self_assessment_updated_at TEXT"
        )
    if "source_okr_id" not in milestone_cols:
        conn.execute("ALTER TABLE milestones ADD COLUMN source_okr_id TEXT")
    if "suggested_by" not in milestone_cols:
        conn.execute("ALTER TABLE milestones ADD COLUMN suggested_by TEXT")
    if "manager_suggestion" not in milestone_cols:
        conn.execute(
            "ALTER TABLE milestones ADD COLUMN manager_suggestion TEXT DEFAULT ''"
        )
    if "linked_okr_id" not in milestone_cols:
        conn.execute("ALTER TABLE milestones ADD COLUMN linked_okr_id TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_okr_assignments (
            id           TEXT PRIMARY KEY,
            employee_id  TEXT NOT NULL,
            okr_id       TEXT NOT NULL,
            assigned_by  TEXT NOT NULL,
            cycle        TEXT DEFAULT 'FY2025',
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
            FOREIGN KEY (okr_id) REFERENCES okrs(okr_id),
            UNIQUE(employee_id, okr_id, cycle)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_okr_assign_employee
        ON employee_okr_assignments(employee_id)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_activity (
            id           TEXT PRIMARY KEY,
            agent        TEXT NOT NULL,
            employee_id  TEXT,
            user_id      TEXT,
            status       TEXT NOT NULL DEFAULT 'completed',
            summary      TEXT DEFAULT '',
            duration_ms  INTEGER DEFAULT 0,
            steps_json   TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_activity_employee
        ON agent_activity(employee_id, created_at DESC)
        """
    )

    _migrate_feedback_v2(conn)
    _migrate_feedback_summaries(conn)
    _migrate_employee_health_scores(conn)
    _migrate_transparency(conn)
    _migrate_syntheses(conn)
    _migrate_employee_achievements(conn)


def _migrate_employee_achievements(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_achievements (
            achievement_id      TEXT PRIMARY KEY,
            employee_id         TEXT NOT NULL,
            type                TEXT NOT NULL
                CHECK(type IN ('certification', 'accomplishment', 'training', 'award', 'project', 'other')),
            title               TEXT NOT NULL,
            description         TEXT DEFAULT '',
            issuer_or_context   TEXT DEFAULT '',
            achieved_at         TEXT,
            review_cycle        TEXT,
            linked_milestone_id TEXT,
            visibility          TEXT NOT NULL DEFAULT 'manager'
                CHECK(visibility IN ('self', 'manager')),
            source              TEXT DEFAULT 'manual',
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_achievements_employee
        ON employee_achievements(employee_id, achieved_at DESC)
        """
    )


def _migrate_employee_health_scores(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_health_scores (
            score_id              TEXT PRIMARY KEY,
            employee_id           TEXT NOT NULL UNIQUE,
            composite_score       REAL NOT NULL DEFAULT 0,
            rag_status            TEXT NOT NULL DEFAULT 'needs_attention',
            goal_quality_score    REAL DEFAULT 0,
            checkin_score         REAL DEFAULT 0,
            feedback_score        REAL DEFAULT 0,
            review_readiness      REAL DEFAULT 0,
            trajectory_score      REAL DEFAULT 0,
            goals_total           INTEGER DEFAULT 0,
            goals_calibrated      INTEGER DEFAULT 0,
            goals_needs_work      INTEGER DEFAULT 0,
            avg_smart_score       REAL DEFAULT 0,
            last_goal_updated     TEXT,
            last_checkin_date     TEXT,
            days_since_checkin    INTEGER,
            total_sessions        INTEGER DEFAULT 0,
            feedback_count_cycle  INTEGER DEFAULT 0,
            feedback_count_total  INTEGER DEFAULT 0,
            last_feedback_date    TEXT,
            days_since_feedback   INTEGER,
            sentiment_positive    INTEGER DEFAULT 0,
            sentiment_constructive INTEGER DEFAULT 0,
            sentiment_neutral     INTEGER DEFAULT 0,
            has_balanced_feedback INTEGER DEFAULT 0,
            has_calibrated_goal   INTEGER DEFAULT 0,
            has_feedback_cycle    INTEGER DEFAULT 0,
            has_summary           INTEGER DEFAULT 0,
            had_recent_checkin    INTEGER DEFAULT 0,
            trajectory            TEXT DEFAULT 'insufficient_data',
            at_risk_reasons       TEXT DEFAULT '[]',
            computed_at           TEXT DEFAULT (datetime('now')),
            review_cycle          TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_health_rag
        ON employee_health_scores(rag_status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_health_employee
        ON employee_health_scores(employee_id)
        """
    )


def _migrate_feedback_v2(conn) -> None:
    """Expand feedback_entries for structured continuous feedback."""
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback_entries'"
    ).fetchone()
    if not table:
        return

    cols = {row[1] for row in conn.execute("PRAGMA table_info(feedback_entries)").fetchall()}
    if "review_cycle" in cols and "context" in cols:
        return

    conn.executescript(
        """
        CREATE TABLE feedback_entries_v2 (
            id                   TEXT PRIMARY KEY,
            employee_id          TEXT NOT NULL,
            author_employee_id   TEXT NOT NULL,
            author_name          TEXT NOT NULL,
            feedback_type        TEXT NOT NULL DEFAULT 'general',
            raw_text             TEXT NOT NULL,
            context              TEXT DEFAULT '',
            sentiment            TEXT NOT NULL DEFAULT 'neutral',
            tags                 TEXT DEFAULT '[]',
            review_cycle         TEXT NOT NULL DEFAULT 'FY2025-H1',
            is_draft             INTEGER NOT NULL DEFAULT 0,
            synthesized_commentary TEXT,
            objectivity_score    INTEGER,
            visibility           TEXT NOT NULL DEFAULT 'manager_only',
            milestone_id         TEXT,
            cycle                TEXT DEFAULT 'FY2025',
            created_at           TEXT DEFAULT (datetime('now')),
            updated_at           TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
            FOREIGN KEY (milestone_id) REFERENCES milestones(id)
        );

        INSERT INTO feedback_entries_v2 (
            id, employee_id, author_employee_id, author_name, feedback_type,
            raw_text, context, sentiment, tags, review_cycle, is_draft,
            synthesized_commentary, objectivity_score, visibility, milestone_id,
            cycle, created_at, updated_at
        )
        SELECT
            id, employee_id, author_employee_id, author_name,
            CASE feedback_type
                WHEN 'continuous' THEN 'general'
                WHEN 'peer' THEN 'general'
                WHEN 'upward' THEN 'general'
                ELSE COALESCE(feedback_type, 'general')
            END,
            raw_text, '', 'neutral', '[]',
            CASE
                WHEN cycle LIKE '%-H_' THEN cycle
                WHEN cycle IS NOT NULL AND cycle != '' THEN cycle || '-H1'
                ELSE 'FY2025-H1'
            END,
            0,
            synthesized_commentary, objectivity_score, visibility, milestone_id,
            COALESCE(cycle, 'FY2025'), created_at, updated_at
        FROM feedback_entries;

        DROP TABLE feedback_entries;
        ALTER TABLE feedback_entries_v2 RENAME TO feedback_entries;

        CREATE INDEX IF NOT EXISTS idx_fb_employee ON feedback_entries(employee_id);
        CREATE INDEX IF NOT EXISTS idx_fb_author ON feedback_entries(author_employee_id);
        CREATE INDEX IF NOT EXISTS idx_fb_cycle ON feedback_entries(review_cycle);
        CREATE INDEX IF NOT EXISTS idx_fb_type ON feedback_entries(feedback_type);
        CREATE INDEX IF NOT EXISTS idx_fb_created ON feedback_entries(created_at);
        """
    )


def _migrate_transparency(conn) -> None:
    aa_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(agent_activity)").fetchall()
    }
    if "workflow_id" not in aa_cols:
        conn.execute("ALTER TABLE agent_activity ADD COLUMN workflow_id TEXT")
    if "confidence_level" not in aa_cols:
        conn.execute("ALTER TABLE agent_activity ADD COLUMN confidence_level TEXT")
    if "confidence_score" not in aa_cols:
        conn.execute("ALTER TABLE agent_activity ADD COLUMN confidence_score REAL")
    if "confidence_reason" not in aa_cols:
        conn.execute("ALTER TABLE agent_activity ADD COLUMN confidence_reason TEXT")
    if "rationale_json" not in aa_cols:
        conn.execute("ALTER TABLE agent_activity ADD COLUMN rationale_json TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            workflow_id   TEXT PRIMARY KEY,
            employee_id   TEXT,
            user_id       TEXT,
            status        TEXT NOT NULL DEFAULT 'active',
            trace_count   INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_activity_workflow
        ON agent_activity(workflow_id, created_at)
        """
    )


def _migrate_syntheses(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS syntheses (
            synthesis_id        TEXT PRIMARY KEY,
            employee_id         TEXT NOT NULL,
            author_user_id      TEXT NOT NULL,
            raw_text            TEXT NOT NULL,
            commentary          TEXT,
            objectivity_score   INTEGER,
            flags_json          TEXT NOT NULL DEFAULT '[]',
            gate_blocked        INTEGER NOT NULL DEFAULT 0,
            gate_reason         TEXT,
            acknowledged_flags  TEXT,
            finalised_at        TEXT,
            created_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_syntheses_employee
        ON syntheses(employee_id, created_at DESC)
        """
    )


def _migrate_feedback_summaries(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_summaries (
            summary_id    TEXT PRIMARY KEY,
            employee_id   TEXT NOT NULL,
            review_cycle  TEXT NOT NULL,
            review_type   TEXT NOT NULL,
            content       TEXT NOT NULL,
            entry_count   INTEGER NOT NULL DEFAULT 0,
            themes        TEXT DEFAULT '[]',
            strengths     TEXT DEFAULT '[]',
            development_areas TEXT DEFAULT '[]',
            trajectory    TEXT DEFAULT 'insufficient_data',
            notable_pattern TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            confidence    TEXT DEFAULT 'medium',
            self_corrections INTEGER DEFAULT 0,
            generated_at  TEXT DEFAULT (datetime('now')),
            status        TEXT DEFAULT 'draft',
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
            UNIQUE(employee_id, review_cycle, review_type)
        )
        """
    )
