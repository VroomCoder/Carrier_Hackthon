import os

from dotenv import load_dotenv

load_dotenv()
# Disable Hugging Face xet downloads (avoids 403 on cas-server.xethub.hf.co)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import (
    CurrentUser,
    authenticate_admin,
    authenticate_employee,
    build_current_user,
    can_access_employee,
    create_session_token,
    get_accessible_employee_ids,
    get_current_user,
    require_admin,
    require_manager_or_admin,
    seed_app_users,
    session_expiry_iso,
    user_payload,
)
from agents.continuous_feedback import router as continuous_feedback_router
from agents.calibrator import router as calibrator_router
from agents.agent_activity import router as agent_activity_router
from agents.coach import router as coach_router
from agent_trace import finish_trace, start_trace
from agents.feedback_reviews import router as feedback_reviews_router
from agents.goals import router as goals_router
from agents.okr_assignments import router as okr_assignments_router
from agents.synthesiser import router as synthesiser_router
from agents.team_health import router as team_health_router
from agents.transparency import router as transparency_router
from agents.achievements import router as achievements_router
from db.database import init_db
from db.sqlite_repo import SqliteRepo, compute_node_fields
from db.vector_store import VectorStore
from ingest_employees import ingest_employees, seed_org_and_okrs
from ingest_policy import ingest_policies_from_directory
from ollama_client import BASE_URL, MODEL, check_llm_status, probe_llm_generation
from seed_achievements import seed_employee_achievements
from seed_feedback import seed_feedback_entries
from scheduler import start_scheduler, stop_scheduler
from workflow_context import set_workflow_id

