"""POST /v1/investigations/run-planned — planner ingress (AD-015)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from fixops_controller.api import app as app_module
from fixops_controller.llm.planner import finalize_planned_normalized
from fixops_controller.settings import settings


@pytest.fixture
def _planner_api_env(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auto_approve_execute", False)
    monkeypatch.setattr(settings, "require_human_approval", True)
    monkeypatch.setattr(settings, "worker_obs_base_url", "http://worker.test")
    monkeypatch.setattr(settings, "executor_url", "http://executor.test")
    monkeypatch.setattr(
        settings, "routing_rules_path", str(repo_root / "config" / "routing_rules.yaml")
    )
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
def test_run_planned_nl_crash_maps_to_alert_shape(_planner_api_env, monkeypatch: pytest.MonkeyPatch):
    respx.post("http://worker.test/investigate").mock(
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
    monkeypatch.setattr(settings, "controller_api_key", None)
    with TestClient(app_module.app) as client:
        r = client.post(
            "/v1/investigations/run-planned",
            json={
                "thread_id": "plan-crash-1",
                "message": "PodCrashLoopBackOff on checkout pod in prod namespace",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["planning"]["planner_mode"] == "mock"
    n = body["planning"]["normalized"]
    assert n["source"] == "alert"
    assert n["raw"]["alertname"] == "PodCrashLoopBackOff"
    assert n["raw"]["namespace"] == "prod"
    assert body.get("status") in ("awaiting_approval", "completed")


@respx.mock
def test_run_planned_messy_payload_coerced(_planner_api_env, monkeypatch: pytest.MonkeyPatch):
    respx.post("http://worker.test/investigate").mock(
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
    monkeypatch.setattr(settings, "controller_api_key", None)
    messy = {
        "alertname": "HighCPU",
        "namespace": "staging",
        "pod": "api-1",
        "labels": {"entity_type": "pod"},
    }
    with TestClient(app_module.app) as client:
        r = client.post(
            "/v1/investigations/run-planned",
            json={"thread_id": "plan-messy", "payload": messy},
        )
    assert r.status_code == 200
    n = r.json()["planning"]["normalized"]
    assert n["source"] == "alert"
    assert n["raw"]["alertname"] == "HighCPU"
    assert n["raw"]["namespace"] == "staging"


@respx.mock
def test_run_planned_question_uses_query_path(_planner_api_env, monkeypatch: pytest.MonkeyPatch):
    respx.post("http://worker.test/investigate").mock(
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
    monkeypatch.setattr(settings, "controller_api_key", None)
    with TestClient(app_module.app) as client:
        r = client.post(
            "/v1/investigations/run-planned",
            json={
                "thread_id": "plan-q",
                "message": "how many pods are failing in monitoring namespace?",
            },
        )
    assert r.status_code == 200
    n = r.json()["planning"]["normalized"]
    assert n["source"] == "query"
    assert "session_id" in n["raw"]
    assert "synthetic_alert" in n["raw"]
    assert n["raw"]["synthetic_alert"]["entity_name"] == "cluster-query"


def test_run_planned_empty_body_422(_planner_api_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "controller_api_key", None)
    with TestClient(app_module.app) as client:
        r = client.post("/v1/investigations/run-planned", json={})
    assert r.status_code == 422


@respx.mock
def test_run_planned_respects_api_key(_planner_api_env, repo_root: Path, monkeypatch: pytest.MonkeyPatch):
    respx.post("http://worker.test/investigate").mock(
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
    monkeypatch.setattr(settings, "controller_api_key", "unit-test-secret")
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    with TestClient(app_module.app) as client:
        r = client.post(
            "/v1/investigations/run-planned",
            json={"thread_id": "plan-auth", "message": "crash", "payload": raw},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401
        r2 = client.post(
            "/v1/investigations/run-planned",
            json={"thread_id": "plan-auth-ok", "message": "PodCrashLoopBackOff in prod"},
            headers={"Authorization": "Bearer unit-test-secret"},
        )
        assert r2.status_code == 200


def test_finalize_rejects_unknown_source():
    with pytest.raises(ValueError, match="source"):
        finalize_planned_normalized({"source": "email", "raw": {}}, fallback_summary=None)
