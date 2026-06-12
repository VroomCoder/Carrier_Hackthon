"""Backward-compatible re-exports — use llm_client for new code."""

from llm_client import (  # noqa: F401
    BASE_URL,
    LLM_PROVIDER,
    MODEL,
    check_llm_status,
    check_ollama_status,
    llm_complete,
    llm_stream,
    ollama_complete,
    ollama_stream,
    probe_llm_generation,
    trim_chat_messages,
)
