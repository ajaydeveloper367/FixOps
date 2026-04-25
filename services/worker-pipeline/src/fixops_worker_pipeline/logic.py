"""Pipeline worker AD-006 stub for deterministic controller routing."""

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult


def investigate(req: WorkerInvestigateRequest) -> WorkerResult:
    stage = int(req.stage or 1)
    return WorkerResult(
        checked=[
            f"pipeline metadata check entity={req.entity_name}",
            f"pipeline stage-specific heuristic stage={stage}",
        ],
        findings=[
            "Pipeline worker stub is reachable and returned a structured response.",
            f"Alert class={req.alert_class!r} routed to worker-pipeline.",
        ],
        evidence_refs=[
            f"pipeline:entity:{req.entity_name}",
            f"pipeline:stage:{stage}",
        ],
        ruled_out=[
            "No direct pipeline connector configured yet in this stub",
        ],
        confidence=0.55,
        next_suggested_check="Add Airflow/Kafka adapter calls for job status, retries, and upstream dependency failures",
    )
