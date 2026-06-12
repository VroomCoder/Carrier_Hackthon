import pandas as pd

SEED_OKRS = [
    {
        "okr_id": "okr_seed_001",
        "title": "Platform reliability",
        "description": "Achieve 95% platform uptime and reduce P1 incidents by 40% through proactive monitoring and engineering excellence.",
        "category": "Engineering",
        "owner": "CTO",
        "cycle": "FY2025",
        "status": "active",
    },
    {
        "okr_id": "okr_seed_002",
        "title": "Enterprise revenue growth",
        "description": "Grow enterprise ARR by 30% by expanding key accounts and improving sales velocity through structured account planning.",
        "category": "Sales",
        "owner": "VP Sales",
        "cycle": "FY2025",
        "status": "active",
    },
    {
        "okr_id": "okr_seed_003",
        "title": "Manager effectiveness & retention",
        "description": "Reduce employee attrition to below 8% by improving manager effectiveness, career development pathways, and compensation equity.",
        "category": "People",
        "owner": "CHRO",
        "cycle": "FY2025",
        "status": "active",
    },
    {
        "okr_id": "okr_seed_004",
        "title": "Product velocity",
        "description": "Launch three new product capabilities per quarter with 80% feature adoption within 60 days of release.",
        "category": "Product",
        "owner": "CPO",
        "cycle": "FY2025",
        "status": "active",
    },
    {
        "okr_id": "okr_seed_005",
        "title": "Security certification",
        "description": "Achieve ISO 27001 certification and zero critical security incidents by Q4 2025.",
        "category": "Security",
        "owner": "CISO",
        "cycle": "FY2025",
        "status": "active",
    },
    {
        "okr_id": "okr_seed_006",
        "title": "Customer onboarding speed",
        "description": "Reduce customer onboarding time from 45 days to 20 days through process automation and self-serve tooling.",
        "category": "Customer Success",
        "owner": "VP CS",
        "cycle": "FY2025",
        "status": "active",
    },
]

SEED_ORG_HIERARCHY: dict[str, dict[str, list[str]]] = {
    "Customer Success": {
        "Account Management": ["CS Associate", "Customer Success Manager", "Senior CSM", "CS Director"],
        "Renewals": ["CS Associate", "Customer Success Manager", "Senior CSM", "CS Director"],
        "Support Engineering": ["Customer Success Manager", "Senior CSM", "CS Director"],
        "Onboarding": ["CS Associate", "Customer Success Manager", "Senior CSM", "CS Director"],
    },
    "Data & Analytics": {
        "Data Engineering": ["Data Analyst", "Senior Data Analyst", "Data Scientist", "Lead Data Scientist", "Head of Data"],
        "Data Governance": ["Data Analyst", "Senior Data Analyst", "Data Scientist", "Lead Data Scientist", "Head of Data"],
        "Business Intelligence": ["Data Analyst", "Senior Data Analyst", "Data Scientist", "Lead Data Scientist", "Head of Data"],
        "ML & AI": ["Data Analyst", "Senior Data Analyst", "Data Scientist", "Lead Data Scientist", "Head of Data"],
    },
    "Engineering": {
        "Platform Engineering": ["Associate Engineer", "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer"],
        "QA & Testing": ["Associate Engineer", "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer"],
        "Mobile & Web": ["Associate Engineer", "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer"],
        "Cloud Infrastructure": ["Associate Engineer", "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer"],
        "DevOps & SRE": ["Associate Engineer", "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Principal Engineer"],
    },
    "Finance": {
        "Tax & Compliance": ["Finance Analyst", "Senior Finance Analyst", "Finance Manager", "Senior Finance Manager"],
        "Treasury": ["Finance Analyst", "Senior Finance Analyst", "Finance Manager", "Senior Finance Manager"],
        "FP&A": ["Finance Analyst", "Senior Finance Analyst", "Finance Manager", "Senior Finance Manager"],
        "Accounting": ["Finance Analyst", "Senior Finance Analyst", "Finance Manager", "Senior Finance Manager"],
    },
    "HR": {
        "HR Business Partnering": ["HR Coordinator", "HR Generalist", "Senior HR Specialist", "HR Manager"],
        "Talent Acquisition": ["HR Coordinator", "HR Generalist", "Senior HR Specialist", "HR Manager"],
        "People Operations": ["HR Coordinator", "HR Generalist", "Senior HR Specialist", "HR Manager"],
        "L&D": ["HR Coordinator", "HR Generalist", "Senior HR Specialist", "HR Manager"],
    },
    "IT Support": {
        "IT Operations": ["IT Support Analyst", "IT Support Engineer", "Senior IT Engineer", "IT Manager"],
        "Security Operations": ["IT Support Analyst", "IT Support Engineer", "Senior IT Engineer", "IT Manager"],
        "End-User Computing": ["IT Support Analyst", "IT Support Engineer", "Senior IT Engineer", "IT Manager"],
    },
    "Legal": {
        "Employment Law": ["Legal Analyst", "Associate Counsel", "Senior Counsel", "Legal Director"],
        "Corporate Legal": ["Legal Analyst", "Associate Counsel", "Senior Counsel", "Legal Director"],
        "IP & Compliance": ["Legal Analyst", "Associate Counsel", "Senior Counsel", "Legal Director"],
    },
    "Marketing": {
        "Demand Generation": ["Marketing Coordinator", "Marketing Specialist", "Senior Marketing Manager", "Marketing Director"],
        "Brand & Communications": ["Marketing Coordinator", "Marketing Specialist", "Senior Marketing Manager", "Marketing Director"],
        "Content & SEO": ["Marketing Coordinator", "Marketing Specialist", "Senior Marketing Manager", "Marketing Director"],
        "Product Marketing": ["Marketing Coordinator", "Marketing Specialist", "Senior Marketing Manager", "Marketing Director"],
    },
    "Operations": {
        "Procurement": ["Operations Analyst", "Operations Specialist", "Senior Operations Mgr", "Operations Director"],
        "Business Operations": ["Operations Analyst", "Operations Specialist", "Senior Operations Mgr", "Operations Director"],
        "Supply Chain": ["Operations Analyst", "Operations Specialist", "Senior Operations Mgr", "Operations Director"],
        "Facilities": ["Operations Analyst", "Operations Specialist", "Senior Operations Mgr", "Operations Director"],
    },
    "Product": {
        "Core Product": ["Associate PM", "Product Manager", "Senior Product Manager", "Principal PM", "VP of Product"],
        "Platform": ["Associate PM", "Product Manager", "Senior Product Manager", "Principal PM", "VP of Product"],
        "Analytics": ["Associate PM", "Product Manager", "Senior Product Manager", "Principal PM", "VP of Product"],
        "Growth": ["Associate PM", "Product Manager", "Senior Product Manager", "Principal PM", "VP of Product"],
    },
    "Sales": {
        "Enterprise Sales": ["Sales Development Rep", "Account Executive", "Senior Account Executive", "Sales Manager", "Sales Director"],
        "SMB Sales": ["Sales Development Rep", "Account Executive", "Senior Account Executive", "Sales Manager", "Sales Director"],
        "Sales Operations": ["Sales Development Rep", "Account Executive", "Senior Account Executive", "Sales Manager", "Sales Director"],
        "Presales": ["Sales Development Rep", "Account Executive", "Senior Account Executive", "Sales Manager", "Sales Director"],
    },
}

