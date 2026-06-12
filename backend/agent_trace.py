"""Agent activity tracing — in-memory trace per request, persisted on finish."""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from typing import Any

from workflow_context import get_workflow_id

_trace: ContextVar["AgentTrace | None"] = ContextVar("agent_trace", default=None)

AGENT_LABELS: dict[str, str] = {
    "coach": "Growth Coach",
    "calibrator": "Goal Calibrator",
    "synthesiser": "Feedback Synthesiser",
    "review_drafter": "Review Drafter",
    "feedback_summary": "Feedback Summary",
    "okr_lookup": "OKR Lookup",
    "health_scoring": "Health Scoring",
    "context_brief": "Coach Context Brief",
    "self_assessment_suggest": "Self-Assessment Suggest",
    "goal_suggestion_draft": "Goal Suggestion Draft",
}


def agent_label(agent: str) -> str:
    return AGENT_LABELS.get(agent, agent.replace("_", " ").title())


class AgentTrace:
    def __init__(
        self,
        agent: str,
        employee_id: str | None,
        user_id: str | None,
        workflow_id: str | None = None,
    ):
        self.id = f"trace_{uuid.uuid4().hex[:12]}"
        self.agent = agent
        self.employee_id = employee_id
        self.user_id = user_id
        self.workflow_id = workflow_id
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []
        self._confidence: dict[str, Any] | None = None
        self._rationale: dict[str, Any] | None = None

    def handoff(self, to: str, detail: str = "") -> None:
        self.steps.append(
            {
                "kind": "handoff",
                "type": "handoff",
                "from": self.agent,
                "to": to,
                "detail": detail,
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def search(self, collection: str, query: str, hits: list) -> None:
        summaries: list[str] = []
        for hit in hits[:5]:
            if collection == "policy_chunks":
                summaries.append(
                    hit.get("section_title") or hit.get("doc_title") or "Policy chunk"
                )
            elif collection == "okr_embeddings":
                summaries.append(hit.get("title") or hit.get("okr_id", ""))
            elif collection == "milestone_embeddings":
                summaries.append(hit.get("id", "milestone"))
            elif collection == "employees_fts":
                summaries.append(
                    f"{hit.get('name', '')} ({hit.get('employee_id', '')})".strip()
                )
            elif collection == "feedback_embeddings":
                summaries.append(hit.get("id", "feedback") if isinstance(hit, dict) else str(hit)[:80])
            else:
                summaries.append(str(hit)[:80])
        self.steps.append(
            {
                "kind": "search",
                "type": "search",
                "collection": collection,
                "query": query[:120],
                "hit_count": len(hits),
                "hits": summaries,
                "detail": f'"{query[:60]}" → {len(hits)} hits',
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def load(self, resource: str, detail: str, count: int = 0) -> None:
        self.steps.append(
            {
                "kind": "load",
                "type": "load",
                "resource": resource,
                "source": resource,
                "detail": detail,
                "count": count,
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def llm(self, model: str, detail: str = "") -> None:
        self.steps.append(
            {
                "kind": "llm",
                "type": "llm",
                "model": model,
                "detail": detail,
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def result(self, summary: str) -> None:
        self.steps.append(
            {
                "kind": "result",
                "type": "result",
                "detail": summary,
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def decision(self, decision: str, explanation: str, sources: list[str] | None = None) -> None:
        self._rationale = {
            "decision": decision,
            "explanation": explanation,
            "sources": sources or [],
        }
        self.steps.append(
            {
                "kind": "decision",
                "type": "decision",
                "detail": decision,
                "explanation": explanation,
                "sources": sources or [],
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )

    def confidence(
        self,
        level: str,
        score: float | None = None,
        reason: str = "",
    ) -> None:
        self._confidence = {
            "level": level,
            "score": score,
            "reason": reason,
        }
        detail = f"{level} ({score})" if score is not None else level
        self.steps.append(
            {
                "kind": "confidence",
                "type": "confidence",
                "detail": detail,
                "reason": reason,
                "at_ms": int((time.time() - self.started) * 1000),
            }
        )


def start_trace(
    agent: str,
    employee_id: str | None = None,
    user_id: str | None = None,
    workflow_id: str | None = None,
) -> AgentTrace:
    wid = workflow_id or get_workflow_id()
    trace = AgentTrace(agent, employee_id, user_id, workflow_id=wid)
    _trace.set(trace)
    return trace


def get_trace() -> AgentTrace | None:
    return _trace.get()


def log_search(collection: str, query: str, hits: list) -> None:
    trace = get_trace()
    if trace:
        trace.search(collection, query, hits)


def finish_trace(
    repo,
    status: str = "completed",
    summary: str | None = None,
    confidence: dict[str, Any] | None = None,
    rationale: dict[str, Any] | None = None,
) -> str | None:
    trace = _trace.get()
    if not trace:
        return None
    duration_ms = int((time.time() - trace.started) * 1000)
    conf = confidence or trace._confidence
    rat = rationale or trace._rationale
    repo.insert_agent_activity(
        {
            "id": trace.id,
            "agent": trace.agent,
            "employee_id": trace.employee_id,
            "user_id": trace.user_id,
            "workflow_id": trace.workflow_id,
            "status": status,
            "summary": summary or "",
            "duration_ms": duration_ms,
            "steps_json": json.dumps(trace.steps),
            "confidence_level": conf.get("level") if conf else None,
            "confidence_score": conf.get("score") if conf else None,
            "confidence_reason": conf.get("reason") if conf else None,
            "rationale_json": json.dumps(rat) if rat else None,
        }
    )
    if trace.workflow_id:
        repo.touch_workflow_run(trace.workflow_id, trace.employee_id, trace.user_id)
    _trace.set(None)
    return trace.id
