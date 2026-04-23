from __future__ import annotations

from fixops_contract.models import (
    AlertPayload,
    InvestigationReport,
    WorkerInvestigationRequest,
)
from fixops_contract.ollama_json import OllamaJsonConfig

from controller.config import ControllerSettings
from controller.conclusion import build_conclusion
from controller.decision_log import append_report
from controller.interpretation import derive_root_cause_and_actions
from controller.router import route_worker
from controller.summary import build_summary_lines
from controller.worker_client import (
    WorkerK8sNotConfigured,
    call_worker_k8s,
)


def run_investigation(
    *,
    settings: ControllerSettings,
    alert: AlertPayload,
) -> InvestigationReport:
    worker_id = route_worker(alert)
    if worker_id != "worker-k8s":
        raise NotImplementedError(f"No worker implementation for {worker_id!r}")

    base = (settings.worker_k8s_base_url or "").strip()
    if not base:
        raise WorkerK8sNotConfigured(
            "Kubernetes worker is not configured: set CONTROLLER_WORKER_K8S_BASE_URL to the "
            "worker-k8s service base URL (for example http://127.0.0.1:8080). "
            "Without a reachable worker, Kubernetes issues cannot be investigated."
        )

    request = WorkerInvestigationRequest(alert=alert, stage=1)
    worker_out = call_worker_k8s(
        base_url=base,
        request=request,
        timeout_seconds=settings.worker_k8s_timeout_seconds,
    )

    ollama: OllamaJsonConfig | None = None
    if settings.llm_base_url and settings.llm_model:
        ollama = OllamaJsonConfig(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    try:
        summary_lines = build_summary_lines(
            ollama=ollama,
            alert=alert,
            worker_id=worker_id,
            worker_out=worker_out,
        )
    except Exception:
        summary_lines = build_summary_lines(
            ollama=None,
            alert=alert,
            worker_id=worker_id,
            worker_out=worker_out,
        )

    root_cause, action_items = derive_root_cause_and_actions(alert, worker_out)
    conclusion = build_conclusion(alert, worker_out)

    report = InvestigationReport(
        alert=alert,
        routed_worker=worker_id,
        worker=worker_out,
        summary_lines=summary_lines,
        root_cause_summary=root_cause,
        action_items=action_items,
        conclusion=conclusion,
    )
    append_report(settings.decision_log_path, report)
    return report
