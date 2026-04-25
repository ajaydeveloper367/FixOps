"""RCA synthesis from structured evidence only — no raw log paste."""

import json
from typing import Any

from fixops_controller.llm.client import chat_completion_json, llm_configured
from fixops_controller.settings import settings


def synthesize_rca(
    normalized: dict[str, Any],
    merged_worker: dict[str, Any],
    evidence_chain: dict[str, Any],
) -> dict[str, Any]:
    if settings.mock_llm or not llm_configured():
        return _mock_rca(merged_worker, evidence_chain)
    messages = [
        {
            "role": "system",
            "content": (
                "Produce a single JSON object with keys: summary, root_cause_hypothesis, "
                "evidence_chain (object, echo the input evidence_chain), recommended_next_steps (array of strings). "
                "Use only the structured evidence provided; do not invent log lines or secret values."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"normalized": normalized, "merged_worker": merged_worker, "evidence_chain": evidence_chain}
            )[:12000],
        },
    ]
    return chat_completion_json(messages)


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
