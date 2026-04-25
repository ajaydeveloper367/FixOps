"""Human-in-the-loop: interrupt at await_approval + Command(resume)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from fixops_controller.api.graph_invoke import invoke_or_interrupt as invoke_fn
from fixops_controller.api.graph_invoke import resume_thread as resume_fn
from fixops_controller.graph.build import build_compiled_graph
from fixops_controller.settings import settings


@pytest.fixture
def hitl_mocks(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auto_approve_execute", False)
    monkeypatch.setattr(settings, "require_human_approval", True)
    monkeypatch.setattr(settings, "worker_obs_base_url", "http://worker.test")
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
def test_hitl_interrupt_then_resume_granted_executes(hitl_mocks, repo_root: Path):
    respx.post("http://worker.test/investigate").mock(
        return_value=httpx.Response(
            200,
            json={
                "checked": ["prometheus"],
                "findings": ["Found 1 series for selector"],
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
    g = build_compiled_graph()
    cfg = {"configurable": {"thread_id": "hitl-1"}}
    first = invoke_fn(g, {"normalized": raw}, cfg)
    assert first["status"] == "awaiting_approval"
    assert first["interrupts"][0]["value"]["kind"] == "await_approval"
    assert "rca" in first["state"]

    second = resume_fn(g, {"granted": True}, cfg)
    assert second["status"] == "completed"
    assert second["state"]["approval"]["granted"] is True
    assert second["state"].get("execution") is not None


@respx.mock
def test_hitl_resume_denied_skips_executor(hitl_mocks, repo_root: Path):
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
    raw = json.loads((repo_root / "fixtures" / "alert_pod_crash.json").read_text())
    g = build_compiled_graph()
    cfg = {"configurable": {"thread_id": "hitl-2"}}
    first = invoke_fn(g, {"normalized": raw}, cfg)
    assert first["status"] == "awaiting_approval"

    second = resume_fn(g, {"granted": False}, cfg)
    assert second["status"] == "completed"
    assert second["state"]["approval"]["granted"] is False
    assert second["state"].get("execution") is None
