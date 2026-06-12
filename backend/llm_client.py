"""Unified LLM client — Gemini (cloud) or Ollama (local)."""

from __future__ import annotations

import json
import os
import time
from typing import AsyncGenerator

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
GEMINI_MAX_INPUT_CHARS = int(os.getenv("GEMINI_MAX_INPUT_CHARS", "6000"))
GEMINI_SKIP_HEALTH_API = os.getenv("GEMINI_SKIP_HEALTH_API", "true").lower() in (
    "1",
    "true",
    "yes",
)
LLM_HEALTH_CACHE_SECONDS = int(os.getenv("LLM_HEALTH_CACHE_SECONDS", "300"))
LLM_MAX_CHAT_MESSAGES = int(os.getenv("LLM_MAX_CHAT_MESSAGES", "6"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

_configured = os.getenv("LLM_PROVIDER", "").strip().lower()
if _configured in ("gemini", "ollama"):
    LLM_PROVIDER = _configured
elif GEMINI_API_KEY:
    LLM_PROVIDER = "gemini"
else:
    LLM_PROVIDER = "ollama"

MODEL = GEMINI_MODEL if LLM_PROVIDER == "gemini" else OLLAMA_MODEL
BASE_URL = GEMINI_BASE_URL if LLM_PROVIDER == "gemini" else OLLAMA_BASE_URL

_health_cache: dict | None = None
_health_cache_at: float = 0.0
_startup_probe: dict = {"done": False, "ok": False, "detail": None}
GEMINI_PROBE_AT_STARTUP = os.getenv("GEMINI_PROBE_AT_STARTUP", "true").lower() in (
    "1",
    "true",
    "yes",
)


def _gemini_error_detail(exc: Exception | None = None) -> str:
    base = (
        "Gemini API is not configured. Set GEMINI_API_KEY in backend/.env "
        f"(model: {GEMINI_MODEL})."
    )
    if exc:
        return f"{base} Error: {exc}"
    return base


def _ollama_error_detail() -> str:
    return (
        "Ollama is not running. Install from https://ollama.com/download, "
        f"open the Ollama app, then run: ollama pull {OLLAMA_MODEL}"
    )


def _llm_unavailable_detail() -> str:
    if LLM_PROVIDER == "gemini":
        return _gemini_error_detail()
    return _ollama_error_detail()


def _truncate(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def trim_chat_messages(messages: list[dict]) -> list[dict]:
    """Keep recent turns only; skip UI welcome message."""
    chat = [m for m in messages if m.get("content", "").strip()]
    if chat and chat[0].get("role") == "assistant":
        chat = chat[1:]
    return chat[-LLM_MAX_CHAT_MESSAGES:]


def check_llm_status() -> dict:
    """Provider-aware health check for /api/health."""
    global _health_cache, _health_cache_at

    now = time.time()
    if _health_cache and now - _health_cache_at < LLM_HEALTH_CACHE_SECONDS:
        return _health_cache

    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            result = {
                "llm_provider": "gemini",
                "llm_ok": False,
                "model_ready": False,
                "model": GEMINI_MODEL,
                "models": [],
                "detail": "GEMINI_API_KEY not set in backend/.env",
            }
            _health_cache = result
            _health_cache_at = now
            return result
        if GEMINI_SKIP_HEALTH_API:
            model_ready = _startup_probe["ok"] if _startup_probe["done"] else bool(GEMINI_API_KEY)
            result = {
                "llm_provider": "gemini",
                "llm_ok": bool(GEMINI_API_KEY),
                "model_ready": model_ready,
                "model": GEMINI_MODEL,
                "models": [GEMINI_MODEL],
                "detail": _startup_probe.get("detail"),
            }
            _health_cache = result
            _health_cache_at = now
            return result
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}",
                    params={"key": GEMINI_API_KEY},
                )
                if response.status_code == 404:
                    result = {
                        "llm_provider": "gemini",
                        "llm_ok": True,
                        "model_ready": False,
                        "model": GEMINI_MODEL,
                        "models": [GEMINI_MODEL],
                        "detail": f"Model '{GEMINI_MODEL}' not found. Check GEMINI_MODEL.",
                    }
                else:
                    response.raise_for_status()
                    result = {
                        "llm_provider": "gemini",
                        "llm_ok": True,
                        "model_ready": True,
                        "model": GEMINI_MODEL,
                        "models": [GEMINI_MODEL],
                    }
        except Exception as exc:
            result = {
                "llm_provider": "gemini",
                "llm_ok": False,
                "model_ready": False,
                "model": GEMINI_MODEL,
                "models": [],
                "detail": str(exc),
            }
        _health_cache = result
        _health_cache_at = now
        return result

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            models = [m.get("name", "") for m in response.json().get("models", [])]
            model_ready = any(
                m == OLLAMA_MODEL or m.startswith(f"{OLLAMA_MODEL}:") for m in models
            )
            result = {
                "llm_provider": "ollama",
                "llm_ok": True,
                "model_ready": model_ready,
                "model": OLLAMA_MODEL,
                "models": models,
            }
    except Exception:
        result = {
            "llm_provider": "ollama",
            "llm_ok": False,
            "model_ready": False,
            "model": OLLAMA_MODEL,
            "models": [],
        }
    _health_cache = result
    _health_cache_at = now
    return result


def _gemini_contents(messages: list[dict]) -> list[dict]:
    contents = []
    for msg in messages:
        role = "model" if msg.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    return contents


def _parse_gemini_http_error(status_code: int, body: str) -> str:
    try:
        err = json.loads(body)
        msg = err.get("error", {}).get("message", "")
    except json.JSONDecodeError:
        msg = body[:200]

    lower = msg.lower()
    if status_code == 429 or "quota" in lower or "credit" in lower or "depleted" in lower:
        return (
            "Gemini quota or prepayment credits are exhausted. "
            "Add credits at https://ai.studio/projects or wait for your limit to reset."
        )
    if status_code in (401, 403) or "api key" in lower or "permission" in lower:
        return (
            "Gemini API key is invalid or lacks permission. "
            "Create a key at https://aistudio.google.com/apikey and set GOOGLE_API_KEY or GEMINI_API_KEY in backend/.env."
        )
    if status_code == 404:
        return f"Gemini model '{GEMINI_MODEL}' not found. Check GEMINI_MODEL in backend/.env."
    return f"Gemini API error ({status_code}): {msg[:200] or body[:200]}"


async def probe_llm_generation() -> dict:
    """One lightweight generate call at startup to verify quota/key."""
    global _startup_probe
    if LLM_PROVIDER != "gemini":
        _startup_probe = {"done": True, "ok": True, "detail": None}
        return _startup_probe
    if not GEMINI_API_KEY:
        _startup_probe = {
            "done": True,
            "ok": False,
            "detail": "GEMINI_API_KEY not set in backend/.env",
        }
        return _startup_probe
    if not GEMINI_PROBE_AT_STARTUP:
        _startup_probe = {"done": True, "ok": True, "detail": None}
        return _startup_probe
    try:
        await _gemini_complete("Reply with exactly: OK", "Test only.", GEMINI_MODEL)
        _startup_probe = {"done": True, "ok": True, "detail": None}
    except HTTPException as exc:
        _startup_probe = {"done": True, "ok": False, "detail": str(exc.detail)}
    except Exception as exc:
        _startup_probe = {"done": True, "ok": False, "detail": str(exc)}
    return _startup_probe


def _extract_gemini_text(data: dict) -> str:
    parts = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                parts.append(text)
    return "".join(parts)


async def _gemini_complete(prompt: str, system: str, model: str) -> str:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail=_gemini_error_detail())

    prompt = _truncate(prompt, GEMINI_MAX_INPUT_CHARS)
    system = _truncate(system, min(GEMINI_MAX_INPUT_CHARS, 4000))

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            "temperature": 0.4,
        },
    }
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url, params={"key": GEMINI_API_KEY}, json=payload
            )
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=503,
                    detail=_parse_gemini_http_error(response.status_code, response.text),
                )
            data = response.json()
            text = _extract_gemini_text(data)
            if not text:
                raise HTTPException(
                    status_code=503,
                    detail="Gemini returned an empty response",
                )
            return text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_gemini_error_detail(exc)) from exc


