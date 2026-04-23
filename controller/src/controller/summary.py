"""Optional LLM narrative; controller-only."""

from __future__ import annotations

import json

from fixops_contract.models import AlertPayload, WorkerResponse
from fixops_contract.ollama_json import OllamaJsonConfig, complete_json


def build_summary_lines(
    *,
    ollama: OllamaJsonConfig | None,
    alert: AlertPayload,
    worker_id: str,
    worker_out: WorkerResponse,
) -> list[str]:
    if ollama is None:
        return [
            f"[{worker_id}] confidence={worker_out.confidence:.2f}",
            *worker_out.findings,
        ]
    system = (
        "You summarize an operational investigation for an on-call engineer. "
        "Return ONLY JSON: {\"lines\": string[]} with 3-8 short lines, no markdown."
    )
    payload = {
        "alert": alert.model_dump(),
        "worker": worker_id,
        "structured": worker_out.model_dump(),
    }
    user = json.dumps(payload, indent=2)[:14000]
    data = complete_json(ollama, system=system, user=user)
    lines = data.get("lines")
    if not isinstance(lines, list):
        raise ValueError("Expected lines[] in LLM JSON")
    return [str(x) for x in lines]
