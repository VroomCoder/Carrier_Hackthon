from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_trace import finish_trace, get_trace, start_trace
from agents.coach_context_brief import build_coach_context_brief
from confidence_utils import brief_completeness_confidence
from auth import (
    CurrentUser,
    get_current_user,
    require_coach_employee_id,
)
from db.sqlite_repo import SqliteRepo
from db.vector_store import VectorStore
from ollama_client import ollama_stream, trim_chat_messages

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict]
    employee_id: str | None = None
    session_id: str | None = None


def get_db_repo() -> SqliteRepo:
    from main import db

    return db


def get_vs() -> VectorStore:
    from main import vs

    return vs


def _coach_system_prompt(brief_text: str) -> str:
    return f"""You are the Growth Coach at NexaCore — a personal development coach for the employee below.

The EMPLOYEE CONTEXT BRIEF is your grounded working memory. It contains their real goals, OKRs, shared manager feedback, health score, cycle status, prior sessions, peer benchmarks, and policy excerpts. Do NOT ask them to re-explain information already in the brief.

Coaching rules:
- Reference their actual goals, feedback patterns, and cycle stage when relevant.
- Notice recurring themes in manager feedback (e.g. repeated development areas).
- Proactively surface important items they have not asked about but should know (e.g. uncalibrated goals, low health dimension, upcoming review readiness).
- Cite policy sections only when the brief includes relevant excerpts.
- Be warm, specific, and actionable — never generic.
- Reply in 2–5 sentences unless they ask for detail or a list.

{brief_text}"""


@router.get("/chat/context")
def get_chat_context(
    employee_id: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
    db_repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    """Return personalised greeting and context brief for session open."""
    eid = require_coach_employee_id(db_repo, user, employee_id)
    if not eid:
        return {
            "employee_id": None,
            "greeting": "Hi — I'm your Growth Coach. How can I help you today?",
            "brief_text": "",
        }
    start_trace("coach", eid, user.user_id)
    trace = get_trace()
    if trace:
        trace.handoff("context_brief", "Build full employee context brief")
    result = build_coach_context_brief(eid, user, db_repo, vector_store)
    if trace:
        trace.load("context_brief", f"{len(result['brief_text'])} chars assembled")
    level, score, reason = brief_completeness_confidence(result.get("sections", {}))
    if trace:
        trace.confidence(level, score, reason)
        trace.decision(
            "Context brief assembled",
            f"Personalised greeting from {len(result.get('sections', {}))} context sections",
            sources=list(result.get("sections", {}).keys()),
        )
    finish_trace(
        db_repo,
        summary="Coach context brief ready",
        confidence={"level": level, "score": score, "reason": reason},
    )
    return {
        "employee_id": eid,
        "greeting": result["greeting"],
        "brief_text": result["brief_text"],
        "sections": list(result.get("sections", {}).keys()),
    }


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db_repo: SqliteRepo = Depends(get_db_repo),
    vector_store: VectorStore = Depends(get_vs),
):
    messages = trim_chat_messages(body.messages)
    last_msg = messages[-1]["content"] if messages else ""

    employee_id = require_coach_employee_id(db_repo, user, body.employee_id)

    start_trace("coach", employee_id, user.user_id)

    if employee_id:
        trace = get_trace()
        if trace:
            trace.handoff("context_brief", "Build full employee context brief")
        brief = build_coach_context_brief(
            employee_id, user, db_repo, vector_store, last_message=last_msg
        )
        if trace:
            trace.load("context_brief", f"{len(brief['brief_text'])} chars · 8 sections")
            level, score, reason = brief_completeness_confidence(brief.get("sections", {}))
            trace.confidence(level, score, reason)
            trace.decision(
                "Coaching response grounded in context brief",
                f"Injected brief covering {len(brief.get('sections', {}))} employee data sections",
                sources=list(brief.get("sections", {}).keys()),
            )
        system_prompt = _coach_system_prompt(brief["brief_text"])
        brief_confidence = brief_completeness_confidence(brief.get("sections", {}))
    else:
        system_prompt = """You are the Growth Coach at NexaCore. No employee profile is linked.
Give general career and performance coaching guidance."""
        brief_confidence = None

    if get_trace():
        get_trace().handoff("llm", "Generate coaching response")

    session_id = body.session_id or f"coach_{user.user_id}_{employee_id or 'general'}"

    async def generate():
        assistant_text = ""
        try:
            async for chunk in ollama_stream(messages, system_prompt):
                assistant_text += chunk
                yield chunk
        finally:
            if employee_id and messages:
                full_messages = list(messages)
                if assistant_text:
                    full_messages.append({"role": "assistant", "content": assistant_text})
                db_repo.upsert_session(session_id, employee_id, full_messages)
            finish_kwargs = {"summary": "Coach response streamed"}
            if brief_confidence:
                level, score, reason = brief_confidence
                finish_kwargs["confidence"] = {
                    "level": level,
                    "score": score,
                    "reason": reason,
                }
            finish_trace(db_repo, **finish_kwargs)

    return StreamingResponse(generate(), media_type="text/plain")
