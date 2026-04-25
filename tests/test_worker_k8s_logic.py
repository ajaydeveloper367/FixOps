"""worker-k8s credentials mapping and pod summary behavior."""

from __future__ import annotations

from typing import Any

from fixops_contract.ad006 import WorkerInvestigateRequest

from fixops_worker_k8s.logic import investigate
from fixops_worker_k8s.settings import settings


class _FakeK8s:
    def __init__(self, pods: list[dict[str, Any]]) -> None:
        self._pods = pods

    def list_pods(self, namespace: str) -> list[dict[str, Any]]:
        return self._pods

    def read_pod(self, namespace: str, name: str) -> dict[str, Any] | None:
        for p in self._pods:
            if p.get("name") == name:
                return p
        return None


def test_investigate_missing_credentials(monkeypatch) -> None:
    monkeypatch.setattr(settings, "default_cluster_id", "local")
    monkeypatch.setattr(settings, "clusters", {})
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="service",
        entity_name="cluster-query",
        namespace="monitoring",
    )
    out = investigate(req, adapter_factory=lambda _: _FakeK8s([]))
    assert out.confidence <= 0.2
    assert "No credentials configured" in out.findings[0]


def test_investigate_rbac_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "default_cluster_id", "local")
    monkeypatch.setattr(settings, "clusters", {"local": {"kubeconfig_path": "~/.kube/config"}})
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="service",
        entity_name="cluster-query",
        namespace="monitoring",
    )

    def _raise(_creds: dict[str, str]):
        raise Exception("403 Forbidden")

    out = investigate(req, adapter_factory=_raise)
    assert out.confidence == 0.2
    assert "No access" in out.findings[0]


def test_investigate_counts_running_and_failing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "default_cluster_id", "local")
    monkeypatch.setattr(settings, "clusters", {"local": {"kubeconfig_path": "~/.kube/config"}})
    pods = [
        {"name": "a", "phase": "Running", "restart_count": 0, "waiting_reasons": []},
        {"name": "b", "phase": "Pending", "restart_count": 0, "waiting_reasons": []},
        {"name": "c", "phase": "Running", "restart_count": 1, "waiting_reasons": ["CrashLoopBackOff"]},
    ]
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="service",
        entity_name="cluster-query",
        namespace="monitoring",
    )
    out = investigate(req, adapter_factory=lambda _: _FakeK8s(pods))
    text = " ".join(out.findings)
    assert "total pods=3" in text
    assert "running=2" in text
    assert "failing=1" in text
    assert any("CrashLoopBackOff" in f for f in out.findings)
