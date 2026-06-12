"""Request-scoped workflow ID for end-to-end agent trace correlation."""

from __future__ import annotations

from contextvars import ContextVar

_workflow_id: ContextVar[str | None] = ContextVar("workflow_id", default=None)


def get_workflow_id() -> str | None:
    return _workflow_id.get()


def set_workflow_id(workflow_id: str | None) -> None:
    _workflow_id.set(workflow_id)
