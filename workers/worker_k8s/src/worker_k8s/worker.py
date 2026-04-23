from __future__ import annotations

from typing import Any

from fixops_contract.models import (
    AlertPayload,
    WorkerInvestigationRequest,
    WorkerResponse,
)
from fixops_contract.ollama_json import OllamaJsonConfig

from worker_k8s.adapters.kubernetes_api import KubernetesApiAdapter, PodSnapshot
from worker_k8s.cluster_map import (
    ClusterKubeCredentials,
    format_known_cluster_ids,
    load_cluster_credentials_map,
)
from worker_k8s.config import WorkerK8sSettings
from worker_k8s.container_pick import (
    alert_suggests_log_evidence,
    infer_container_name,
    should_pull_logs,
)
from worker_k8s.datasource_cm_scan import scan_grafana_datasource_defaults
from worker_k8s.synthesis import (
    build_facts_bundle,
    deterministic_response,
    llm_response,
)


class K8sWorker:
    """Domain worker: gathers facts via adapter, returns structured contract."""

    def __init__(self, settings: WorkerK8sSettings | None = None) -> None:
        self._settings = settings or WorkerK8sSettings()
        self._cluster_map: dict[str, ClusterKubeCredentials] | None = None
        if self._settings.cluster_map_path:
            self._cluster_map = load_cluster_credentials_map(
                self._settings.cluster_map_path
            )

    def _build_k8s_adapter(
        self, alert: AlertPayload
    ) -> tuple[KubernetesApiAdapter | None, str | None]:
        """
        Build an isolated API client for this alert. Caller must ``adapter.close()``.

        If ``WORKER_K8S_CLUSTER_MAP_PATH`` is set, ``alert.cluster_id`` selects
        kubeconfig + context from the map. Otherwise the worker uses global
        ``WORKER_K8S_KUBECONFIG`` / ``WORKER_K8S_KUBE_CONTEXT`` (single-cluster).
        """
        if self._cluster_map is not None:
            cid = (alert.cluster_id or "").strip()
            if not cid:
                return None, (
                    "Worker is configured with WORKER_K8S_CLUSTER_MAP_PATH (multi-cluster). "
                    "Set `cluster_id` on the alert to match a key under `clusters:` in that file."
                )
            cred = self._cluster_map.get(cid)
            if cred is None:
                known = format_known_cluster_ids(self._cluster_map)
                return None, (
                    f"Unknown cluster_id={cid!r}. Known ids: {known}. "
                    "Fix the alert or extend the cluster map YAML."
                )
            return (
                KubernetesApiAdapter(
                    kubeconfig=str(cred.kubeconfig),
                    context=cred.context,
                ),
                None,
            )

        kube_path = str(self._settings.kubeconfig) if self._settings.kubeconfig else None
        return (
            KubernetesApiAdapter(
                kubeconfig=kube_path,
                context=self._settings.kube_context,
            ),
            None,
        )

    def investigate(self, request: WorkerInvestigationRequest) -> WorkerResponse:
        alert = request.alert
        if not alert.namespace:
            return WorkerResponse(
                contract_version=request.contract_version,
                checked=[],
                findings=["Alert missing `namespace`; cannot query the cluster."],
                evidence_refs=[],
                ruled_out=[],
                confidence=0.2,
                next_suggested_check="Provide namespace in the alert payload.",
            )

        k8s, map_err = self._build_k8s_adapter(alert)
        if map_err or k8s is None:
            return WorkerResponse(
                contract_version=request.contract_version,
                checked=[],
                findings=[map_err or "Could not build Kubernetes client."],
                evidence_refs=[],
                ruled_out=[],
                confidence=0.15,
                next_suggested_check="Fix cluster_id / cluster map or kube settings.",
            )
        try:
            return self._investigate_with_adapter(request, k8s)
        finally:
            k8s.close()

    def _investigate_with_adapter(
        self,
        request: WorkerInvestigationRequest,
        k8s: KubernetesApiAdapter,
    ) -> WorkerResponse:
        alert = request.alert

        pod_snap: PodSnapshot | None = None
        deployment: dict[str, Any] | None = None
        name_sub: str | None = None

        if alert.entity_type == "pod" and alert.name:
            pod_snap = k8s.read_pod(alert.namespace, alert.name)
            name_sub = alert.name
        elif alert.entity_type == "deployment" and alert.name:
            deployment = k8s.read_deployment(alert.namespace, alert.name)
            name_sub = alert.name
        else:
            # Best-effort: if a name is present, try pod then deployment
            if alert.name:
                pod_snap = k8s.read_pod(alert.namespace, alert.name)
                if not pod_snap.exists:
                    deployment = k8s.read_deployment(alert.namespace, alert.name)
                name_sub = alert.name

        events = k8s.list_recent_events(
            alert.namespace,
            for_name_substring=name_sub,
        )

        pod_logs: dict[str, dict[str, str]] = {}
        pull_logs = (pod_snap and pod_snap.exists) and (
            should_pull_logs(pod_snap) or alert_suggests_log_evidence(alert)
        )
        if pull_logs:
            cname = infer_container_name(alert, pod_snap)
            if cname:
                prev = k8s.read_pod_container_log(
                    alert.namespace,
                    pod_snap.name,
                    cname,
                    previous=True,
                    tail_lines=160,
                )
                cur = k8s.read_pod_container_log(
                    alert.namespace,
                    pod_snap.name,
                    cname,
                    previous=False,
                    tail_lines=200,
                )
                pod_logs[cname] = {
                    "previous": (prev or "").strip(),
                    "current": (cur or "").strip(),
                }

        base = deterministic_response(
            alert=alert,
            pod=pod_snap,
            deployment=deployment,
            events=events,
            pod_logs=pod_logs or None,
        )

        cm_extra_findings: list[str] = []
        cm_extra_checked: list[str] = []
        if pod_snap and pod_snap.exists and pod_logs:
            cmerge = infer_container_name(alert, pod_snap)
            if cmerge and pod_logs.get(cmerge):
                blob = (pod_logs[cmerge].get("previous") or "") + "\n" + (
                    pod_logs[cmerge].get("current") or ""
                )
                cm_extra_findings, cm_extra_checked = scan_grafana_datasource_defaults(
                    k8s,
                    namespace=alert.namespace,
                    pod_name=pod_snap.name,
                    container_name=cmerge,
                    log_blob=blob,
                )
                if cm_extra_findings or cm_extra_checked:
                    base = base.model_copy(
                        update={
                            "findings": [*base.findings, *cm_extra_findings],
                            "checked": [*base.checked, *cm_extra_checked],
                            "evidence_refs": [*base.evidence_refs, *cm_extra_checked],
                            "confidence": min(1.0, max(base.confidence, 0.92)),
                        }
                    )

        facts = build_facts_bundle(
            alert=alert,
            pod=pod_snap,
            deployment=deployment,
            events=events,
            pod_logs=pod_logs or None,
        )
        if cm_extra_findings:
            facts = {**facts, "datasource_cm_findings": cm_extra_findings}

        if self._settings.llm_base_url and self._settings.llm_model:
            ollama = OllamaJsonConfig(
                base_url=self._settings.llm_base_url,
                model=self._settings.llm_model,
                timeout_seconds=self._settings.llm_timeout_seconds,
            )
            try:
                return llm_response(ollama=ollama, facts=facts)
            except Exception:
                # LLM optional: transport, JSON, or schema drift should not fail the run
                return base

        return base
