"""HTTP resume guard: only allow POST .../resume when the graph has a pending interrupt."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from fixops_controller.api import app as app_module
from fixops_controller.settings import settings


@pytest.fixture
def _api_hitl_env(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
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


@pytest.fixture
def _api_no_hitl_env(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auto_approve_execute", False)
    monkeypatch.setattr(settings, "require_human_approval", False)
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


def _worker_and_executor_mocks() -> None:
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


@respx.mock
def test_api_resume_after_awaiting_approval(_api_hitl_env, repo_root: Path):
    _worker_and_executor_mocks()
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    with TestClient(app_module.app) as client:
        r1 = client.post("/v1/investigations/run", json={"thread_id": "api-hil-1", "normalized": raw})
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["status"] == "awaiting_approval"

        r2 = client.post(
            "/v1/threads/api-hil-1/resume",
            json={"resume": {"granted": True, "approved_by": "pytest"}},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["status"] == "completed"
        assert body2["state"]["approval"]["granted"] is True


@respx.mock
def test_api_resume_rejected_when_run_completed_without_interrupt(_api_no_hitl_env, repo_root: Path):
    _worker_and_executor_mocks()
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    with TestClient(app_module.app) as client:
        r1 = client.post("/v1/investigations/run", json={"thread_id": "api-no-hil", "normalized": raw})
        assert r1.status_code == 200
        assert r1.json()["status"] == "completed"

        r2 = client.post(
            "/v1/threads/api-no-hil/resume",
            json={"resume": {"granted": True}},
        )
        assert r2.status_code == 400
        assert "No pending" in r2.json()["detail"]


@respx.mock
def test_api_resume_unknown_thread_returns_400(_api_hitl_env):
    _worker_and_executor_mocks()
    with TestClient(app_module.app) as client:
        r = client.post(
            "/v1/threads/never-started-thread/resume",
            json={"resume": {"granted": True}},
        )
        assert r.status_code == 400
        assert "No pending" in r.json()["detail"]


@respx.mock
def test_api_second_resume_returns_400(_api_hitl_env, repo_root: Path):
    _worker_and_executor_mocks()
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    with TestClient(app_module.app) as client:
        r1 = client.post("/v1/investigations/run", json={"thread_id": "api-hil-2", "normalized": raw})
        assert r1.status_code == 200
        assert r1.json()["status"] == "awaiting_approval"

        r2 = client.post("/v1/threads/api-hil-2/resume", json={"resume": {"granted": True}})
        assert r2.status_code == 200

        r3 = client.post("/v1/threads/api-hil-2/resume", json={"resume": {"granted": True}})
        assert r3.status_code == 400
        assert "No pending" in r3.json()["detail"]
