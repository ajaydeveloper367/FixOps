"""Tiny Ollama (OpenAI-compatible) client: one place, no domain logic."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field


class OllamaJsonConfig(BaseModel):
    """Each service builds this from its own settings (endpoint + model)."""

    base_url: str = Field(
        description="Example: http://127.0.0.1:11434/v1 (OpenAI-compatible path)"
    )
    model: str
    timeout_seconds: float = 120.0


def complete_json(
    config: OllamaJsonConfig,
    *,
    system: str,
    user: str,
) -> dict[str, Any]:
    """
    Ask the model for a single JSON object in the assistant message content.
    Raises ValueError on transport/parse errors.
    """
    url = config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "stream": False,
    }
    with httpx.Client(timeout=config.timeout_seconds) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected chat response shape: {data!r}") from e
    content = content.strip()
    if content.startswith("```"):
        # fence optional
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return json.loads(content)
