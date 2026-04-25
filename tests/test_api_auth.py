"""Optional ``controller_api_key`` gates run / resume / snapshot."""

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
    monkeypatch.setattr(settings, "worker_k8s_base_url", "http://worker.test")
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
def test_run_without_key_when_api_key_unset(_api_hitl_env, repo_root: Path, monkeypatch: pytest.MonkeyPatch):
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
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    with TestClient(app_module.app) as client:
        r = client.post("/v1/investigations/run", json={"thread_id": "auth-off", "normalized": raw})
        assert r.status_code == 200


@respx.mock
def test_run_accepts_bearer_or_x_api_key_when_api_key_set(
    _api_hitl_env, repo_root: Path, monkeypatch: pytest.MonkeyPatch
):
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
        r = client.post("/v1/investigations/run", json={"thread_id": "auth-on", "normalized": raw})
        assert r.status_code == 401

        r_bad = client.post(
            "/v1/investigations/run",
            json={"thread_id": "auth-bad", "normalized": raw},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r_bad.status_code == 401

        r2 = client.post(
            "/v1/investigations/run",
            json={"thread_id": "auth-bearer", "normalized": raw},
            headers={"Authorization": "Bearer unit-test-secret"},
        )
        assert r2.status_code == 200

        r3 = client.post(
            "/v1/investigations/run",
            json={"thread_id": "auth-header", "normalized": raw},
            headers={"X-API-Key": "unit-test-secret"},
        )
        assert r3.status_code == 200
