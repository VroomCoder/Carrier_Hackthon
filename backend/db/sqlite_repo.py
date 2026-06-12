import json
import re
import uuid
from datetime import datetime, timezone

from db.database import get_db
from feedback_cycle import compute_review_cycle

SENIORITY_ORDER = ["junior", "mid", "senior", "lead", "director"]

FOCUS_DESCRIPTIONS = {
    "junior": (
        "Executing assigned tasks, building foundational skills, "
        "learning processes, and delivering on clearly scoped objectives."
    ),
    "mid": (
        "Owning workstreams end-to-end, collaborating cross-functionally, "
        "improving execution quality, and developing specialist expertise."
    ),
    "senior": (
        "Leading complex initiatives, mentoring others, driving quality and "
        "consistency, and contributing to strategic decisions."
    ),
    "lead": (
        "Defining technical or functional direction, influencing org-wide "
        "standards, leading large cross-functional programmes, and developing "
        "team capability."
    ),
    "director": (
        "Setting department strategy, accountable for business outcomes, "
        "building high-performing teams, and representing the function at "
        "executive level."
    ),
}

DEPT_OKR_CATEGORIES = {
    "Engineering": ["Engineering", "Security"],
    "Data & Analytics": ["Engineering", "Product"],
    "Product": ["Product", "Engineering"],
    "Sales": ["Sales", "Customer Success"],
    "Customer Success": ["Customer Success", "Sales"],
    "Marketing": ["Sales", "Product"],
    "HR": ["People"],
    "Finance": ["Finance"],
    "Legal": ["Security", "Finance"],
    "IT Support": ["Engineering", "Security"],
    "Operations": ["Finance", "Customer Success"],
}


def slugify(text: str) -> str:
    text = text.lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def compute_seniority_tier(designation: str) -> str:
    d = designation.lower()
    if "director" in d or "vp of" in d or "head of" in d:
        return "director"
    if "principal" in d or "lead " in d or d.startswith("lead ") or "staff " in d:
        return "lead"
    if "senior" in d:
        return "senior"
    if (
        "associate" in d
        or "coordinator" in d
        or ("analyst" in d and "senior" not in d)
        or "development rep" in d
        or "sdr" in d
        or " i " in f" {d} "
    ):
        return "junior"
    return "mid"


def compute_node_fields(department: str, business_unit: str, designation: str) -> dict:
    node_id = slugify(f"{department}__{business_unit}__{designation}")
    seniority_tier = compute_seniority_tier(designation)
    focus_description = FOCUS_DESCRIPTIONS[seniority_tier]
    categories = DEPT_OKR_CATEGORIES.get(department, ["Engineering", "Product"])
    okr_categories = ",".join(categories)
    return {
        "node_id": node_id,
        "seniority_tier": seniority_tier,
        "focus_description": focus_description,
        "okr_categories": okr_categories,
    }


