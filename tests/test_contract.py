"""AD-006 wire contract validation."""

import pytest
from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult
from pydantic import ValidationError


def test_worker_result_roundtrip():
    w = WorkerResult(
        checked=["prometheus instant query: up"],
        findings=["Found 1 series"],
        evidence_refs=["prom:query:up"],
        ruled_out=[],
        confidence=0.82,
        next_suggested_check=None,
    )
    j = w.model_dump()
    w2 = WorkerResult.model_validate(j)
    assert w2.confidence == 0.82


def test_worker_result_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        WorkerResult(confidence=1.5, checked=[], findings=[], evidence_refs=[], ruled_out=[])


def test_investigate_request_refs_only():
    r = WorkerInvestigateRequest(
        investigation_id="inv-1",
        entity_type="service",
        entity_name="checkout-api",
        credentials_ref="ref:dev-eks",
        cluster_id="dev-eks",
    )
    assert r.credentials_ref == "ref:dev-eks"
    assert "kubeconfig" not in r.model_dump_json()
