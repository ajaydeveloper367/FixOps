"""LangGraph smoke — mocked worker HTTP + no real Postgres."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from fixops_controller.graph.build import build_compiled_graph
from fixops_controller.settings import settings


@pytest.fixture
def graph_mocks(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auto_approve_execute", False)
    monkeypatch.setattr(settings, "require_human_approval", False)
    monkeypatch.setattr(settings, "worker_obs_base_url", "http://worker.test")
    monkeypatch.setattr(settings, "worker_k8s_base_url", "http://worker.test")
    monkeypatch.setattr(settings, "executor_url", "http://executor.test")
    monkeypatch.setattr(settings, "routing_rules_path", str(repo_root / "config" / "routing_rules.yaml"))

    monkeypatch.setattr("fixops_controller.graph.nodes.append_decision_sync", lambda *a, **k: None)
    monkeypatch.setattr(
        "fixops_controller.graph.nodes.list_inventory_entities_sync",
        lambda: [
            {
                "id": "service:checkout-api",
                "entity_type": "service",
                "data": {
                    "service_name": "checkout-api",
                    "cluster_id": "dev-eks",
                    "credentials_ref": "ref:dev-eks",
                },
            }
        ],
    )
    monkeypatch.setattr("fixops_controller.graph.nodes.graph_neighbors_sync", lambda _eid: [])


@respx.mock
def test_graph_alert_fixture(graph_mocks, repo_root: Path):
    respx.post("http://worker.test/investigate").mock(
        return_value=httpx.Response(
            200,
            json={
                "checked": ["prometheus instant query: up{job=\"checkout-api\"}"],
                "findings": ["Found 1 series for selector"],
                "evidence_refs": ["prom:query:up{job=\"checkout-api\"}"],
                "ruled_out": [],
                "confidence": 0.82,
                "next_suggested_check": None,
            },
        )
    )
    respx.post("http://executor.test/execute").mock(
        return_value=httpx.Response(200, json={"status": "accepted", "executed": []}),
    )
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    g = build_compiled_graph()
    out = g.invoke({"normalized": raw}, config={"configurable": {"thread_id": "test-alert"}})
    assert out["route"]["worker_id"] == "worker-obs"
    assert out["merged"]["confidence"] >= 0.82
    assert "rca" in out


@respx.mock
def test_graph_query_intent_fixture(graph_mocks, repo_root: Path):
    respx.post("http://worker.test/investigate").mock(
        return_value=httpx.Response(
            200,
            json={
                "checked": ["prometheus"],
                "findings": ["ok"],
                "evidence_refs": ["e1"],
                "ruled_out": [],
                "confidence": 0.9,
                "next_suggested_check": None,
            },
        )
    )
    respx.post("http://executor.test/execute").mock(
        return_value=httpx.Response(200, json={"status": "accepted", "executed": []}),
    )
    intent = json.loads((repo_root / "fixtures" / "query_intent.json").read_text())
    normalized = {
        "source": "query",
        "environment": "development",
        "raw": intent,
        "session_id": intent["session_id"],
    }
    g = build_compiled_graph()
    out = g.invoke({"normalized": normalized}, config={"configurable": {"thread_id": "test-query"}})
    assert out["extracted"]["entity_name"] == "checkout-api"
    assert out["route"]["worker_id"] == "worker-obs"


@respx.mock
def test_graph_escalates_until_stage_cap_when_confidence_not_high(graph_mocks, repo_root: Path):
    # Medium confidence (< high threshold) should trigger staged re-checks until max stage.
    respx.post("http://worker.test/investigate").mock(
        return_value=httpx.Response(
            200,
            json={
                "checked": ["prometheus instant query: up{job=\"checkout-api\"}"],
                "findings": ["Found 1 series for selector"],
                "evidence_refs": ["prom:query:up{job=\"checkout-api\"}"],
                "ruled_out": [],
                "confidence": 0.72,
                "next_suggested_check": "re-check with broader context",
            },
        )
    )
    respx.post("http://executor.test/execute").mock(
        return_value=httpx.Response(200, json={"status": "accepted", "executed": []}),
    )
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    g = build_compiled_graph()
    out = g.invoke({"normalized": raw}, config={"configurable": {"thread_id": "test-escalate"}})
    assert out["stage"] == settings.max_investigation_stages
    assert len(out["worker_results"]) == settings.max_investigation_stages
    assert out["confidence_band"] in {"medium", "low"}


@respx.mock
def test_graph_sends_credentials_ref_only_to_worker(graph_mocks, repo_root: Path):
    route = respx.post("http://worker.test/investigate").mock(
        return_value=httpx.Response(
            200,
            json={
                "checked": ["x"],
                "findings": ["ok"],
                "evidence_refs": ["e1"],
                "ruled_out": [],
                "confidence": 0.9,
                "next_suggested_check": None,
            },
        )
    )
    respx.post("http://executor.test/execute").mock(
        return_value=httpx.Response(200, json={"status": "accepted", "executed": []}),
    )
    raw = {
        "source": "alert",
        "environment": "development",
        "raw": {
            "alertname": "HighErrorRate",
            "service": "checkout-api",
            "namespace": "prod",
            "labels": {"entity_type": "service"},
        },
    }
    g = build_compiled_graph()
    g.invoke({"normalized": raw}, config={"configurable": {"thread_id": "test-creds-ref"}})
    req_body = json.loads(route.calls[0].request.content.decode())
    assert req_body["credentials_ref"] == "ref:dev-eks"
    assert "kubeconfig_path" not in json.dumps(req_body)