class SqliteRepo:
    """All SQLite database operations."""

    # ── EMPLOYEES ──────────────────────────────────────────────────────

    def upsert_employee(self, emp: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO employees (
                    employee_id, name, email, department, sub_department,
                    job_title, grade, manager_id, manager_name, location,
                    join_date, employment_type, leave_balance, work_mode,
                    phone_extension, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(employee_id) DO UPDATE SET
                    name=excluded.name, email=excluded.email,
                    department=excluded.department, sub_department=excluded.sub_department,
                    job_title=excluded.job_title, grade=excluded.grade,
                    manager_id=excluded.manager_id, manager_name=excluded.manager_name,
                    location=excluded.location, join_date=excluded.join_date,
                    employment_type=excluded.employment_type, leave_balance=excluded.leave_balance,
                    work_mode=excluded.work_mode, phone_extension=excluded.phone_extension,
                    updated_at=datetime('now')
                """,
                (
                    emp["employee_id"],
                    emp["name"],
                    emp.get("email"),
                    emp.get("department"),
                    emp.get("sub_department"),
                    emp.get("job_title"),
                    emp.get("grade"),
                    emp.get("manager_id"),
                    emp.get("manager_name"),
                    emp.get("location"),
                    emp.get("join_date"),
                    emp.get("employment_type"),
                    emp.get("leave_balance"),
                    emp.get("work_mode"),
                    emp.get("phone_extension"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_employee_by_id(self, employee_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def search_employees(
        self,
        query: str,
        limit: int = 5,
        allowed_ids: list[str] | None = None,
    ) -> list[dict]:
        conn = get_db()
        try:
            q = query.strip()
            if not q:
                if allowed_ids is not None:
                    return self.get_employees_by_ids(allowed_ids[:limit])
                return []
            fts_query = " OR ".join(f'"{term}"' for term in q.split())
            rows = conn.execute(
                """
                SELECT e.* FROM employees e
                JOIN employees_fts fts ON e.rowid = fts.rowid
                WHERE employees_fts MATCH ?
                LIMIT ?
                """,
                (fts_query, limit * 3 if allowed_ids else limit),
            ).fetchall()
            if not rows:
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT * FROM employees
                    WHERE name LIKE ? OR department LIKE ? OR job_title LIKE ?
                       OR sub_department LIKE ? OR employee_id LIKE ?
                    LIMIT ?
                    """,
                    (like, like, like, like, like, limit * 3 if allowed_ids else limit),
                ).fetchall()
            results = [dict(r) for r in rows]
            if allowed_ids is not None:
                allowed_set = set(allowed_ids)
                results = [r for r in results if r["employee_id"] in allowed_set]
            results = results[:limit]
            try:
                from agent_trace import log_search

                log_search("employees_fts", q, results)
            except ImportError:
                pass
            return results
        finally:
            conn.close()

    def get_employees_by_ids(self, employee_ids: list[str]) -> list[dict]:
        if not employee_ids:
            return []
        conn = get_db()
        try:
            placeholders = ",".join("?" * len(employee_ids))
            rows = conn.execute(
                f"SELECT * FROM employees WHERE employee_id IN ({placeholders}) ORDER BY name",
                employee_ids,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_direct_reports(self, manager_id: str) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM employees WHERE manager_id = ? ORDER BY name",
                (manager_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_employees(self) -> int:
        conn = get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        finally:
            conn.close()

    def get_employees_by_department(self, dept: str) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM employees WHERE department = ? ORDER BY name",
                (dept,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── ORG NODES ──────────────────────────────────────────────────────

    def upsert_org_node(self, node: dict) -> None:
        computed = compute_node_fields(
            node["department"], node["business_unit"], node["designation"]
        )
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO org_nodes (
                    node_id, department, business_unit, designation,
                    seniority_tier, focus_description, okr_categories,
                    status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(department, business_unit, designation) DO UPDATE SET
                    seniority_tier=excluded.seniority_tier,
                    focus_description=excluded.focus_description,
                    okr_categories=excluded.okr_categories,
                    status=excluded.status,
                    updated_at=datetime('now')
                """,
                (
                    computed["node_id"],
                    node["department"],
                    node["business_unit"],
                    node["designation"],
                    computed["seniority_tier"],
                    computed["focus_description"],
                    computed["okr_categories"],
                    node.get("status", "active"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_departments(self) -> list[str]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT department FROM org_nodes WHERE status='active' ORDER BY department"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def get_business_units(self, department: str) -> list[str]:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT business_unit FROM org_nodes
                WHERE department = ? AND status = 'active'
                ORDER BY business_unit
                """,
                (department,),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def get_designations(self, department: str, business_unit: str) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT * FROM org_nodes
                WHERE department = ? AND business_unit = ? AND status = 'active'
                """,
                (department, business_unit),
            ).fetchall()
            nodes = [dict(r) for r in rows]
            nodes.sort(
                key=lambda n: SENIORITY_ORDER.index(n["seniority_tier"])
                if n["seniority_tier"] in SENIORITY_ORDER
                else 99
            )
            return [n["designation"] for n in nodes]
        finally:
            conn.close()

    def get_org_node(
        self, department: str, business_unit: str, designation: str
    ) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT * FROM org_nodes
                WHERE department = ? AND business_unit = ? AND designation = ?
                """,
                (department, business_unit, designation),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def validate_org_node(
        self, department: str, business_unit: str, designation: str
    ) -> bool:
        return self.get_org_node(department, business_unit, designation) is not None

    def get_all_org_nodes(
        self, status: str | None = None, department: str | None = None
    ) -> list[dict]:
        conn = get_db()
        try:
            query = "SELECT * FROM org_nodes WHERE 1=1"
            params: list = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if department:
                query += " AND department = ?"
                params.append(department)
            query += " ORDER BY department, business_unit, designation"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def search_org_nodes(self, query: str) -> list[dict]:
        conn = get_db()
        try:
            like = f"%{query.strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM org_nodes
                WHERE department LIKE ? OR business_unit LIKE ? OR designation LIKE ?
                ORDER BY department, business_unit, designation
                LIMIT 50
                """,
                (like, like, like),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def archive_org_node(self, node_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "UPDATE org_nodes SET status='archived', updated_at=datetime('now') WHERE node_id=?",
                (node_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def activate_org_node(self, node_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "UPDATE org_nodes SET status='active', updated_at=datetime('now') WHERE node_id=?",
                (node_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_org_node(self, node_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM org_nodes WHERE node_id = ?", (node_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def count_org_nodes(self, status: str = "active") -> int:
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM org_nodes WHERE status = ?", (status,)
            ).fetchone()[0]
        finally:
            conn.close()

    def bulk_upsert_org_nodes(self, nodes: list[dict]) -> int:
        for node in nodes:
            self.upsert_org_node(node)
        return len(nodes)

    # ── OKRs ───────────────────────────────────────────────────────────

    def upsert_okr(self, okr: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO okrs (
                    okr_id, title, description, category, owner, cycle, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(okr_id) DO UPDATE SET
                    title=excluded.title, description=excluded.description,
                    category=excluded.category, owner=excluded.owner,
                    cycle=excluded.cycle, status=excluded.status,
                    updated_at=datetime('now')
                """,
                (
                    okr["okr_id"],
                    okr["title"],
                    okr["description"],
                    okr["category"],
                    okr.get("owner", ""),
                    okr.get("cycle", "FY2025"),
                    okr.get("status", "active"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_okrs(
        self, status: str | None = None, department: str | None = None
    ) -> list[dict]:
        conn = get_db()
        try:
            query = "SELECT * FROM okrs WHERE 1=1"
            params: list = []
            if status:
                query += " AND status = ?"
                params.append(status)
            rows = conn.execute(query + " ORDER BY category, title", params).fetchall()
            okrs = [dict(r) for r in rows]
            if department:
                categories = DEPT_OKR_CATEGORIES.get(
                    department, ["Engineering", "Product"]
                )
                okrs = [o for o in okrs if o["category"] in categories]
            return okrs
        finally:
            conn.close()

    def get_okr_by_id(self, okr_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM okrs WHERE okr_id = ?", (okr_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_okr(self, okr_id: str, updates: dict) -> dict | None:
        existing = self.get_okr_by_id(okr_id)
        if not existing:
            return None
        merged = {**existing, **updates, "okr_id": okr_id}
        self.upsert_okr(merged)
        return self.get_okr_by_id(okr_id)

    def delete_okr(self, okr_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM okrs WHERE okr_id = ?", (okr_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def archive_okr(self, okr_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "UPDATE okrs SET status='archived', updated_at=datetime('now') WHERE okr_id=?",
                (okr_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def activate_okr(self, okr_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "UPDATE okrs SET status='active', updated_at=datetime('now') WHERE okr_id=?",
                (okr_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def count_okrs(self, status: str = "active") -> int:
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM okrs WHERE status = ?", (status,)
            ).fetchone()[0]
        finally:
            conn.close()

    def get_active_okr_texts(self) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT okr_id, title, description, category, status FROM okrs WHERE status='active'"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── MILESTONES ─────────────────────────────────────────────────────

    def upsert_milestone(self, milestone: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO milestones (
                    id, employee_id, raw_goal, smart_goal,
                    score_s, score_m, score_a, score_r, score_t,
                    overall_score, okr_alignment, seniority_tier, status,
                    source_okr_id, suggested_by, manager_suggestion, linked_okr_id,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    raw_goal=excluded.raw_goal, smart_goal=excluded.smart_goal,
                    score_s=excluded.score_s, score_m=excluded.score_m,
                    score_a=excluded.score_a, score_r=excluded.score_r,
                    score_t=excluded.score_t, overall_score=excluded.overall_score,
                    okr_alignment=excluded.okr_alignment,
                    seniority_tier=excluded.seniority_tier, status=excluded.status,
                    source_okr_id=excluded.source_okr_id,
                    suggested_by=excluded.suggested_by,
                    manager_suggestion=excluded.manager_suggestion,
                    linked_okr_id=excluded.linked_okr_id,
                    updated_at=datetime('now')
                """,
                (
                    milestone["id"],
                    milestone["employee_id"],
                    milestone["raw_goal"],
                    milestone.get("smart_goal"),
                    milestone.get("score_s", 0),
                    milestone.get("score_m", 0),
                    milestone.get("score_a", 0),
                    milestone.get("score_r", 0),
                    milestone.get("score_t", 0),
                    milestone.get("overall_score", 0),
                    milestone.get("okr_alignment", ""),
                    milestone.get("seniority_tier", ""),
                    milestone.get("status", "needs_work"),
                    milestone.get("source_okr_id"),
                    milestone.get("suggested_by"),
                    milestone.get("manager_suggestion", ""),
                    milestone.get("linked_okr_id"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def create_suggested_goal(
        self,
        employee_id: str,
        raw_goal: str,
        suggested_by: str,
        linked_okr_id: str | None = None,
    ) -> dict:
        milestone_id = self.new_milestone_id()
        milestone = {
            "id": milestone_id,
            "employee_id": employee_id,
            "raw_goal": raw_goal,
            "smart_goal": None,
            "score_s": 0,
            "score_m": 0,
            "score_a": 0,
            "score_r": 0,
            "score_t": 0,
            "overall_score": 0,
            "okr_alignment": "",
            "seniority_tier": "",
            "status": "suggested",
            "suggested_by": suggested_by,
            "manager_suggestion": raw_goal,
            "linked_okr_id": linked_okr_id,
            "source_okr_id": linked_okr_id,
        }
        self.upsert_milestone(milestone)
        return self.get_milestone_by_id(milestone_id) or milestone

    def employee_has_source_okr(self, employee_id: str, source_okr_id: str) -> bool:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT 1 FROM milestones
                WHERE employee_id = ? AND source_okr_id = ?
                LIMIT 1
                """,
                (employee_id, source_okr_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def get_milestones_by_employee(self, employee_id: str) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM milestones WHERE employee_id = ? ORDER BY created_at DESC",
                (employee_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_milestone_by_id(self, milestone_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM milestones WHERE id = ?", (milestone_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_milestone(self, milestone_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── EMPLOYEE OKR ASSIGNMENTS ───────────────────────────────────────

    def get_okr_assignments_for_employee(
        self, employee_id: str, cycle: str | None = None
    ) -> list[dict]:
        conn = get_db()
        try:
            query = """
                SELECT a.*, o.title, o.description, o.category, o.owner, o.status AS okr_status
                FROM employee_okr_assignments a
                JOIN okrs o ON o.okr_id = a.okr_id
                WHERE a.employee_id = ?
            """
            params: list = [employee_id]
            if cycle:
                query += " AND a.cycle = ?"
                params.append(cycle)
            query += " ORDER BY a.created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_okr_assignments(self, employee_id: str, cycle: str) -> int:
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM employee_okr_assignments WHERE employee_id = ? AND cycle = ?",
                (employee_id, cycle),
            ).fetchone()[0]
        finally:
            conn.close()

    def has_okr_assignment(
        self, employee_id: str, okr_id: str, cycle: str | None = None
    ) -> bool:
        conn = get_db()
        try:
            if cycle:
                row = conn.execute(
                    """
                    SELECT 1 FROM employee_okr_assignments
                    WHERE employee_id = ? AND okr_id = ? AND cycle = ?
                    """,
                    (employee_id, okr_id, cycle),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 1 FROM employee_okr_assignments
                    WHERE employee_id = ? AND okr_id = ?
                    """,
                    (employee_id, okr_id),
                ).fetchone()
            return row is not None
        finally:
            conn.close()

    def create_okr_assignment(
        self,
        employee_id: str,
        okr_id: str,
        assigned_by: str,
        cycle: str,
    ) -> dict:
        assignment_id = f"asgn_{uuid.uuid4().hex[:8]}"
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO employee_okr_assignments (id, employee_id, okr_id, assigned_by, cycle)
                VALUES (?, ?, ?, ?, ?)
                """,
                (assignment_id, employee_id, okr_id, assigned_by, cycle),
            )
            conn.commit()
        finally:
            conn.close()
        rows = self.get_okr_assignments_for_employee(employee_id, cycle=cycle)
        return next((r for r in rows if r["id"] == assignment_id), rows[0] if rows else {})

    def delete_okr_assignment(self, assignment_id: str, employee_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "DELETE FROM employee_okr_assignments WHERE id = ? AND employee_id = ?",
                (assignment_id, employee_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_milestone_self_assessment(
        self, milestone_id: str, employee_id: str, assessment: str
    ) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT employee_id FROM milestones WHERE id = ?", (milestone_id,)
            ).fetchone()
            if not row or row[0] != employee_id:
                return None
            conn.execute(
                """
                UPDATE milestones
                SET employee_self_assessment = ?,
                    self_assessment_updated_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (assessment, milestone_id),
            )
            conn.commit()
            return self.get_milestone_by_id(milestone_id)
        finally:
            conn.close()

    def get_all_milestones_for_sync(self) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM milestones").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── FEEDBACK ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_tags(raw: str | list | None) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _feedback_row_to_dict(row: dict) -> dict:
        result = dict(row)
        result["tags"] = SqliteRepo._parse_tags(result.get("tags"))
        result["is_draft"] = bool(result.get("is_draft", 0))
        result["content"] = result.get("raw_text", "")
        result["entry_id"] = result.get("id")
        result["manager_name"] = result.get("author_name")
        if result.get("visibility") == "shared":
            result["visibility_label"] = "shared_with_employee"
        return result

    def insert_feedback(self, entry: dict) -> dict:
        conn = get_db()
        entry_id = entry.get("id") or entry.get("entry_id") or self.new_feedback_id()
        tags = entry.get("tags", [])
        tags_json = json.dumps(tags) if isinstance(tags, list) else (tags or "[]")
        review_cycle = entry.get("review_cycle") or compute_review_cycle(
            entry.get("created_at")
        )
        raw_text = entry.get("raw_text") or entry.get("content", "")
        try:
            conn.execute(
                """
                INSERT INTO feedback_entries (
                    id, employee_id, author_employee_id, author_name,
                    feedback_type, raw_text, context, sentiment, tags,
                    review_cycle, is_draft, synthesized_commentary,
                    objectivity_score, visibility, milestone_id, cycle
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    entry["employee_id"],
                    entry.get("author_employee_id") or entry.get("manager_id") or "admin",
                    entry.get("author_name") or entry.get("manager_name") or "Manager",
                    entry.get("feedback_type", "general"),
                    raw_text,
                    entry.get("context", ""),
                    entry.get("sentiment", "neutral"),
                    tags_json,
                    review_cycle,
                    1 if entry.get("is_draft") else 0,
                    entry.get("synthesized_commentary"),
                    entry.get("objectivity_score"),
                    self._normalize_visibility(entry.get("visibility", "manager_only")),
                    entry.get("milestone_id"),
                    entry.get("cycle", "FY2025"),
                ),
            )
            conn.commit()
            row = self.get_feedback_by_id(entry_id)
            return row if row else entry
        finally:
            conn.close()

    @staticmethod
    def _normalize_visibility(visibility: str) -> str:
        if visibility in ("shared_with_employee", "shared"):
            return "shared"
        return "manager_only"

    def get_feedback_by_id(self, feedback_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM feedback_entries WHERE id = ?", (feedback_id,)
            ).fetchone()
            return self._feedback_row_to_dict(dict(row)) if row else None
        finally:
            conn.close()

    def create_feedback_entry(self, entry: dict) -> dict:
        return self.insert_feedback(entry)

    def get_feedback_entry(self, entry_id: str) -> dict | None:
        return self.get_feedback_by_id(entry_id)

    def update_feedback_entry(self, entry_id: str, updates: dict) -> dict | None:
        allowed = {
            "raw_text",
            "content",
            "context",
            "feedback_type",
            "sentiment",
            "visibility",
            "tags",
            "is_draft",
            "synthesized_commentary",
            "objectivity_score",
        }
        fields: dict = {}
        for key, val in updates.items():
            if key == "content":
                fields["raw_text"] = val
            elif key in allowed and key != "content":
                fields[key] = val
        if "visibility" in fields:
            fields["visibility"] = self._normalize_visibility(fields["visibility"])
        if "tags" in fields and isinstance(fields["tags"], list):
            fields["tags"] = json.dumps(fields["tags"])
        if "is_draft" in fields:
            fields["is_draft"] = 1 if fields["is_draft"] else 0
        if not fields:
            return self.get_feedback_by_id(entry_id)
        fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn = get_db()
        try:
            conn.execute(
                f"UPDATE feedback_entries SET {set_clause} WHERE id = ?",
                (*fields.values(), entry_id),
            )
            conn.commit()
            return self.get_feedback_by_id(entry_id)
        finally:
            conn.close()

    def delete_feedback_entry(self, entry_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute("DELETE FROM feedback_entries WHERE id = ?", (entry_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_entries_for_employee(
        self,
        employee_id: str,
        review_cycle: str | None = None,
        feedback_type: str | None = None,
        sentiment: str | None = None,
        visibility: str | None = None,
        include_drafts: bool = False,
    ) -> list[dict]:
        conn = get_db()
        try:
            query = "SELECT * FROM feedback_entries WHERE employee_id = ?"
            params: list = [employee_id]
            if not include_drafts:
                query += " AND is_draft = 0"
            if review_cycle:
                query += " AND review_cycle = ?"
                params.append(review_cycle)
            if feedback_type:
                query += " AND feedback_type = ?"
                params.append(feedback_type)
            if sentiment:
                query += " AND sentiment = ?"
                params.append(sentiment)
            if visibility:
                vis = self._normalize_visibility(visibility)
                query += " AND visibility = ?"
                params.append(vis)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._feedback_row_to_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_entries_for_review(self, employee_id: str, review_cycle: str) -> list[dict]:
        return self.get_entries_for_employee(
            employee_id, review_cycle=review_cycle, include_drafts=False
        )

    def count_entries(self, employee_id: str, review_cycle: str | None = None) -> int:
        conn = get_db()
        try:
            if review_cycle:
                return conn.execute(
                    """
                    SELECT COUNT(*) FROM feedback_entries
                    WHERE employee_id = ? AND review_cycle = ? AND is_draft = 0
                    """,
                    (employee_id, review_cycle),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM feedback_entries WHERE employee_id = ? AND is_draft = 0",
                (employee_id,),
            ).fetchone()[0]
        finally:
            conn.close()

    def get_all_entries_for_sync(self) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback_entries WHERE is_draft = 0"
            ).fetchall()
            return [self._feedback_row_to_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def upsert_feedback_summary(self, summary: dict) -> None:
        conn = get_db()
        themes = summary.get("themes", [])
        strengths = summary.get("strengths", [])
        dev = summary.get("development_areas", [])
        try:
            conn.execute(
                """
                INSERT INTO feedback_summaries (
                    summary_id, employee_id, review_cycle, review_type, content,
                    entry_count, themes, strengths, development_areas, trajectory,
                    notable_pattern, quality_score, confidence, self_corrections,
                    generated_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                ON CONFLICT(employee_id, review_cycle, review_type) DO UPDATE SET
                    summary_id=excluded.summary_id,
                    content=excluded.content,
                    entry_count=excluded.entry_count,
                    themes=excluded.themes,
                    strengths=excluded.strengths,
                    development_areas=excluded.development_areas,
                    trajectory=excluded.trajectory,
                    notable_pattern=excluded.notable_pattern,
                    quality_score=excluded.quality_score,
                    confidence=excluded.confidence,
                    self_corrections=excluded.self_corrections,
                    generated_at=datetime('now'),
                    status=excluded.status
                """,
                (
                    summary["summary_id"],
                    summary["employee_id"],
                    summary["review_cycle"],
                    summary["review_type"],
                    summary["content"],
                    summary.get("entry_count", 0),
                    json.dumps(themes if isinstance(themes, list) else []),
                    json.dumps(strengths if isinstance(strengths, list) else []),
                    json.dumps(dev if isinstance(dev, list) else []),
                    summary.get("trajectory", "insufficient_data"),
                    summary.get("notable_pattern") or "",
                    summary.get("quality_score", 0),
                    summary.get("confidence", "medium"),
                    summary.get("self_corrections", 0),
                    summary.get("status", "draft"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_feedback_summary(
        self, employee_id: str, review_cycle: str, review_type: str
    ) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT * FROM feedback_summaries
                WHERE employee_id = ? AND review_cycle = ? AND review_type = ?
                """,
                (employee_id, review_cycle, review_type),
            ).fetchone()
            if not row:
                return None
            return self._summary_row_to_dict(dict(row))
        finally:
            conn.close()

    def get_latest_summary(self, employee_id: str, review_type: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT * FROM feedback_summaries
                WHERE employee_id = ? AND review_type = ?
                ORDER BY generated_at DESC LIMIT 1
                """,
                (employee_id, review_type),
            ).fetchone()
            return self._summary_row_to_dict(dict(row)) if row else None
        finally:
            conn.close()

    def finalise_feedback_summary(self, summary_id: str) -> dict | None:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE feedback_summaries SET status = 'finalised' WHERE summary_id = ?",
                (summary_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM feedback_summaries WHERE summary_id = ?", (summary_id,)
            ).fetchone()
            return self._summary_row_to_dict(dict(row)) if row else None
        finally:
            conn.close()

    @staticmethod
    def _summary_row_to_dict(row: dict) -> dict:
        result = dict(row)
        for field in ("themes", "strengths", "development_areas"):
            try:
                result[field] = json.loads(result.get(field) or "[]")
            except json.JSONDecodeError:
                result[field] = []
        return result

    def feedback_stats(self, employee_id: str, current_cycle: str) -> dict:
        entries = self.get_entries_for_employee(employee_id, include_drafts=False)
        by_type: dict[str, int] = {}
        by_sentiment: dict[str, int] = {}
        by_cycle: dict[str, int] = {}
        last_date = None
        for e in entries:
            ft = e.get("feedback_type", "general")
            by_type[ft] = by_type.get(ft, 0) + 1
            sent = e.get("sentiment", "neutral")
            by_sentiment[sent] = by_sentiment.get(sent, 0) + 1
            rc = e.get("review_cycle", "")
            by_cycle[rc] = by_cycle.get(rc, 0) + 1
            if e.get("created_at") and (not last_date or e["created_at"] > last_date):
                last_date = e["created_at"]
        current_count = by_cycle.get(current_cycle, 0)
        has_summary = bool(
            self.get_feedback_summary(employee_id, current_cycle, "mid_year")
            or self.get_feedback_summary(employee_id, current_cycle, "year_end")
        )
        return {
            "total_entries": len(entries),
            "current_cycle_entries": current_count,
            "by_type": by_type,
            "by_sentiment": by_sentiment,
            "by_cycle": by_cycle,
            "has_summary_this_cycle": has_summary,
            "last_entry_date": last_date,
        }

    def list_feedback_for_employee(
        self,
        employee_id: str,
        *,
        include_manager_only: bool = True,
        cycle: str | None = None,
    ) -> list[dict]:
        conn = get_db()
        try:
            query = "SELECT * FROM feedback_entries WHERE employee_id = ?"
            params: list = [employee_id]
            if not include_manager_only:
                query += " AND visibility = 'shared'"
            if cycle:
                query += " AND cycle = ?"
                params.append(cycle)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._feedback_row_to_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def update_feedback(self, feedback_id: str, updates: dict) -> dict | None:
        return self.update_feedback_entry(feedback_id, updates)

    def count_feedback_for_employee(
        self, employee_id: str, *, shared_only: bool = False
    ) -> int:
        conn = get_db()
        try:
            if shared_only:
                return conn.execute(
                    "SELECT COUNT(*) FROM feedback_entries WHERE employee_id = ? AND visibility = 'shared'",
                    (employee_id,),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM feedback_entries WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()[0]
        finally:
            conn.close()

    # ── SYNTHESIS (bias gate) ──────────────────────────────────────────

    def _parse_synthesis_row(self, row) -> dict:
        item = dict(row)
        try:
            item["flags"] = json.loads(item.pop("flags_json", "[]") or "[]")
        except json.JSONDecodeError:
            item["flags"] = []
        ack = item.pop("acknowledged_flags", None)
        if ack:
            try:
                item["acknowledged_flags"] = json.loads(ack)
            except json.JSONDecodeError:
                item["acknowledged_flags"] = []
        else:
            item["acknowledged_flags"] = []
        item["gate_blocked"] = bool(item.get("gate_blocked"))
        return item

    def insert_synthesis(self, row: dict) -> dict:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO syntheses (
                    synthesis_id, employee_id, author_user_id, raw_text,
                    commentary, objectivity_score, flags_json, gate_blocked,
                    gate_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["synthesis_id"],
                    row["employee_id"],
                    row["author_user_id"],
                    row["raw_text"],
                    row.get("commentary"),
                    row.get("objectivity_score"),
                    json.dumps(row.get("flags") or []),
                    1 if row.get("gate_blocked") else 0,
                    row.get("gate_reason"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_synthesis(row["synthesis_id"]) or row

    def get_synthesis(self, synthesis_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM syntheses WHERE synthesis_id = ?",
                (synthesis_id,),
            ).fetchone()
            return self._parse_synthesis_row(row) if row else None
        finally:
            conn.close()

    def finalise_synthesis(
        self, synthesis_id: str, acknowledged_flags: list[str]
    ) -> dict | None:
        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE syntheses
                SET acknowledged_flags = ?,
                    finalised_at = datetime('now')
                WHERE synthesis_id = ?
                """,
                (json.dumps(acknowledged_flags), synthesis_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_synthesis(synthesis_id)

    # ── PERFORMANCE REVIEWS ────────────────────────────────────────────

    def get_or_create_review(
        self, employee_id: str, review_type: str, cycle: str = "FY2025"
    ) -> dict:
        existing = self.get_review(employee_id, review_type, cycle)
        if existing:
            return existing
        review_id = self.new_review_id()
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO performance_reviews (
                    id, employee_id, cycle, review_type, status
                ) VALUES (?, ?, ?, ?, 'draft')
                """,
                (review_id, employee_id, cycle, review_type),
            )
            conn.commit()
            return self.get_review(employee_id, review_type, cycle) or {
                "id": review_id,
                "employee_id": employee_id,
                "cycle": cycle,
                "review_type": review_type,
                "status": "draft",
            }
        finally:
            conn.close()

    def get_review(
        self, employee_id: str, review_type: str, cycle: str = "FY2025"
    ) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT * FROM performance_reviews
                WHERE employee_id = ? AND review_type = ? AND cycle = ?
                """,
                (employee_id, review_type, cycle),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_reviews_for_employee(
        self, employee_id: str, cycle: str | None = None
    ) -> list[dict]:
        conn = get_db()
        try:
            if cycle:
                rows = conn.execute(
                    """
                    SELECT * FROM performance_reviews
                    WHERE employee_id = ? AND cycle = ?
                    ORDER BY review_type
                    """,
                    (employee_id, cycle),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM performance_reviews
                    WHERE employee_id = ?
                    ORDER BY cycle DESC, review_type
                    """,
                    (employee_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_review(self, review_id: str, updates: dict) -> dict | None:
        allowed = {
            "employee_self_assessment",
            "manager_summary",
            "development_areas",
            "overall_rating",
            "status",
            "submitted_at",
            "locked_at",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return self.get_review_by_id(review_id)
        fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn = get_db()
        try:
            conn.execute(
                f"UPDATE performance_reviews SET {set_clause} WHERE id = ?",
                (*fields.values(), review_id),
            )
            conn.commit()
            return self.get_review_by_id(review_id)
        finally:
            conn.close()

    def get_review_by_id(self, review_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM performance_reviews WHERE id = ?", (review_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def new_feedback_id() -> str:
        return f"fb_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def new_feedback_summary_id() -> str:
        return f"fs_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def new_review_id() -> str:
        return f"rev_{uuid.uuid4().hex[:8]}"

    # ── SESSIONS ───────────────────────────────────────────────────────

    def upsert_session(
        self, session_id: str, employee_id: str | None, messages: list
    ) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO sessions (session_id, employee_id, messages, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    employee_id=excluded.employee_id,
                    messages=excluded.messages,
                    updated_at=datetime('now')
                """,
                (session_id, employee_id, json.dumps(messages)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["messages"] = json.loads(result["messages"])
            return result
        finally:
            conn.close()

    def get_recent_messages(self, employee_id: str, limit: int = 10) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT messages FROM sessions
                WHERE employee_id = ?
                ORDER BY updated_at DESC
                LIMIT 5
                """,
                (employee_id,),
            ).fetchall()
            all_msgs: list[dict] = []
            for row in rows:
                msgs = json.loads(row[0])
                all_msgs.extend(msgs)
            return all_msgs[-limit:]
        finally:
            conn.close()

    def get_latest_session_for_employee(self, employee_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT session_id, employee_id, updated_at, created_at
                FROM sessions
                WHERE employee_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (employee_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def count_sessions_for_employee(self, employee_id: str) -> int:
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()[0]
        finally:
            conn.close()

    # ── EMPLOYEE HEALTH SCORES ───────────────────────────────────────────

    def upsert_health_score(self, score: dict) -> None:
        conn = get_db()
        reasons_json = json.dumps(score.get("at_risk_reasons") or [])
        try:
            conn.execute(
                """
                INSERT INTO employee_health_scores (
                    score_id, employee_id, composite_score, rag_status,
                    goal_quality_score, checkin_score, feedback_score,
                    review_readiness, trajectory_score,
                    goals_total, goals_calibrated, goals_needs_work,
                    avg_smart_score, last_goal_updated,
                    last_checkin_date, days_since_checkin, total_sessions,
                    feedback_count_cycle, feedback_count_total,
                    last_feedback_date, days_since_feedback,
                    sentiment_positive, sentiment_constructive, sentiment_neutral,
                    has_balanced_feedback, has_calibrated_goal,
                    has_feedback_cycle, has_summary, had_recent_checkin,
                    trajectory, at_risk_reasons, computed_at, review_cycle
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id) DO UPDATE SET
                    composite_score=excluded.composite_score,
                    rag_status=excluded.rag_status,
                    goal_quality_score=excluded.goal_quality_score,
                    checkin_score=excluded.checkin_score,
                    feedback_score=excluded.feedback_score,
                    review_readiness=excluded.review_readiness,
                    trajectory_score=excluded.trajectory_score,
                    goals_total=excluded.goals_total,
                    goals_calibrated=excluded.goals_calibrated,
                    goals_needs_work=excluded.goals_needs_work,
                    avg_smart_score=excluded.avg_smart_score,
                    last_goal_updated=excluded.last_goal_updated,
                    last_checkin_date=excluded.last_checkin_date,
                    days_since_checkin=excluded.days_since_checkin,
                    total_sessions=excluded.total_sessions,
                    feedback_count_cycle=excluded.feedback_count_cycle,
                    feedback_count_total=excluded.feedback_count_total,
                    last_feedback_date=excluded.last_feedback_date,
                    days_since_feedback=excluded.days_since_feedback,
                    sentiment_positive=excluded.sentiment_positive,
                    sentiment_constructive=excluded.sentiment_constructive,
                    sentiment_neutral=excluded.sentiment_neutral,
                    has_balanced_feedback=excluded.has_balanced_feedback,
                    has_calibrated_goal=excluded.has_calibrated_goal,
                    has_feedback_cycle=excluded.has_feedback_cycle,
                    has_summary=excluded.has_summary,
                    had_recent_checkin=excluded.had_recent_checkin,
                    trajectory=excluded.trajectory,
                    at_risk_reasons=excluded.at_risk_reasons,
                    computed_at=excluded.computed_at,
                    review_cycle=excluded.review_cycle
                """,
                (
                    score.get("score_id") or f"hs_{uuid.uuid4().hex[:8]}",
                    score["employee_id"],
                    score.get("composite_score", 0),
                    score.get("rag_status", "needs_attention"),
                    score.get("goal_quality_score", 0),
                    score.get("checkin_score", 0),
                    score.get("feedback_score", 0),
                    score.get("review_readiness", 0),
                    score.get("trajectory_score", 0),
                    score.get("goals_total", 0),
                    score.get("goals_calibrated", 0),
                    score.get("goals_needs_work", 0),
                    score.get("avg_smart_score", 0),
                    score.get("last_goal_updated"),
                    score.get("last_checkin_date"),
                    score.get("days_since_checkin"),
                    score.get("total_sessions", 0),
                    score.get("feedback_count_cycle", 0),
                    score.get("feedback_count_total", 0),
                    score.get("last_feedback_date"),
                    score.get("days_since_feedback"),
                    int(score.get("sentiment_positive", 0)),
                    int(score.get("sentiment_constructive", 0)),
                    int(score.get("sentiment_neutral", 0)),
                    1 if score.get("has_balanced_feedback") else 0,
                    1 if score.get("has_calibrated_goal") else 0,
                    1 if score.get("has_feedback_cycle") else 0,
                    1 if score.get("has_summary") else 0,
                    1 if score.get("had_recent_checkin") else 0,
                    score.get("trajectory", "insufficient_data"),
                    reasons_json,
                    score.get("computed_at"),
                    score.get("review_cycle", ""),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _health_row_to_dict(row: dict) -> dict:
        result = dict(row)
        try:
            result["at_risk_reasons"] = json.loads(result.get("at_risk_reasons") or "[]")
        except json.JSONDecodeError:
            result["at_risk_reasons"] = []
        for flag in (
            "has_balanced_feedback",
            "has_calibrated_goal",
            "has_feedback_cycle",
            "has_summary",
            "had_recent_checkin",
        ):
            result[flag] = bool(result.get(flag, 0))
        return result

    def get_health_score(self, employee_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM employee_health_scores WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
            return self._health_row_to_dict(dict(row)) if row else None
        finally:
            conn.close()

    def get_all_health_scores(
        self,
        manager_id: str | None = None,
        rag_status: str | None = None,
    ) -> list[dict]:
        conn = get_db()
        try:
            query = "SELECT hs.* FROM employee_health_scores hs"
            params: list = []
            clauses: list[str] = []
            if manager_id:
                query += " JOIN employees e ON hs.employee_id = e.employee_id"
                clauses.append("e.manager_id = ?")
                params.append(manager_id)
            if rag_status:
                clauses.append("hs.rag_status = ?")
                params.append(rag_status)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY hs.composite_score ASC"
            rows = conn.execute(query, params).fetchall()
            return [self._health_row_to_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_team_health_summary(self, manager_id: str) -> dict:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN hs.rag_status='on_track' THEN 1 ELSE 0 END) as on_track,
                    SUM(CASE WHEN hs.rag_status='needs_attention' THEN 1 ELSE 0 END)
                        as needs_attention,
                    SUM(CASE WHEN hs.rag_status='at_risk' THEN 1 ELSE 0 END) as at_risk,
                    AVG(hs.composite_score) as avg_score,
                    AVG(hs.goal_quality_score) as avg_goal_quality,
                    AVG(hs.feedback_score) as avg_feedback_coverage,
                    AVG(hs.checkin_score) as avg_checkin_recency
                FROM employee_health_scores hs
                JOIN employees e ON hs.employee_id = e.employee_id
                WHERE e.manager_id = ?
                """,
                (manager_id,),
            ).fetchone()
            if not row or not row["total"]:
                return {
                    "total": 0,
                    "on_track": 0,
                    "needs_attention": 0,
                    "at_risk": 0,
                    "avg_score": 0,
                    "avg_goal_quality": 0,
                    "avg_feedback_coverage": 0,
                    "avg_checkin_recency": 0,
                }
            return {
                "total": row["total"] or 0,
                "on_track": row["on_track"] or 0,
                "needs_attention": row["needs_attention"] or 0,
                "at_risk": row["at_risk"] or 0,
                "avg_score": round(row["avg_score"] or 0, 1),
                "avg_goal_quality": round(row["avg_goal_quality"] or 0, 1),
                "avg_feedback_coverage": round(row["avg_feedback_coverage"] or 0, 1),
                "avg_checkin_recency": round(row["avg_checkin_recency"] or 0, 1),
            }
        finally:
            conn.close()

    def count_health_scores(self) -> int:
        conn = get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM employee_health_scores").fetchone()[0]
        finally:
            conn.close()

    def get_latest_shared_feedback_snippet(self, employee_id: str, max_len: int = 60) -> str | None:
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT raw_text FROM feedback_entries
                WHERE employee_id = ? AND visibility = 'shared' AND is_draft = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (employee_id,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    SELECT raw_text FROM feedback_entries
                    WHERE employee_id = ? AND is_draft = 0
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (employee_id,),
                ).fetchone()
            if not row:
                return None
            text = (row["raw_text"] or "").strip()
            return text[:max_len] + ("…" if len(text) > max_len else "")
        finally:
            conn.close()

    # ── POLICY DOCUMENTS ───────────────────────────────────────────────

    def upsert_policy_doc(self, doc: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO policy_documents (
                    doc_id, filename, title, description, chunk_count,
                    status, uploaded_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(doc_id) DO UPDATE SET
                    filename=excluded.filename, title=excluded.title,
                    description=excluded.description, chunk_count=excluded.chunk_count,
                    status=excluded.status, updated_at=datetime('now')
                """,
                (
                    doc["doc_id"],
                    doc["filename"],
                    doc["title"],
                    doc.get("description", ""),
                    doc.get("chunk_count", 0),
                    doc.get("status", "active"),
                    doc.get(
                        "uploaded_at",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_policy_docs(self, status: str | None = None) -> list[dict]:
        conn = get_db()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM policy_documents WHERE status = ? ORDER BY uploaded_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM policy_documents ORDER BY uploaded_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_policy_doc_by_id(self, doc_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM policy_documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_policy_doc_by_filename(self, filename: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM policy_documents WHERE filename = ?", (filename,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_policy_doc(self, doc_id: str, updates: dict) -> dict | None:
        existing = self.get_policy_doc_by_id(doc_id)
        if not existing:
            return None
        conn = get_db()
        try:
            title = updates.get("title", existing["title"])
            description = updates.get("description", existing["description"])
            conn.execute(
                """
                UPDATE policy_documents
                SET title=?, description=?, updated_at=datetime('now')
                WHERE doc_id=?
                """,
                (title, description, doc_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_policy_doc_by_id(doc_id)

    def delete_policy_doc(self, doc_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "DELETE FROM policy_documents WHERE doc_id = ?", (doc_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def archive_policy_doc(self, doc_id: str) -> dict | None:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE policy_documents SET status='archived', updated_at=datetime('now') WHERE doc_id=?",
                (doc_id,),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_policy_doc_by_id(doc_id)

    def activate_policy_doc(self, doc_id: str) -> dict | None:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE policy_documents SET status='active', updated_at=datetime('now') WHERE doc_id=?",
                (doc_id,),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_policy_doc_by_id(doc_id)

    def count_policy_docs(self, status: str = "active") -> int:
        conn = get_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM policy_documents WHERE status = ?", (status,)
            ).fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def new_okr_id() -> str:
        return f"okr_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def new_milestone_id() -> str:
        return f"ms_{uuid.uuid4().hex[:8]}"

    # ── AGENT ACTIVITY ─────────────────────────────────────────────────

    def insert_agent_activity(self, row: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO agent_activity (
                    id, agent, employee_id, user_id, workflow_id, status, summary,
                    duration_ms, steps_json, confidence_level, confidence_score,
                    confidence_reason, rationale_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["agent"],
                    row.get("employee_id"),
                    row.get("user_id"),
                    row.get("workflow_id"),
                    row.get("status", "completed"),
                    row.get("summary", ""),
                    row.get("duration_ms", 0),
                    row.get("steps_json", "[]"),
                    row.get("confidence_level"),
                    row.get("confidence_score"),
                    row.get("confidence_reason"),
                    row.get("rationale_json"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _parse_agent_activity_row(self, row) -> dict:
        item = dict(row)
        try:
            item["steps"] = json.loads(item.pop("steps_json", "[]") or "[]")
        except json.JSONDecodeError:
            item["steps"] = []
        rationale_raw = item.pop("rationale_json", None)
        if rationale_raw:
            try:
                item["rationale"] = json.loads(rationale_raw)
            except json.JSONDecodeError:
                item["rationale"] = None
        else:
            item["rationale"] = None
        return item

    def list_agent_activity(
        self, employee_id: str | None = None, limit: int = 20
    ) -> list[dict]:
        conn = get_db()
        try:
            if employee_id:
                rows = conn.execute(
                    """
                    SELECT * FROM agent_activity
                    WHERE employee_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (employee_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM agent_activity
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [self._parse_agent_activity_row(row) for row in rows]
        finally:
            conn.close()

    def list_agent_activity_by_workflow(self, workflow_id: str) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT * FROM agent_activity
                WHERE workflow_id = ?
                ORDER BY created_at ASC
                """,
                (workflow_id,),
            ).fetchall()
            return [self._parse_agent_activity_row(row) for row in rows]
        finally:
            conn.close()

    def touch_workflow_run(
        self,
        workflow_id: str,
        employee_id: str | None,
        user_id: str | None,
    ) -> None:
        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT 1 FROM workflow_runs WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE workflow_runs
                    SET updated_at = datetime('now'),
                        trace_count = trace_count + 1,
                        employee_id = COALESCE(employee_id, ?),
                        user_id = COALESCE(user_id, ?)
                    WHERE workflow_id = ?
                    """,
                    (employee_id, user_id, workflow_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO workflow_runs (
                        workflow_id, employee_id, user_id, trace_count
                    ) VALUES (?, ?, ?, 1)
                    """,
                    (workflow_id, employee_id, user_id),
                )
            conn.commit()
        finally:
            conn.close()

    def list_workflow_runs(
        self, employee_id: str | None = None, limit: int = 10
    ) -> list[dict]:
        conn = get_db()
        try:
            if employee_id:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_runs
                    WHERE employee_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (employee_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_runs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_workflow_run(self, workflow_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_transparency_coverage(self, employee_id: str | None = None) -> dict:
        conn = get_db()
        try:
            params: list = []
            where = "WHERE created_at >= datetime('now', '-7 days')"
            if employee_id:
                where += " AND employee_id = ?"
                params.append(employee_id)
            rows = conn.execute(
                f"""
                SELECT agent,
                       COUNT(*) AS total,
                       SUM(CASE WHEN confidence_level IS NOT NULL THEN 1 ELSE 0 END) AS with_confidence,
                       SUM(CASE WHEN rationale_json IS NOT NULL THEN 1 ELSE 0 END) AS with_rationale
                FROM agent_activity
                {where}
                GROUP BY agent
                """,
                params,
            ).fetchall()
            agents = []
            total_runs = 0
            total_conf = 0
            total_rat = 0
            for row in rows:
                total = int(row["total"])
                with_conf = int(row["with_confidence"] or 0)
                with_rat = int(row["with_rationale"] or 0)
                total_runs += total
                total_conf += with_conf
                total_rat += with_rat
                agents.append(
                    {
                        "agent": row["agent"],
                        "total_runs": total,
                        "with_confidence": with_conf,
                        "with_rationale": with_rat,
                        "confidence_pct": round(with_conf / total * 100) if total else 0,
                        "rationale_pct": round(with_rat / total * 100) if total else 0,
                    }
                )
            return {
                "window_days": 7,
                "employee_id": employee_id,
                "total_runs": total_runs,
                "confidence_coverage_pct": round(total_conf / total_runs * 100)
                if total_runs
                else 0,
                "rationale_coverage_pct": round(total_rat / total_runs * 100)
                if total_runs
                else 0,
                "agents": agents,
            }
        finally:
            conn.close()

    # ── EMPLOYEE ACHIEVEMENTS ────────────────────────────────────────

    @staticmethod
    def new_achievement_id() -> str:
        return f"ach_{uuid.uuid4().hex[:10]}"

    def count_achievements(self) -> int:
        conn = get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM employee_achievements").fetchone()[0]
        finally:
            conn.close()

    def realign_seed_achievements_cycle(self, review_cycle: str) -> int:
        conn = get_db()
        try:
            cur = conn.execute(
                """
                UPDATE employee_achievements
                SET review_cycle = ?, updated_at = datetime('now')
                WHERE source = 'seed' AND (review_cycle IS NULL OR review_cycle != ?)
                """,
                (review_cycle, review_cycle),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def _achievement_row_to_dict(self, row) -> dict:
        return dict(row) if row else {}

    def list_achievements(
        self,
        employee_id: str,
        review_cycle: str | None = None,
        include_private: bool = True,
    ) -> list[dict]:
        conn = get_db()
        try:
            if review_cycle:
                rows = conn.execute(
                    """
                    SELECT * FROM employee_achievements
                    WHERE employee_id = ?
                      AND (review_cycle IS NULL OR review_cycle = ? OR review_cycle = '')
                    ORDER BY achieved_at DESC, created_at DESC
                    """,
                    (employee_id, review_cycle),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM employee_achievements
                    WHERE employee_id = ?
                    ORDER BY achieved_at DESC, created_at DESC
                    """,
                    (employee_id,),
                ).fetchall()
            items = [self._achievement_row_to_dict(r) for r in rows]
            if include_private:
                return items
            return [a for a in items if a.get("visibility") != "self"]
        finally:
            conn.close()

    def get_achievement(self, achievement_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM employee_achievements WHERE achievement_id = ?",
                (achievement_id,),
            ).fetchone()
            return self._achievement_row_to_dict(row) if row else None
        finally:
            conn.close()

    def insert_achievement(self, row: dict) -> dict:
        conn = get_db()
        aid = row.get("achievement_id") or self.new_achievement_id()
        try:
            conn.execute(
                """
                INSERT INTO employee_achievements (
                    achievement_id, employee_id, type, title, description,
                    issuer_or_context, achieved_at, review_cycle,
                    linked_milestone_id, visibility, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    row["employee_id"],
                    row["type"],
                    row["title"],
                    row.get("description", ""),
                    row.get("issuer_or_context", ""),
                    row.get("achieved_at"),
                    row.get("review_cycle"),
                    row.get("linked_milestone_id"),
                    row.get("visibility", "manager"),
                    row.get("source", "manual"),
                ),
            )
            conn.commit()
            return self.get_achievement(aid) or {**row, "achievement_id": aid}
        finally:
            conn.close()

    def update_achievement(self, achievement_id: str, updates: dict) -> dict | None:
        allowed = {
            "type",
            "title",
            "description",
            "issuer_or_context",
            "achieved_at",
            "review_cycle",
            "linked_milestone_id",
            "visibility",
        }
        parts = []
        values: list = []
        for key, val in updates.items():
            if key in allowed and val is not None:
                parts.append(f"{key} = ?")
                values.append(val)
        if not parts:
            return self.get_achievement(achievement_id)
        parts.append("updated_at = datetime('now')")
        values.append(achievement_id)
        conn = get_db()
        try:
            conn.execute(
                f"UPDATE employee_achievements SET {', '.join(parts)} WHERE achievement_id = ?",
                values,
            )
            conn.commit()
            return self.get_achievement(achievement_id)
        finally:
            conn.close()

    def delete_achievement(self, achievement_id: str) -> bool:
        conn = get_db()
        try:
            cur = conn.execute(
                "DELETE FROM employee_achievements WHERE achievement_id = ?",
                (achievement_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── AUTH ───────────────────────────────────────────────────────────

    def upsert_app_user(self, user: dict) -> None:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO app_users (user_id, employee_id, role, display_name, pin)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    employee_id=excluded.employee_id,
                    role=excluded.role,
                    display_name=excluded.display_name,
                    pin=excluded.pin
                """,
                (
                    user["user_id"],
                    user.get("employee_id"),
                    user["role"],
                    user["display_name"],
                    user["pin"],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def count_app_users(self) -> int:
        conn = get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        finally:
            conn.close()

    def migrate_legacy_manager_users(self) -> None:
        """Convert stored manager role to employee; manager is derived from org data."""
        conn = get_db()
        try:
            conn.execute(
                "UPDATE app_users SET role = 'employee' WHERE role = 'manager'"
            )
            conn.commit()
        finally:
            conn.close()

    def list_all_employees(self) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_employees_for_login(self) -> list[dict]:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT e.employee_id, e.name, e.job_title, e.department, e.sub_department,
                       (SELECT COUNT(*) FROM employees r WHERE r.manager_id = e.employee_id) AS report_count
                FROM employees e
                ORDER BY e.name
                """
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["is_manager"] = item.pop("report_count", 0) > 0
                results.append(item)
            return results
        finally:
            conn.close()

    def get_app_user_by_id(self, user_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM app_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def authenticate_user(self, user_id: str, pin: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM app_users WHERE user_id = ? AND pin = ?",
                (user_id, pin),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_auth_session(self, token: str, user_id: str, expires_at: str) -> None:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO auth_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def get_auth_session(self, token: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM auth_sessions WHERE token = ?", (token,)
            ).fetchone()
            if not row:
                return None
            session = dict(row)
            expires = datetime.fromisoformat(session["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
                conn.commit()
                return None
            return session
        finally:
            conn.close()

    def delete_auth_session(self, token: str) -> None:
        conn = get_db()
        try:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
