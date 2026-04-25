"""Live checks against local Kubernetes credentials mapping in config/worker-k8s.yaml."""

from __future__ import annotations

import pytest
from fixops_contract.ad006 import WorkerInvestigateRequest
from fixops_contract.config_yaml import load_worker_k8s_yaml

from fixops_worker_k8s.logic import investigate
from fixops_worker_k8s.settings import settings

pytestmark = pytest.mark.integration


def test_k8s_worker_local_namespace_snapshot(monkeypatch: pytest.MonkeyPatch):
    cfg = load_worker_k8s_yaml()
    clusters = cfg.get("clusters") or {}
    if not clusters:
        pytest.skip("No clusters configured in config/worker-k8s.yaml")
    monkeypatch.setattr(settings, "clusters", clusters)
    monkeypatch.setattr(settings, "default_cluster_id", cfg.get("default_cluster_id") or "local")

    req = WorkerInvestigateRequest(
        investigation_id="live-k8s-1",
        entity_type="service",
        entity_name="cluster-query",
        namespace="monitoring",
        labels={"intent": "observability_question"},
    )
    out = investigate(req)
    # If RBAC is too narrow this may report no-access, which is still a valid explicit behavior.
    assert out.confidence >= 0.1
    assert len(out.checked) >= 1
