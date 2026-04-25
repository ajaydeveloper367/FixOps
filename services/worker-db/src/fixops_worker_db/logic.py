"""Database worker AD-006 stub for deterministic controller routing."""

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult


def investigate(req: WorkerInvestigateRequest) -> WorkerResult:
    namespace = req.namespace or "default"
    return WorkerResult(
        checked=[
            f"database symptom triage entity={req.entity_name}",
            f"namespace mapping check namespace={namespace}",
        ],
        findings=[
            "Database worker stub is reachable and returned AD-006 output.",
            f"Received labels={sorted((req.labels or {}).keys())}",
        ],
        evidence_refs=[
            f"db:entity:{req.entity_name}",
            f"db:namespace:{namespace}",
        ],
        ruled_out=[
            "No direct DB connector configured yet in this stub",
        ],
        confidence=0.56,
        next_suggested_check="Add SQL/NoSQL adapters for connection saturation, slow query, and lock diagnostics",
    )
