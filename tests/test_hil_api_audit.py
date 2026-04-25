"""HTTP POST /resume writes ``hil_api_resume`` row to ``decision_log`` (AD-003 audit)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from fixops_controller.api import app as app_module
from fixops_controller.db.models import DecisionLogEntry
from fixops_controller.db.sync_session import SyncSessionLocal
from fixops_controller.settings import settings


@pytest.fixture
def _api_hitl_with_db_audit(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    """HIL + mocked HTTP workers; real ``append_decision_sync`` (ephemeral SQLite from conftest)."""
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
def test_resume_persists_hil_api_audit_row(_api_hitl_with_db_audit, repo_root: Path):
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
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    tid = "audit-hil-1"
    with TestClient(app_module.app) as client:
        r1 = client.post("/v1/investigations/run", json={"thread_id": tid, "normalized": raw})
        assert r1.status_code == 200
        inv = r1.json()["state"]["investigation_id"]

        r2 = client.post(
            f"/v1/threads/{tid}/resume",
            json={"resume": {"granted": True, "approved_by": "audit-test"}},
        )
        assert r2.status_code == 200

    with SyncSessionLocal() as s:
        row = s.scalars(
            select(DecisionLogEntry)
            .where(DecisionLogEntry.step == "hil_api_resume")
            .where(DecisionLogEntry.investigation_id == inv)
            .order_by(DecisionLogEntry.id.desc())
        ).first()
    assert row is not None
    assert row.payload["thread_id"] == tid
    assert row.payload["resume"]["granted"] is True
    assert row.payload["resume"]["approved_by"] == "audit-test"
    assert row.payload["graph_status"] == "completed"
