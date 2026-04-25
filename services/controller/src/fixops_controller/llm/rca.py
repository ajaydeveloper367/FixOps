"""RCA synthesis from structured evidence only — no raw log paste."""

import json
import uuid
from typing import Any

import httpx

from fixops_controller.settings import settings


def synthesize_rca(
    normalized: dict[str, Any],
    merged_worker: dict[str, Any],
    evidence_chain: dict[str, Any],
) -> dict[str, Any]:
    if settings.mock_llm or not settings.llm_api_key:
        return _mock_rca(merged_worker, evidence_chain)
    url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    body = {
        "model": settings.llm_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Produce RCA JSON with keys: summary, root_cause_hypothesis, "
                    "evidence_chain (object echoing input), recommended_next_steps (array). "
                    "Use only the structured evidence provided; do not invent log lines."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"normalized": normalized, "merged_worker": merged_worker, "evidence_chain": evidence_chain}
                )[:12000],
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    with httpx.Client(timeout=90.0) as client:
        r = client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


def _mock_rca(merged_worker: dict[str, Any], evidence_chain: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "Mock RCA: narrative grounded in structured worker fields only.",
        "root_cause_hypothesis": (merged_worker.get("findings") or ["unknown"])[0],
        "evidence_chain": evidence_chain,
        "recommended_next_steps": [
            "Validate evidence_refs in dashboards",
            "Human approve before executor (AD-003)",
        ],
    }
