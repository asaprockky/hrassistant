"""OpenAI HTTP client used by the AI interview and AI resume review
endpoints.

The OpenAI API key is read from the OPENAI_API_KEY environment variable.
If the variable is missing the helper functions raise
HTTPException(status_code=503, detail="ai_unavailable") so callers can
surface a clean "AI is not configured" error to the client without
crashing the request handler.

We intentionally avoid the official `openai` SDK so the backend does not
pick up a heavy dependency for two endpoints. The OpenAI chat completions
HTTP API is stable enough to call with the stdlib.
"""
from __future__ import annotations

import json
import os
import re
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_INTERVIEW_MODEL = os.environ.get(
    "OPENAI_INTERVIEW_MODEL", "gpt-4o-mini"
)
DEFAULT_RESUME_MODEL = os.environ.get(
    "OPENAI_RESUME_MODEL", "gpt-4o-mini"
)
HTTP_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "45"))


class AIServiceUnavailable(HTTPException):
    """Raised when the OPENAI_API_KEY is not configured or the upstream
    OpenAI call fails. Mapped to 503 so the client can show a graceful
    fallback ("AI is offline right now")."""

    def __init__(self, detail: str = "ai_unavailable"):
        super().__init__(status_code=503, detail=detail)


def is_configured() -> bool:
    """Returns True if the OPENAI_API_KEY env var is set. UI/health
    endpoints can call this without raising."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def _require_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise AIServiceUnavailable("openai_api_key_missing")
    return key


def chat_completion(
    messages: Iterable[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.4,
    max_tokens: int = 600,
    response_format: Optional[dict] = None,
) -> str:
    """Single OpenAI chat completion call. Returns the assistant message
    content as a string.

    `messages` is an iterable of `{"role": "system"|"user"|"assistant",
    "content": "..."}` dicts.

    Set `response_format={"type": "json_object"}` to force OpenAI to
    return a valid JSON document (used by the resume reviewer + the
    interview final grading step).
    """
    key = _require_api_key()
    body: dict = {
        "model": model or DEFAULT_INTERVIEW_MODEL,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format

    req = Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "talentflow-backend/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        # OpenAI returned a 4xx/5xx. Try to surface their error code so
        # the admin can debug bad keys / rate limits.
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {"error": str(exc)}
        raise AIServiceUnavailable(
            f"openai_http_{exc.code}:{detail.get('error', {}).get('code') or detail.get('error') or 'unknown'}"
        )
    except URLError as exc:
        raise AIServiceUnavailable(f"openai_unreachable:{exc.reason}")

    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise AIServiceUnavailable(f"openai_bad_response:{exc}")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def parse_json_response(content: str) -> dict:
    """OpenAI sometimes wraps JSON in markdown fences even when asked
    for `response_format=json_object`. Strip the fence and parse, raise
    AIServiceUnavailable on a malformed payload."""
    fenced = _JSON_FENCE_RE.search(content)
    if fenced:
        content = fenced.group(1)
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIServiceUnavailable(f"openai_invalid_json:{exc}")
