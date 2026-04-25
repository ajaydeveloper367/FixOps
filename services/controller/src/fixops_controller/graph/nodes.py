"""LangGraph nodes — controller owns orchestration; no peer workers."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from fixops_contract.ad006 import WorkerInvestigateRequest
from fixops_contract.entities import ExtractedEntity

from fixops_controller.db.sync_session import append_decision_sync
from fixops_controller.graph.state import OpsState
from fixops_controller.inventory.repo_sync import graph_neighbors_sync, list_inventory_entities_sync
from fixops_controller.llm.extract import extract_entity_llm
from fixops_controller.llm.rca import synthesize_rca
from fixops_controller.rag.retrieve import retrieve_relevant_chunks_sync
from fixops_controller.routing.rules import load_routing_table, resolve_route
from fixops_controller.settings import settings


def _log(state: OpsState, step: str, payload: dict[str, Any]) -> None:
    iid = state.get("investigation_id") or "unknown"
    append_decision_sync(iid, step, payload)


def node_normalize(state: OpsState) -> dict[str, Any]:
    inv = state.get("investigation_id") or str(uuid.uuid4())
    raw = state.get("normalized") or {}
    if not raw:
        raw = {"source": "alert", "environment": settings.environment, "raw": {}}
    _log({**state, "investigation_id": inv}, "normalize", {"normalized": raw})
    return {"investigation_id": inv, "normalized": raw, "errors": []}


def node_extract(state: OpsState) -> dict[str, Any]:
    n = state["normalized"]
    ent = extract_entity_llm(n)
    payload = ent.model_dump()
    _log(state, "extract_entities", {"extracted": payload})
    return {"extracted": payload}


def node_route(state: OpsState) -> dict[str, Any]:
    routing = load_routing_table(settings.routing_rules_path) or {
        "default_worker_id": "worker-obs",
        "rules": [],
    }
    extracted = ExtractedEntity.model_validate(state["extracted"])
    inv_rows = list_inventory_entities_sync()
    worker_registry = {
        "worker-obs": settings.worker_obs_base_url,
        "worker-k8s": settings.worker_k8s_base_url,
        "worker-pipeline": settings.worker_pipeline_base_url,
        "worker-db": settings.worker_db_base_url,
        "worker-app-rca": settings.worker_app_rca_base_url,
    }
    decision = resolve_route(extracted, routing, inv_rows, worker_registry)
    route = {
        "worker_id": decision.worker_id,
        "worker_base_url": decision.worker_base_url,
        "cluster_id": decision.cluster_id,
        "credentials_ref": decision.credentials_ref,
        "inventory_match_id": decision.inventory_match_id,
    }
    _log(state, "route", {"route": route, "rules_version": routing.get("version")})
    return {"route": route}


def node_stage_context(state: OpsState) -> dict[str, Any]:
    """AD-005 staged context with hard per-stage budgets."""
    extracted = state["extracted"]
    route = state["route"]
    inv_rows = list_inventory_entities_sync()
    neighbors: list[dict[str, Any]] = []
    iid = route.get("inventory_match_id")
    if iid:
        neighbors = graph_neighbors_sync(iid)

    prior_stage = int(state.get("stage") or 0)
    max_stage = max(1, int(settings.max_investigation_stages or 3))
    if prior_stage <= 0:
        stage = 1
        reason = "initial"
    else:
        stage = min(prior_stage + 1, max_stage)
        reason = "confidence_escalation"

    token_by_stage = {
        1: int(settings.stage1_token_budget),
        2: int(settings.stage2_token_budget),
        3: int(settings.stage3_token_budget),
    }
    tool_calls_by_stage = {
        1: int(settings.stage1_tool_call_budget),
        2: int(settings.stage2_tool_call_budget),
        3: int(settings.stage3_tool_call_budget),
    }
    token_budget = token_by_stage.get(stage, token_by_stage[3])
    tool_call_budget = tool_calls_by_stage.get(stage, tool_calls_by_stage[3])

    staged = {
        "stage": stage,
        "reason": reason,
        "inventory_hits": [r for r in inv_rows if r.get("data", {}).get("service_name") == extracted.get("entity_name")],
        "graph_neighbors": neighbors[:20],
        "token_budget": token_budget,
        "tool_call_budget": tool_call_budget,
    }
    _log(state, "stage_context", {"staged_context": staged})
    return {"stage": stage, "staged_context": staged}


def node_invoke_worker(state: OpsState) -> dict[str, Any]:
    route = state["route"]
    extracted = state["extracted"]
    n = state["normalized"]
    inv = state["investigation_id"]
    url = route["worker_base_url"].rstrip("/") + "/investigate"
    staged = state.get("staged_context") or {}
    token_budget = int(staged.get("token_budget") or 3500)
    tool_call_budget = int(staged.get("tool_call_budget") or 8)
    req = WorkerInvestigateRequest(
        investigation_id=inv,
        stage=state.get("stage", 1),
        cluster_id=route.get("cluster_id"),
        credentials_ref=route.get("credentials_ref"),
        entity_type=extracted["entity_type"],
        entity_name=extracted["entity_name"],
        namespace=extracted.get("namespace"),
        alert_class=extracted.get("alert_class"),
        labels=extracted.get("labels") or {},
        compact_context={"staged": state.get("staged_context") or {}, "ingress": n},
        token_budget=token_budget,
        tool_call_budget=tool_call_budget,
    )
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, content=req.model_dump_json(), headers={"Content-Type": "application/json"})
        r.raise_for_status()
        body = r.json()
    _log(state, "invoke_worker", {"worker_id": route["worker_id"], "result": body})
    prior_results = list(state.get("worker_results") or [])
    return {"worker_results": [*prior_results, body]}


def node_merge(state: OpsState) -> dict[str, Any]:
    results = state.get("worker_results") or []
    merged = {
        "checked": [],
        "findings": [],
        "evidence_refs": [],
        "ruled_out": [],
        "confidence": 0.0,
        "next_suggested_check": None,
    }
    for w in results:
        merged["checked"].extend(w.get("checked") or [])
        merged["findings"].extend(w.get("findings") or [])
        merged["evidence_refs"].extend(w.get("evidence_refs") or [])
        merged["ruled_out"].extend(w.get("ruled_out") or [])
        merged["confidence"] = max(merged["confidence"], float(w.get("confidence") or 0.0))
        if w.get("next_suggested_check"):
            merged["next_suggested_check"] = w["next_suggested_check"]
    _log(state, "merge_findings", {"merged": merged})
    return {"merged": merged}


def node_confidence(state: OpsState) -> dict[str, Any]:
    conf = float((state.get("merged") or {}).get("confidence") or 0.0)
    high = float(settings.confidence_high_threshold)
    low = float(settings.confidence_low_threshold)
    stage = int(state.get("stage") or 1)
    max_stage = max(1, int(settings.max_investigation_stages or 3))
    if conf >= high:
        band = "high"
        escalate = False
    elif conf >= low:
        band = "medium"
        escalate = True
    else:
        band = "low"
        escalate = True
    if stage >= max_stage:
        escalate = False
    next_step = "stage_context" if escalate else "rca"
    _log(
        state,
        "confidence_gate",
        {
            "confidence": conf,
            "band": band,
            "escalate": escalate,
            "stage": stage,
            "max_stage": max_stage,
            "next_step": next_step,
        },
    )
    return {"confidence_band": band, "escalate": escalate}


def node_rca(state: OpsState) -> dict[str, Any]:
    merged = state.get("merged") or {}
    n = state.get("normalized") or {}
    extracted = state.get("extracted") or {}
    q_parts = [
        str(extracted.get("entity_type") or ""),
        str(extracted.get("entity_name") or ""),
        str(extracted.get("alert_class") or ""),
        " ".join((merged.get("findings") or [])[:3]),
    ]
    retrieval_query = " ".join(x for x in q_parts if x.strip())
    rag_context = retrieve_relevant_chunks_sync(
        retrieval_query,
        top_k=int(settings.rag_top_k),
        char_budget=int(settings.rag_char_budget),
    )
    chain = {
        "alert": n.get("raw"),
        "checks": merged.get("checked"),
        "root_signal": merged.get("findings"),
        "cause": merged.get("findings"),
        "supporting_refs": merged.get("evidence_refs"),
        "ruled_out": merged.get("ruled_out"),
        "institutional_context": rag_context,
    }
    rca = synthesize_rca(n, merged, chain)
    _log(
        state,
        "rca_synthesis",
        {
            "rca": rca,
            "rag_chunks_used": len(rag_context),
            "rag_char_budget": int(settings.rag_char_budget),
        },
    )
    return {"rca": rca, "rag_context": rag_context}


def node_await_approval(state: OpsState) -> dict[str, Any]:
    """Human gate before executor (AD-003). Uses LangGraph interrupt() when require_human_approval is on."""
    if settings.auto_approve_execute:
        _log(state, "await_approval_auto", {"granted": True})
        return {
            "approval": {
                "status": "auto_approved",
                "granted": True,
                "environment": settings.environment,
            }
        }
    if not settings.require_human_approval:
        _log(state, "await_approval_bypass", {"granted": True})
        return {
            "approval": {
                "status": "bypass_dev",
                "granted": True,
                "environment": settings.environment,
            }
        }

    from langgraph.types import interrupt

    payload = {
        "kind": "await_approval",
        "investigation_id": state.get("investigation_id"),
        "environment": settings.environment,
        "rca_summary": (state.get("rca") or {}).get("summary"),
        "confidence_band": state.get("confidence_band"),
    }
    decision = interrupt(payload)
    granted = False
    if isinstance(decision, dict):
        granted = bool(decision.get("granted"))
    _log(
        state,
        "await_approval_resolved",
        {"granted": granted, "environment": settings.environment},
    )
    return {
        "approval": {
            "status": "approved" if granted else "rejected",
            "granted": granted,
            "environment": settings.environment,
            "human": decision if isinstance(decision, dict) else {},
        }
    }


def node_executor(state: OpsState) -> dict[str, Any]:
    """Runs only when conditional routing allows (AD-003)."""
    ex_base = settings.executor_url
    plan = {
        "investigation_id": state.get("investigation_id"),
        "actions": [{"type": "noop", "detail": "stub executor milestone-1"}],
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{ex_base.rstrip('/')}/execute",
            content=json.dumps({"approved": True, "plan": plan}),
            headers={"Content-Type": "application/json"},
        )
        if r.status_code >= 400:
            _log(state, "executor_error", {"status_code": r.status_code, "body": r.text[:500]})
            return {"execution": {"status": "error", "code": r.status_code}}
        body = r.json()
    _log(state, "executor_completed", {"execution": body})
    return {"execution": body}


def route_after_approval(state: OpsState) -> str:
    """Conditional: only run executor when approval granted or auto in dev."""
    if settings.environment == "production" and not settings.auto_approve_execute:
        appr = state.get("approval") or {}
        if appr.get("granted"):
            return "executor"
        return "end"
    if settings.auto_approve_execute:
        return "executor"
    appr = state.get("approval") or {}
    if appr.get("granted"):
        return "executor"
    return "end"


def route_after_confidence(state: OpsState) -> str:
    """Escalate staged checks until confidence is high or stage cap is reached."""
    if bool(state.get("escalate")):
        return "stage_context"
    return "rca"
