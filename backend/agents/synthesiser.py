import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_trace import finish_trace, get_trace, start_trace
from agents.bias_scan import high_severity_passages
from agents.synthesis_core import run_synthesis
from agents.feedback_reviews import _can_write_feedback_for_employee
from auth import CurrentUser, get_current_user, require_employee_access
from confidence_utils import objectivity_to_confidence
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from feedback_cycle import current_review_cycle

router = APIRouter()


class SynthesiseRequest(BaseModel):
    feedback: str
    employee_id: str | None = None
    use_continuous_feedback: bool = False
    review_cycle: str | None = None
    review_type: str = "mid_year"


class FinaliseRequest(BaseModel):
    synthesis_id: str
    acknowledged_flags: list[str] = []


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


def _synthesis_response(row: dict) -> dict:
    return {
        "synthesis_id": row["synthesis_id"],
        "employee_id": row["employee_id"],
        "commentary": row.get("commentary") or "",
        "score": row.get("objectivity_score") or 0,
        "flags": row.get("flags") or [],
        "policy_references": [],
        "gate_blocked": bool(row.get("gate_blocked")),
        "gate_reason": row.get("gate_reason"),
        "finalised_at": row.get("finalised_at"),
        "acknowledged_flags": row.get("acknowledged_flags") or [],
    }


@router.post("/synthesise")
async def synthesise(
    body: SynthesiseRequest,
    user: CurrentUser = Depends(get_current_user),
    db_repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    feedback = body.feedback.strip()
    employee_id = require_employee_access(db_repo, user, body.employee_id)

    if body.use_continuous_feedback and employee_id:
        cycle = body.review_cycle or current_review_cycle()
        summary = db_repo.get_feedback_summary(
            employee_id, cycle, body.review_type
        ) or db_repo.get_latest_summary(employee_id, body.review_type)
        if not summary:
            from agents.feedback_summary_agent import generate_feedback_summary

            try:
                gen = await generate_feedback_summary(
                    employee_id,
                    body.review_type,
                    db_repo,
                    vector_store,
                    review_cycle=cycle,
                    user_id=user.user_id,
                )
                if gen.get("summary"):
                    summary = db_repo.get_feedback_summary(
                        employee_id, gen["review_cycle"], body.review_type
                    )
            except Exception:
                summary = None
        if summary and summary.get("content"):
            feedback = (
                f"[CONTINUOUS FEEDBACK SUMMARY — {summary.get('review_cycle')}]\n"
                f"{summary['content']}\n\n[ADDITIONAL NOTES]\n{feedback}"
            ).strip()

    if not feedback:
        raise HTTPException(status_code=400, detail="Feedback is required")
    if employee_id and not _can_write_feedback_for_employee(db_repo, user, employee_id):
        raise HTTPException(
            status_code=403,
            detail="Only managers can synthesise feedback for their direct reports",
        )

    try:
        start_trace("synthesiser", employee_id, user.user_id)
        trace = get_trace()
        result = await run_synthesis(feedback, employee_id, db_repo, vector_store)
        score = result.get("score")
        gate_blocked = bool(result.get("gate_blocked"))
        gate_reason = result.get("gate_reason")
        level, conf_score, reason = objectivity_to_confidence(score)
        synthesis_id = f"syn_{uuid.uuid4().hex[:12]}"
        row = db_repo.insert_synthesis(
            {
                "synthesis_id": synthesis_id,
                "employee_id": employee_id or "",
                "author_user_id": user.user_id,
                "raw_text": feedback,
                "commentary": result.get("commentary", ""),
                "objectivity_score": score,
                "flags": result.get("flags") or [],
                "gate_blocked": gate_blocked,
                "gate_reason": gate_reason,
            }
        )
        if trace:
            trace.confidence(level, conf_score, reason)
            trace.decision(
                "Synthesis draft created",
                gate_reason or f"Objectivity {score}/100",
                sources=["milestone_embeddings", "bias_taxonomy"],
            )
            if gate_blocked:
                trace.decision(
                    "Bias gate active",
                    gate_reason or "High-severity flags require acknowledgement",
                    sources=["bias_taxonomy"],
                )
        finish_trace(
            db_repo,
            summary=f"Synthesised feedback (objectivity score {score})"
            if score
            else "Synthesised feedback",
            confidence={"level": level, "score": conf_score, "reason": reason},
            rationale={
                "decision": "Synthesis draft",
                "explanation": gate_reason or reason,
                "sources": ["bias_taxonomy"],
                "gate_blocked": gate_blocked,
                "acknowledged_flags": [],
                "finalised_at": None,
            },
        )
    except json.JSONDecodeError as exc:
        finish_trace(db_repo, status="failed", summary="LLM parse error")
        raise HTTPException(
            status_code=422,
            detail="Failed to parse LLM response as JSON",
        ) from exc
    except Exception as exc:
        finish_trace(db_repo, status="failed", summary=str(exc)[:120])
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _synthesis_response(row)


@router.post("/synthesise/finalise")
async def finalise_synthesis(
    body: FinaliseRequest,
    user: CurrentUser = Depends(get_current_user),
    db_repo: SqliteRepo = Depends(get_db_repo),
):
    row = db_repo.get_synthesis(body.synthesis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Synthesis not found")
    if row.get("author_user_id") != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if not _can_write_feedback_for_employee(db_repo, user, row["employee_id"]):
        raise HTTPException(status_code=403, detail="Access denied for this employee")
    if row.get("finalised_at"):
        return {"finalised": True, "synthesis_id": body.synthesis_id}

    if row.get("gate_blocked"):
        required = high_severity_passages(row.get("flags") or [])
        ack_set = set(body.acknowledged_flags or [])
        missing = [p for p in required if p not in ack_set]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "gate_blocked",
                    "unacknowledged": missing,
                    "message": (
                        "Please acknowledge all high-severity bias flags "
                        "before finalising."
                    ),
                },
            )

    start_trace("synthesiser", row["employee_id"], user.user_id)
    trace = get_trace()
    finalised = db_repo.finalise_synthesis(
        body.synthesis_id, body.acknowledged_flags or []
    )
    if trace:
        trace.decision(
            "Synthesis finalised",
            row.get("gate_reason") or "Commentary approved for save",
            sources=["bias_taxonomy"],
        )
    finish_trace(
        db_repo,
        summary="Synthesis finalised",
        rationale={
            "decision": "Synthesis finalised",
            "explanation": row.get("gate_reason") or "",
            "sources": ["bias_taxonomy"],
            "gate_blocked": bool(row.get("gate_blocked")),
            "acknowledged_flags": body.acknowledged_flags or [],
            "finalised_at": finalised.get("finalised_at") if finalised else None,
        },
    )
    return {"finalised": True, "synthesis_id": body.synthesis_id}