async def _gemini_stream(
    messages: list[dict], system: str, model: str
) -> AsyncGenerator[str, None]:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail=_gemini_error_detail())

    messages = trim_chat_messages(messages)
    system = _truncate(system, min(GEMINI_MAX_INPUT_CHARS, 4000))

    payload = {
        "contents": _gemini_contents(messages),
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "maxOutputTokens": min(GEMINI_MAX_OUTPUT_TOKENS, 512),
            "temperature": 0.5,
        },
    }
    url = f"{GEMINI_BASE_URL}/models/{model}:streamGenerateContent"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                params={"key": GEMINI_API_KEY, "alt": "sse"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise HTTPException(
                        status_code=503,
                        detail=_parse_gemini_http_error(
                            response.status_code, body.decode()
                        ),
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_gemini_text(chunk)
                    if text:
                        yield text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_gemini_error_detail(exc)) from exc


async def _ollama_complete(prompt: str, system: str, model: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail=_ollama_error_detail())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=_ollama_error_detail()) from exc


async def _ollama_stream(
    messages: list[dict], system: str, model: str
) -> AsyncGenerator[str, None]:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "system": system,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail=_ollama_error_detail())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=_ollama_error_detail()) from exc


async def llm_complete(prompt: str, system: str, model: str | None = None) -> str:
    model = model or MODEL
    trace = None
    try:
        from agent_trace import get_trace

        trace = get_trace()
    except ImportError:
        pass
    t0 = time.time()
    if trace:
        trace.llm(model, "Completion started")
    if LLM_PROVIDER == "gemini":
        result = await _gemini_complete(prompt, system, model)
    else:
        result = await _ollama_complete(prompt, system, model)
    if trace:
        trace.llm(model, f"Completed in {int((time.time() - t0) * 1000)}ms")
    return result


async def llm_stream(
    messages: list[dict], system: str, model: str | None = None
) -> AsyncGenerator[str, None]:
    model = model or MODEL
    trace = None
    try:
        from agent_trace import get_trace

        trace = get_trace()
    except ImportError:
        pass
    t0 = time.time()
    if trace:
        trace.llm(model, "Stream started")
    try:
        if LLM_PROVIDER == "gemini":
            async for chunk in _gemini_stream(messages, system, model):
                yield chunk
        else:
            async for chunk in _ollama_stream(messages, system, model):
                yield chunk
    finally:
        if trace:
            trace.llm(model, f"Stream completed in {int((time.time() - t0) * 1000)}ms")


# Backward-compatible aliases
ollama_complete = llm_complete
ollama_stream = llm_stream
check_ollama_status = check_llm_status
