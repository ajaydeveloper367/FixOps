"""Application RCA worker AD-006 stub for deterministic controller routing."""

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult


def investigate(req: WorkerInvestigateRequest) -> WorkerResult:
    alert_class = req.alert_class or "unknown"
    return WorkerResult(
        checked=[
            f"application symptom interpretation entity={req.entity_name}",
            f"alert class mapping alert_class={alert_class}",
        ],
        findings=[
            "App RCA worker stub is reachable and returned structured findings.",
            "Initial hypothesis: application-level regression or configuration drift should be checked next.",
        ],
        evidence_refs=[
            f"app:entity:{req.entity_name}",
            f"app:alert_class:{alert_class}",
        ],
        ruled_out=[
            "No code/config repository adapter configured yet in this stub",
        ],
        confidence=0.54,
        next_suggested_check="Add git/config adapters to compare recent deploy diffs and runtime config deltas",
    )
