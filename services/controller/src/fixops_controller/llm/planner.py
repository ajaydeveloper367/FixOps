"""Ingress planner: free text or messy payloads → same ``normalized`` shape as strict POST /run (AD-015)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fixops_controller.llm.client import chat_completion_json, llm_configured
from fixops_controller.settings import settings


def _env(default_environment: str | None) -> str:
    return (default_environment or settings.environment or "development").strip()


def _non_empty(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _mock_plan(
    *,
    message: str | None,
    payload: dict[str, Any] | None,
    default_environment: str | None,
) -> dict[str, Any]:
    env = _env(default_environment)
    if payload is not None:
        if isinstance(payload.get("source"), str) and isinstance(payload.get("raw"), dict):
            return {
                "source": payload["source"],
                "environment": str(payload.get("environment") or env),
                "raw": dict(payload["raw"]),
            }
        # Treat payload as alert ``raw``-only (messy webhook body).
        return {"source": "alert", "environment": env, "raw": dict(payload)}

    text = (message or "").strip()
    if not text:
        raise ValueError("message or payload is required")

    lower = text.lower()
    if "how many" in lower or "how long" in lower or "are there" in lower or "any " in lower:
        ns = None
        m = re.search(r"namespace\s+(\S+)", lower)
        if m:
            ns = m.group(1).rstrip(".,;")
        cluster_id = "local" if "local cluster" in lower or "cluster local" in lower else None
        labels: dict[str, str] = {"intent": "observability_question"}
        if cluster_id:
            labels["cluster_id"] = cluster_id
        return {
            "source": "query",
            "environment": env,
            "raw": {
                "session_id": str(uuid.uuid4()),
                "summary": text[:512],
                "synthetic_alert": {
                    "entity_type": "service",
                    "entity_name": "cluster-query",
                    "namespace": ns,
                    "alert_class": "AdHocQuery",
                    "labels": labels,
                },
            },
        }

    if "crash" in lower or "podcrash" in lower or "backoff" in lower:
        ns = "prod"
        m = re.search(r"namespace[:\s]+(\S+)", lower)
        if m:
            ns = m.group(1).rstrip(".,;")
        pod = "checkout-api-7d8f9"
        m2 = re.search(r"pod[:\s]+(\S+)", lower)
        if m2:
            pod = m2.group(1).rstrip(".,;")
        return {
            "source": "alert",
            "environment": env,
            "raw": {
                "alertname": "PodCrashLoopBackOff",
                "namespace": ns,
                "pod": pod,
                "labels": {"entity_type": "pod", "app": "checkout-api"},
            },
        }

    return {
        "source": "alert",
        "environment": env,
        "raw": {
            "alertname": "UnparsedAlert",
            "namespace": None,
            "pod": None,
            "labels": {"entity_type": "service", "note": text[:200]},
        },
    }


def _llm_plan(
    *,
    message: str | None,
    payload: dict[str, Any] | None,
    default_environment: str | None,
) -> dict[str, Any]:
    env = _env(default_environment)
    user_obj: dict[str, Any] = {
        "default_environment": env,
        "message": message,
        "payload": payload,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You normalize operational input into ONE JSON object for an investigation pipeline. "
                "Output ONLY valid JSON, no markdown.\n"
                "Schema:\n"
                '- source: \"alert\" | \"query\"\n'
                '- environment: string (use default_environment if unsure)\n'
                '- raw: object\n'
                "For source=alert, raw should include alertname (or title), namespace, pod or deployment if known, "
                "labels object with string values.\n"
                "For source=query, raw MUST include: session_id (UUID string), summary (short string), "
                "synthetic_alert: { entity_type, entity_name, namespace|null, alert_class, labels } "
                "so downstream extraction can route to workers.\n"
                "For natural-language ad-hoc ops questions, set synthetic_alert.alert_class to AdHocQuery.\n"
                "Infer missing optional fields as null or empty object; never invent secrets."
            ),
        },
        {"role": "user", "content": json.dumps(user_obj, default=str)[:12000]},
    ]
    return chat_completion_json(messages)


def finalize_planned_normalized(
    planned: dict[str, Any],
    *,
    fallback_summary: str | None,
) -> dict[str, Any]:
    """Ensure required keys exist so extract + graph do not break."""
    out = dict(planned)
    src = out.get("source")
    if src not in ("alert", "query"):
        raise ValueError('planned "source" must be "alert" or "query"')
    raw = dict(out.get("raw") or {})
    out["raw"] = raw
    out["environment"] = str(out.get("environment") or settings.environment or "development")

    if src == "query":
        if not str(raw.get("session_id") or "").strip():
            raw["session_id"] = str(uuid.uuid4())
        if not str(raw.get("summary") or "").strip():
            raw["summary"] = (fallback_summary or "Planned investigation")[:512]
        syn = raw.get("synthetic_alert")
        if not isinstance(syn, dict):
            syn = {}
        syn["entity_type"] = _non_empty(syn.get("entity_type")) or "service"
        syn["entity_name"] = _non_empty(syn.get("entity_name")) or "cluster-query"
        syn["alert_class"] = _non_empty(syn.get("alert_class")) or "AdHocQuery"
        labels = syn.get("labels")
        if not isinstance(labels, dict):
            labels = {}
        labels_out: dict[str, str] = {}
        for k, v in labels.items():
            ks = _non_empty(k)
            vs = _non_empty(v)
            if ks and vs:
                labels_out[ks] = vs
        # Planner is best-effort; help local demos by deriving cluster hint from question text.
        summary_l = str(raw.get("summary") or "").lower()
        if "local cluster" in summary_l and "cluster_id" not in labels_out:
            labels_out["cluster_id"] = "local"
        syn["labels"] = labels_out
        raw["synthetic_alert"] = syn
    else:
        raw.setdefault("labels", {})

    out["raw"] = raw
    return out


def plan_flexible_input(
    *,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    default_environment: str | None = None,
) -> dict[str, Any]:
    """
    Turn natural language and/or a messy dict into the same ``normalized`` dict
    accepted by ``POST /v1/investigations/run`` (after ``finalize_planned_normalized``).
    """
    if payload is None and (message is None or not str(message).strip()):
        raise ValueError("Provide a non-empty message and/or a payload object")

    if settings.mock_llm or not llm_configured():
        raw_plan = _mock_plan(message=message, payload=payload, default_environment=default_environment)
    else:
        raw_plan = _llm_plan(message=message, payload=payload, default_environment=default_environment)

    if not isinstance(raw_plan, dict):
        raise ValueError("planner returned non-object JSON")

    return finalize_planned_normalized(
        raw_plan,
        fallback_summary=message,
    )


def planner_mode_label() -> str:
    return "mock" if (settings.mock_llm or not llm_configured()) else "llm"
