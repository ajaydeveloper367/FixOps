"""Schema-bound entity extraction (AD-002). Routing is never chosen by this LLM path."""

import json
from typing import Any

from fixops_contract.entities import ExtractedEntity

from fixops_controller.llm.client import chat_completion_json, llm_configured
from fixops_controller.settings import settings


def coalesce_extracted_from_normalized(
    entity: ExtractedEntity, normalized: dict[str, Any]
) -> ExtractedEntity:
    """Fill blanks left by the LLM from ``normalized.raw`` (pod, namespace, labels, alertname)."""
    raw = normalized.get("raw") or {}
    raw_labels = {k: str(v) for k, v in (raw.get("labels") or {}).items() if v is not None}

    name = (entity.entity_name or "").strip()
    if not name:
        name = (
            _non_empty_str(raw.get("pod"))
            or _non_empty_str(raw.get("service"))
            or _non_empty_str(raw.get("deployment"))
            or _non_empty_str(raw_labels.get("app"))
            or _non_empty_str(raw.get("name"))
            or "unknown"
        )

    et = (entity.entity_type or "").strip().lower()
    if not et:
        et = (_non_empty_str(raw_labels.get("entity_type")) or "pod").lower()

    ns = entity.namespace
    if ns is not None and not str(ns).strip():
        ns = None
    if ns is None:
        ns = _non_empty_str(raw.get("namespace"))

    ac = entity.alert_class
    if ac is None or not str(ac).strip():
        ac = _non_empty_str(raw.get("alertname")) or _non_empty_str(raw.get("alert_class"))

    labels = dict(raw_labels)
    for k, v in entity.labels.items():
        vs = _non_empty_str(v)
        if vs:
            labels[k] = vs

    return ExtractedEntity(
        entity_type=et,
        entity_name=name,
        namespace=ns,
        alert_class=ac,
        labels=labels,
    )


def _non_empty_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clean_llm_labels(obj: Any) -> dict[str, str]:
    """LLMs often emit null values or empty keys; ``ExtractedEntity.labels`` is ``dict[str, str]`` only."""
    if not isinstance(obj, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in obj.items():
        if k is None:
            continue
        ks = str(k).strip()
        if not ks:
            continue
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            out[ks] = json.dumps(v, default=str)[:512]
        else:
            vs = str(v).strip()
            if vs:
                out[ks] = vs
    return out


def _sanitize_llm_extracted_dict(parsed: dict[str, Any]) -> dict[str, Any]:
    """Coerce OpenAI-style JSON into values ``ExtractedEntity`` accepts."""
    p = dict(parsed)
    p["labels"] = _clean_llm_labels(p.get("labels"))
    # Use "" when missing so ``coalesce_extracted_from_normalized`` can still fill from ``raw``.
    p["entity_type"] = _non_empty_str(p.get("entity_type")) or ""
    p["entity_name"] = _non_empty_str(p.get("entity_name")) or ""
    p["namespace"] = _non_empty_str(p.get("namespace"))
    p["alert_class"] = _non_empty_str(p.get("alert_class"))
    return p


def extract_entity_llm(normalized: dict[str, Any]) -> ExtractedEntity:
    """Call shared LLM with strict JSON schema, or deterministic mock for CI / no LLM config."""
    # Query ingress already carries bounded synthetic entity keys (AD-013); keep this path deterministic
    # so routing doesn't depend on an LLM rewriting synthetic_alert fields.
    if normalized.get("source") == "query":
        return _extract_query_synthetic(normalized)
    if settings.mock_llm or not llm_configured():
        ent = _mock_extract(normalized)
    else:
        ent = _openai_compatible_extract(normalized)
    return coalesce_extracted_from_normalized(ent, normalized)


def _extract_query_synthetic(normalized: dict[str, Any]) -> ExtractedEntity:
    raw = normalized.get("raw") or {}
    syn = raw.get("synthetic_alert") or {}
    labels = {
        str(k): str(v)
        for k, v in (syn.get("labels") or {}).items()
        if k is not None and v is not None and str(k).strip() and str(v).strip()
    }
    return ExtractedEntity(
        entity_type=_non_empty_str(syn.get("entity_type")) or "service",
        entity_name=_non_empty_str(syn.get("entity_name")) or "cluster-query",
        namespace=_non_empty_str(syn.get("namespace")),
        alert_class=_non_empty_str(syn.get("alert_class")) or "AdHocQuery",
        labels=labels,
    )


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
    schema_hint = ExtractedEntity.model_json_schema()
    messages = [
        {
            "role": "system",
            "content": (
                "Extract operational entity fields only. Output a single JSON object with keys: "
                "entity_type, entity_name, namespace, alert_class, labels. "
                "Use null for unknown optional fields. labels must be an object with string values."
            ),
        },
        {"role": "user", "content": json.dumps(normalized)[:8000]},
        {"role": "user", "content": f"JSON Schema: {json.dumps(schema_hint)[:4000]}"},
    ]
    parsed = chat_completion_json(messages)
    if not isinstance(parsed, dict):
        raise ValueError("extract LLM returned non-object JSON")
    return ExtractedEntity.model_validate(_sanitize_llm_extracted_dict(parsed))