db = SqliteRepo()
vs = VectorStore(os.getenv("CHROMA_PERSIST_PATH", "./chroma_db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    csv_path = os.getenv("EMPLOYEES_CSV_PATH", "./data/employees.csv")
    if db.count_employees() == 0 and os.path.exists(csv_path):
        n = ingest_employees(csv_path, db)
        print(f"Employees ingested: {n}")

    result = seed_org_and_okrs(db, vs)
    print(f"OKRs seeded: {result['okrs_seeded']}")
    print(f"Org nodes seeded: {result['nodes_seeded']}")

    okrs = db.get_active_okr_texts()
    n = vs.sync_all_okrs(okrs)
    print(f"OKR embeddings synced: {n}")

    milestones = db.get_all_milestones_for_sync()
    for m in milestones:
        vs.sync_milestone(m)

    policies_dir = os.getenv("POLICIES_DIR", "./data/policies")
    n = ingest_policies_from_directory(policies_dir, db, vs)
    if n > 0:
        print(f"Policy documents auto-ingested: {n}")

    n_users = seed_app_users(db)
    if n_users > 0:
        print(f"Demo users seeded: {n_users}")

    n_fb = seed_feedback_entries(db, vs)
    if n_fb > 0:
        print(f"Feedback entries seeded: {n_fb}")

    n_ach = seed_employee_achievements(db)
    if n_ach > 0:
        print(f"Employee achievements seeded: {n_ach}")

    existing_feedback = db.get_all_entries_for_sync()
    n = vs.sync_all_feedback(existing_feedback)
    print(f"Feedback embeddings synced: {n}")

    print(f"Policy chunks indexed: {vs.count_policy_chunks()}")

    print("Computing initial employee health scores...")
    from agents.health_scoring_agent import run_health_scoring_for_all

    health_result = await run_health_scoring_for_all(db)
    print(
        f"Health scores computed: {health_result['scored']} employees, "
        f"{health_result['at_risk']} at risk"
    )

    probe = await probe_llm_generation()
    if probe.get("detail"):
        print(f"LLM probe: {probe['detail']}")
    elif probe.get("ok"):
        print("LLM probe: OK")

    start_scheduler(db, vs)

    yield

    stop_scheduler()


app = FastAPI(title="NexaCore Growth Coach", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def workflow_middleware(request, call_next):
    wid = request.headers.get("X-Workflow-Id")
    set_workflow_id(wid)
    try:
        return await call_next(request)
    finally:
        set_workflow_id(None)


app.include_router(continuous_feedback_router, prefix="/api")
app.include_router(calibrator_router, prefix="/api")
app.include_router(agent_activity_router, prefix="/api")
app.include_router(okr_assignments_router, prefix="/api")
app.include_router(goals_router, prefix="/api")
app.include_router(synthesiser_router, prefix="/api")
app.include_router(feedback_reviews_router, prefix="/api")
app.include_router(coach_router, prefix="/api")
app.include_router(team_health_router, prefix="/api")
app.include_router(transparency_router, prefix="/api")
app.include_router(achievements_router, prefix="/api")


def get_db_repo() -> SqliteRepo:
    return db


def get_vs() -> VectorStore:
    return vs


@app.get("/")
@app.get("/ui")
def root():
    return {
        "message": "NexaCore Growth Coach API is running.",
        "ui": "Open the app at http://localhost:5173 (start frontend: cd frontend && npm run dev)",
        "health": "/api/health",
        "docs": "/docs",
    }


# ── HEALTH ─────────────────────────────────────────────────────────

@app.get("/api/health")
def health(vs_dep: VectorStore = Depends(get_vs)):
    llm = check_llm_status()
    return {
        "status": "ok",
        "employees_indexed": db.count_employees(),
        "active_okrs": db.count_okrs("active"),
        "active_org_nodes": db.count_org_nodes("active"),
        "policy_docs": db.count_policy_docs("active"),
        "policy_chunks": vs_dep.count_policy_chunks(),
        "llm_provider": llm["llm_provider"],
        "llm_ok": llm["llm_ok"],
        "llm_model_ready": llm["model_ready"],
        "llm_detail": llm.get("detail"),
        "model": MODEL,
        "llm_url": BASE_URL,
        # backward compatibility for older frontend checks
        "ollama_url": BASE_URL,
        "ollama_ok": llm["llm_ok"],
        "ollama_model_ready": llm["model_ready"],
        "ollama_models": llm.get("models", []),
    }


# ── AUTH ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    login_type: str
    pin: str
    employee_id: str | None = None


def _auth_session_response(repo: SqliteRepo, user: dict, token: str) -> dict:
    current = build_current_user(repo, user)
    employee = None
    direct_reports = []
    if current.employee_id:
        employee = repo.get_employee_by_id(current.employee_id)
        if current.is_manager:
            direct_reports = repo.get_direct_reports(current.employee_id)
    return {
        "token": token,
        "user": user_payload(current),
        "employee": employee,
        "direct_reports": direct_reports,
        "accessible_employee_ids": get_accessible_employee_ids(repo, current),
    }


@app.get("/api/auth/login-options")
def login_options():
    """Public login types for the sign-in screen."""
    return {"login_types": ["admin", "employee"]}


@app.get("/api/auth/employees-for-login")
def employees_for_login(repo: SqliteRepo = Depends(get_db_repo)):
    """Public employee picker for employee sign-in."""
    return repo.list_employees_for_login()


@app.post("/api/auth/login")
def login(body: LoginRequest, repo: SqliteRepo = Depends(get_db_repo)):
    login_type = body.login_type.strip().lower()
    if login_type == "admin":
        user = authenticate_admin(repo, body.pin)
    elif login_type == "employee":
        if not body.employee_id:
            raise HTTPException(status_code=400, detail="employee_id is required for employee login")
        user = authenticate_employee(repo, body.employee_id, body.pin)
    else:
        raise HTTPException(status_code=400, detail="login_type must be 'admin' or 'employee'")

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session_token()
    repo.create_auth_session(token, user["user_id"], session_expiry_iso())
    return _auth_session_response(repo, user, token)


@app.get("/api/auth/me")
def auth_me(
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    employee = None
    direct_reports = []
    if user.employee_id:
        employee = repo.get_employee_by_id(user.employee_id)
        if user.is_manager:
            direct_reports = repo.get_direct_reports(user.employee_id)
    return {
        "user": user_payload(user),
        "employee": employee,
        "accessible_employee_ids": get_accessible_employee_ids(repo, user),
        "direct_reports": direct_reports,
    }


@app.post("/api/auth/logout")
def logout(
    user: CurrentUser = Depends(get_current_user),
    authorization: Annotated[str | None, Header()] = None,
    repo: SqliteRepo = Depends(get_db_repo),
):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        repo.delete_auth_session(token)
    return {"logged_out": True}


# ── EMPLOYEES ──────────────────────────────────────────────────────

def _employee_summary(e: dict) -> dict:
    return {
        "employee_id": e["employee_id"],
        "name": e["name"],
        "job_title": e.get("job_title", ""),
        "department": e.get("department", ""),
        "sub_department": e.get("sub_department", ""),
        "grade": e.get("grade", ""),
        "location": e.get("location", ""),
        "work_mode": e.get("work_mode", ""),
    }


@app.get("/api/employees")
def search_employees(
    q: str = "",
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_manager_or_admin(user)
    allowed = get_accessible_employee_ids(repo, user)
    if q.strip():
        results = repo.search_employees(q, limit=limit, allowed_ids=allowed)
    elif allowed is None:
        results = repo.list_all_employees()
    else:
        results = repo.get_employees_by_ids(allowed)
    return [_employee_summary(e) for e in results]


@app.get("/api/employees/{employee_id}")
def get_employee(
    employee_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    emp = repo.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@app.get("/api/employees/{employee_id}/milestones")
def get_employee_milestones(
    employee_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    if not can_access_employee(repo, user, employee_id):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    milestones = repo.get_milestones_by_employee(employee_id)
    return [
        {
            "id": m["id"],
            "employee_id": m["employee_id"],
            "raw_goal": m["raw_goal"],
            "smart_goal": m.get("smart_goal"),
            "overall_score": m.get("overall_score", 0),
            "status": m.get("status", "needs_work"),
            "seniority_tier": m.get("seniority_tier", ""),
            "created_at": m.get("created_at", ""),
            "updated_at": m.get("updated_at", ""),
            "employee_self_assessment": m.get("employee_self_assessment", ""),
            "self_assessment_updated_at": m.get("self_assessment_updated_at"),
            "source_okr_id": m.get("source_okr_id"),
            "suggested_by": m.get("suggested_by"),
            "manager_suggestion": m.get("manager_suggestion", ""),
            "linked_okr_id": m.get("linked_okr_id"),
        }
        for m in milestones
    ]


# ── OKRs ───────────────────────────────────────────────────────────

class OKRCreate(BaseModel):
    title: str
    description: str
    category: str
    owner: str = ""
    cycle: str = "FY2025"
    status: str = "active"


class OKRUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    owner: str | None = None
    cycle: str | None = None
    status: str | None = None


class OKRBulkRequest(BaseModel):
    okrs: list[dict]
    replace_existing: bool = False


@app.get("/api/okrs")
def list_okrs(
    status: str | None = None,
    department: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.get_all_okrs(status=status, department=department)


@app.post("/api/okrs")
def create_okr(
    body: OKRCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    okr_id = SqliteRepo.new_okr_id()
    okr = {"okr_id": okr_id, **body.model_dump()}
    repo.upsert_okr(okr)
    vector_store.sync_okr(okr)
    return repo.get_okr_by_id(okr_id)


@app.put("/api/okrs/{okr_id}")
def update_okr(
    okr_id: str,
    body: OKRUpdate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = repo.update_okr(okr_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="OKR not found")
    vector_store.sync_okr(result)
    return result


@app.delete("/api/okrs/{okr_id}")
def delete_okr(
    okr_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    if not repo.delete_okr(okr_id):
        raise HTTPException(status_code=404, detail="OKR not found")
    vector_store.remove_okr(okr_id)
    return {"deleted": True, "okr_id": okr_id}


@app.post("/api/okrs/{okr_id}/archive")
def archive_okr(
    okr_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    if not repo.archive_okr(okr_id):
        raise HTTPException(status_code=404, detail="OKR not found")
    okr = repo.get_okr_by_id(okr_id)
    if okr:
        vector_store.sync_okr(okr)
    return okr


@app.post("/api/okrs/{okr_id}/activate")
def activate_okr(
    okr_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    if not repo.activate_okr(okr_id):
        raise HTTPException(status_code=404, detail="OKR not found")
    okr = repo.get_okr_by_id(okr_id)
    if okr:
        vector_store.sync_okr(okr)
    return okr


@app.post("/api/okrs/bulk")
def bulk_okrs(
    body: OKRBulkRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    require_admin(user)
    if body.replace_existing:
        existing = repo.get_all_okrs()
        for okr in existing:
            repo.delete_okr(okr["okr_id"])
            vector_store.remove_okr(okr["okr_id"])

    count = 0
    for item in body.okrs:
        okr_id = item.get("okr_id") or SqliteRepo.new_okr_id()
        okr = {
            "okr_id": okr_id,
            "title": item["title"],
            "description": item["description"],
            "category": item.get("category", "Other"),
            "owner": item.get("owner", ""),
            "cycle": item.get("cycle", "FY2025"),
            "status": item.get("status", "active"),
        }
        repo.upsert_okr(okr)
        vector_store.sync_okr(okr)
        count += 1
    return {"imported": count}


@app.get("/api/okrs/search")
def search_okrs(
    q: str,
    n: int = 3,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    start_trace("okr_lookup", user.employee_id, user.user_id)
    results = vector_store.search_okrs(q, n_results=n)
    finish_trace(
        repo,
        summary=f'OKR search "{q[:60]}" — {len(results)} result(s)',
    )
    return {"results": results, "query": q}


# ── ORG ────────────────────────────────────────────────────────────

class OrgNodeCreate(BaseModel):
    department: str
    business_unit: str
    designation: str
    status: str = "active"


class OrgBulkRequest(BaseModel):
    nodes: list[dict]
    replace_existing: bool = False


@app.get("/api/org/departments")
def org_departments(
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.get_all_departments()


@app.get("/api/org/business-units")
def org_business_units(
    department: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.get_business_units(department)


@app.get("/api/org/designations")
def org_designations(
    department: str,
    business_unit: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.get_designations(department, business_unit)


@app.get("/api/org/validate")
def org_validate(
    department: str,
    business_unit: str,
    designation: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return {"valid": repo.validate_org_node(department, business_unit, designation)}


@app.get("/api/org/role-context")
def org_role_context(
    department: str,
    business_unit: str,
    designation: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    node = repo.get_org_node(department, business_unit, designation)
    if not node:
        computed = compute_node_fields(department, business_unit, designation)
        return {
            "designation": designation,
            "department": department,
            "business_unit": business_unit,
            "seniority_tier": computed["seniority_tier"],
            "focus_description": computed["focus_description"],
            "okr_categories": computed["okr_categories"].split(","),
            "valid": False,
        }
    return {
        "designation": node["designation"],
        "department": node["department"],
        "business_unit": node["business_unit"],
        "seniority_tier": node["seniority_tier"],
        "focus_description": node["focus_description"],
        "okr_categories": node["okr_categories"].split(","),
        "valid": True,
    }


@app.get("/api/org/nodes")
def org_nodes(
    status: str | None = None,
    department: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.get_all_org_nodes(status=status, department=department)


@app.get("/api/org/nodes/search")
def org_nodes_search(
    q: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    return repo.search_org_nodes(q)


@app.post("/api/org/nodes")
def create_org_node(
    body: OrgNodeCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    repo.upsert_org_node(body.model_dump())
    node = repo.get_org_node(body.department, body.business_unit, body.designation)
    return node


@app.put("/api/org/nodes/{node_id}")
def update_org_node(
    node_id: str,
    body: OrgNodeCreate,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    existing_nodes = repo.get_all_org_nodes()
    existing = next((n for n in existing_nodes if n["node_id"] == node_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Node not found")
    if (
        existing["department"] != body.department
        or existing["business_unit"] != body.business_unit
        or existing["designation"] != body.designation
    ):
        repo.delete_org_node(node_id)
    repo.upsert_org_node(body.model_dump())
    return repo.get_org_node(body.department, body.business_unit, body.designation)


@app.delete("/api/org/nodes/{node_id}")
def delete_org_node(
    node_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    if not repo.delete_org_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"deleted": True, "node_id": node_id}


@app.post("/api/org/nodes/{node_id}/archive")
def archive_org_node(
    node_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    if not repo.archive_org_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    nodes = repo.get_all_org_nodes()
    return next((n for n in nodes if n["node_id"] == node_id), None)


@app.post("/api/org/nodes/{node_id}/activate")
def activate_org_node(
    node_id: str,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    if not repo.activate_org_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    nodes = repo.get_all_org_nodes()
    return next((n for n in nodes if n["node_id"] == node_id), None)


@app.post("/api/org/nodes/bulk")
def bulk_org_nodes(
    body: OrgBulkRequest,
    user: CurrentUser = Depends(get_current_user),
    repo: SqliteRepo = Depends(get_db_repo),
):
    require_admin(user)
    if body.replace_existing:
        for node in repo.get_all_org_nodes():
            repo.delete_org_node(node["node_id"])
    count = repo.bulk_upsert_org_nodes(body.nodes)
    return {"imported": count}


