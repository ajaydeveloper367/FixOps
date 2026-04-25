"""Schema-bound entity extraction (AD-002). Routing is never chosen by this LLM path."""

import json
import uuid
from typing import Any

import httpx
from fixops_contract.entities import ExtractedEntity

from fixops_controller.settings import settings


def extract_entity_llm(normalized: dict[str, Any]) -> ExtractedEntity:
    """Call shared LLM with strict JSON schema, or deterministic mock for CI."""
    if settings.mock_llm:
        return _mock_extract(normalized)
    return _openai_compatible_extract(normalized)


def _mock_extract(normalized: dict[str, Any]) -> ExtractedEntity:
    raw = normalized.get("raw") or {}
    labels = raw.get("labels") or {}
    if normalized.get("source") == "query":
        syn = raw.get("synthetic_alert") or {}
        return ExtractedEntity(
            entity_type=syn.get("entity_type", "service"),
            entity_name=syn.get("entity_name", "unknown"),
            namespace=syn.get("namespace"),
            alert_class=syn.get("alert_class", "QuerySynthetic"),
            labels=dict(syn.get("labels") or {}),
        )
    return ExtractedEntity(
        entity_type=labels.get("entity_type", "pod"),
        entity_name=raw.get("pod") or raw.get("service") or "unknown",
        namespace=raw.get("namespace"),
        alert_class=raw.get("alertname") or raw.get("alert_class"),
        labels={k: str(v) for k, v in labels.items()},
    )


def _openai_compatible_extract(normalized: dict[str, Any]) -> ExtractedEntity:
    if not settings.llm_api_key:
        return _mock_extract(normalized)
    url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    schema_hint = ExtractedEntity.model_json_schema()
    body = {
        "model": settings.llm_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "Extract operational entity fields only. Output a single JSON object matching the schema keys: entity_type, entity_name, namespace, alert_class, labels.",
            },
            {"role": "user", "content": json.dumps(normalized)[:8000]},
            {"role": "user", "content": f"JSON Schema: {json.dumps(schema_hint)[:4000]}"},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    rid = str(uuid.uuid4())
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return ExtractedEntity.model_validate(parsed)
