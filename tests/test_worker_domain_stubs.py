"""AD-006 stubs for pipeline/db/app workers return structured responses."""

from fixops_contract.ad006 import WorkerInvestigateRequest

from fixops_worker_app_rca.logic import investigate as app_investigate
from fixops_worker_db.logic import investigate as db_investigate
from fixops_worker_pipeline.logic import investigate as pipeline_investigate


def _req(alert_class: str) -> WorkerInvestigateRequest:
    return WorkerInvestigateRequest(
        investigation_id="stub-1",
        stage=1,
        entity_type="service",
        entity_name="checkout-api",
        namespace="prod",
        alert_class=alert_class,
        labels={"app": "checkout-api"},
    )


def test_pipeline_stub_contract() -> None:
    out = pipeline_investigate(_req("PipelineFailure"))
    assert out.confidence >= 0.0
    assert out.checked
    assert out.findings
    assert out.evidence_refs


def test_db_stub_contract() -> None:
    out = db_investigate(_req("DatabaseLatency"))
    assert out.confidence >= 0.0
    assert out.checked
    assert out.findings
    assert out.evidence_refs


def test_app_rca_stub_contract() -> None:
    out = app_investigate(_req("AppRegression"))
    assert out.confidence >= 0.0
    assert out.checked
    assert out.findings
    assert out.evidence_refs