COLUMNS = [
    "employee_id", "name", "email", "department", "sub_department",
    "job_title", "grade", "manager_id", "manager_name", "location",
    "join_date", "employment_type", "leave_balance", "work_mode",
    "phone_extension",
]


def build_seed_org_nodes() -> list[dict]:
    nodes: list[dict] = []
    for department, bus in SEED_ORG_HIERARCHY.items():
        for business_unit, designations in bus.items():
            for designation in designations:
                nodes.append(
                    {
                        "department": department,
                        "business_unit": business_unit,
                        "designation": designation,
                        "status": "active",
                    }
                )
    return nodes


SEED_ORG_NODES = build_seed_org_nodes()


def parse_csv(csv_path: str) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        first_line = f.readline()
    sep = "\t" if "\t" in first_line else ","
    has_header = not first_line.strip().startswith("NX")

    if has_header:
        df = pd.read_csv(csv_path, sep=sep)
    else:
        df = pd.read_csv(csv_path, sep=sep, header=None, names=COLUMNS)

    df = df.where(pd.notnull(df), None)
    records = df.to_dict(orient="records")

    for rec in records:
        for key in ("manager_id", "manager_name"):
            if rec.get(key) in ("", "nan", None):
                rec[key] = None
        if rec.get("leave_balance") is not None:
            try:
                rec["leave_balance"] = int(rec["leave_balance"])
            except (ValueError, TypeError):
                rec["leave_balance"] = None

    return records


def ingest_employees(csv_path: str, db_repo) -> int:
    employees = parse_csv(csv_path)
    for emp in employees:
        db_repo.upsert_employee(emp)
    return len(employees)


def seed_org_and_okrs(db_repo, vector_store) -> dict:
    okrs_seeded = 0
    nodes_seeded = 0

    if db_repo.count_okrs() == 0:
        for okr in SEED_OKRS:
            db_repo.upsert_okr(okr)
        okrs_seeded = len(SEED_OKRS)

    if db_repo.count_org_nodes() == 0:
        db_repo.bulk_upsert_org_nodes(SEED_ORG_NODES)
        nodes_seeded = len(SEED_ORG_NODES)

    okrs = db_repo.get_active_okr_texts()
    vector_store.sync_all_okrs(okrs)

    return {"okrs_seeded": okrs_seeded, "nodes_seeded": nodes_seeded}
