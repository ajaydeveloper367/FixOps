"""OpenAI-compatible chat completions (Ollama, vLLM, OpenAI, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from fixops_controller.settings import settings

logger = logging.getLogger(__name__)


def _message_content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def parse_llm_json_object(content: str) -> dict[str, Any]:
    """
    Parse JSON from model output (Ollama often wraps in markdown or adds prose).
    """
    s = (content or "").strip()
    if not s:
        raise ValueError("LLM returned empty message content (check model is running and /v1/chat/completions works)")

    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    try:
        out = json.loads(s)
        if isinstance(out, dict):
            return out
    except json.JSONDecodeError:
        pass

    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            out = json.loads(s[start : end + 1])
            if isinstance(out, dict):
                return out
        except json.JSONDecodeError:
            pass

    raise ValueError(f"LLM content is not valid JSON object. First 400 chars: {s[:400]!r}")


def llm_configured() -> bool:
    """True when mock is off and a remote model should be called."""
    return (not settings.mock_llm) and bool(settings.llm_base_url or settings.llm_api_key)


def chat_completion_json(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """
    POST /v1/chat/completions; returns parsed JSON object from message content.
    Retries without response_format if the server rejects json_object mode (common on Ollama).
    """
    base = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    def _post(extra: dict[str, Any]) -> dict[str, Any]:
        payload = {**body, **extra}
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=payload, headers=headers)
            if r.status_code >= 400:
                logger.warning("LLM HTTP %s: %s", r.status_code, r.text[:500])
            r.raise_for_status()
            return r.json()

    if settings.llm_use_json_response_format:
        try:
            data = _post({"response_format": {"type": "json_object"}})
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 400:
                logger.info("Retrying LLM without response_format (json_object not supported)")
                data = _post({})
            else:
                raise
    else:
        data = _post({})

    msg = data["choices"][0].get("message") or {}
    content = _message_content_to_str(msg.get("content"))
    return parse_llm_json_object(content)
