"""worker-obs Prometheus candidate queries and fallback investigate path."""

from __future__ import annotations

from typing import Any

import pytest

from fixops_contract.ad006 import WorkerInvestigateRequest

from fixops_worker_obs.logic import _instant_query_candidates, investigate


def test_candidates_service_single_job() -> None:
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="service",
        entity_name="checkout-api",
        namespace="prod",
    )
    assert _instant_query_candidates(req) == ['up{job="checkout-api"}']


def test_candidates_pod_namespace_app_then_fallbacks() -> None:
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="pod",
        entity_name="checkout-api-7d8f9",
        namespace="prod",
        labels={"app": "checkout-api"},
    )
    q = _instant_query_candidates(req)
    assert q[0] == 'up{namespace="prod"}'
    assert 'up{job="checkout-api"}' in q
    assert 'up{namespace="prod",job="checkout-api"}' in q
    assert 'up{namespace="default"}' in q
    assert q[-1] == "count(up)"


def test_candidates_pod_default_namespace_skips_default_dup() -> None:
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="pod",
        entity_name="x",
        namespace="default",
        labels={},
    )
    q = _instant_query_candidates(req)
    assert q[0] == 'up{namespace="default"}'
    assert q.count('up{namespace="default"}') == 1
    assert q[-1] == "count(up)"


class _FakeProm:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self._i = 0
        self.seen: list[str] = []

    def query_instant(self, expr: str) -> dict[str, Any]:
        self.seen.append(expr)
        if self._i >= len(self.responses):
            return self.responses[-1]
        r = self.responses[self._i]
        self._i += 1
        return r


def test_investigate_uses_fallback_when_primary_empty() -> None:
    one_series = {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"metric": {"job": "x"}, "value": [1, "1"]}]},
    }
    empty = {"status": "success", "data": {"resultType": "vector", "result": []}}
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="pod",
        entity_name="pod-a",
        namespace="prod",
        labels={"app": "myapp"},
    )
    # Primary + job selectors empty, default namespace hits
    fake = _FakeProm([empty, empty, empty, one_series])
    out = investigate(req, fake)
    assert "fallback" in " ".join(out.findings).lower() or "fallback selector" in out.findings[0].lower()
    assert out.confidence == 0.72
    assert len(fake.seen) >= 4


def test_investigate_monitoring_pod_hits_namespace_selector_first() -> None:
    """When ``up{namespace=\"monitoring\"}`` returns data, confidence is high (first match)."""
    one_series = {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"metric": {"job": "node-exporter"}, "value": [1, "1"]}]},
    }
    req = WorkerInvestigateRequest(
        investigation_id="i-mon",
        entity_type="pod",
        entity_name="monitoring-prometheus-node-exporter-6lwrb",
        namespace="monitoring",
        labels={"entity_type": "pod", "app": "node-exporter"},
    )
    fake = _FakeProm([one_series])
    out = investigate(req, fake)
    assert fake.seen[0] == 'up{namespace="monitoring"}'
    assert out.confidence == 0.82
    assert "Found 1 series for selector" in out.findings[0]


def test_investigate_count_up_last_resort() -> None:
    empty = {"status": "success", "data": {"resultType": "vector", "result": []}}
    count_vec = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [1, "3"]}],
        },
    }
    req = WorkerInvestigateRequest(
        investigation_id="i1",
        entity_type="pod",
        entity_name="orphan",
        namespace="ghost-ns",
        labels={},
    )
    # All up{...} empty until count(up)
    n = len(_instant_query_candidates(req))
    fakes = [empty] * (n - 1) + [count_vec]
    fake = _FakeProm(fakes)
    out = investigate(req, fake)
    assert fake.seen[-1] == "count(up)"
    assert "count(up)" in out.findings[0] or "count(up)" in " ".join(out.findings)
    assert out.confidence == 0.62
