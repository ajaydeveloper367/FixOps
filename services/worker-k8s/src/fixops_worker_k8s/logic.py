"""Kubernetes worker logic with local credentials map keyed by cluster_id."""

from __future__ import annotations

from typing import Any, Callable

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult

from fixops_worker_k8s.adapters.kubernetes import KubernetesPort, build_kubernetes_adapter
from fixops_worker_k8s.settings import settings


def _resolve_cluster_id(req: WorkerInvestigateRequest) -> str | None:
    cid = (req.cluster_id or "").strip()
    if cid:
        return cid
    # Allow labels override from planner if provided.
    label_cid = str((req.labels or {}).get("cluster_id") or "").strip()
    if label_cid:
        return label_cid
    default_cid = str(settings.default_cluster_id or "").strip()
    return default_cid or None


def _namespace(req: WorkerInvestigateRequest) -> str:
    return (req.namespace or "").strip() or "default"


def _rbac_result(req: WorkerInvestigateRequest, cluster_id: str, namespace: str, detail: str) -> WorkerResult:
    return WorkerResult(
        checked=[f"kubernetes auth check cluster={cluster_id} namespace={namespace}"],
        findings=[
            (
                f"No access for cluster_id={cluster_id!r} in namespace={namespace!r}. "
                "The configured credentials are not authorized for this query."
            )
        ],
        evidence_refs=[f"k8s:authz:{cluster_id}:{namespace}"],
        ruled_out=[detail],
        confidence=0.2,
        next_suggested_check="Grant RBAC for list/get pods in this namespace or use another credentials mapping",
    )


def _no_credentials_result(req: WorkerInvestigateRequest, cluster_id: str | None) -> WorkerResult:
    wanted = cluster_id or "<missing>"
    return WorkerResult(
        checked=["cluster credentials resolution"],
        findings=[
            (
                f"No credentials configured for cluster_id={wanted!r}. "
                "Worker stores creds locally and maps by cluster_id."
            )
        ],
        evidence_refs=[f"k8s:credentials:{wanted}"],
        ruled_out=[],
        confidence=0.1,
        next_suggested_check="Add this cluster_id under config/worker-k8s.yaml clusters map",
    )


def _summarize_pods(pods: list[dict[str, Any]]) -> tuple[int, int, int]:
    running = 0
    failing = 0
    crashloop = 0
    for p in pods:
        phase = str(p.get("phase") or "")
        if phase == "Running":
            running += 1
        elif phase in {"Pending", "Failed", "Unknown"}:
            failing += 1
        reasons = {str(r) for r in (p.get("waiting_reasons") or [])}
        if "CrashLoopBackOff" in reasons:
            crashloop += 1
    return running, failing, crashloop


def investigate(
    req: WorkerInvestigateRequest,
    adapter_factory: Callable[[dict[str, str]], KubernetesPort] = build_kubernetes_adapter,
) -> WorkerResult:
    cluster_id = _resolve_cluster_id(req)
    if not cluster_id:
        return _no_credentials_result(req, None)
    creds = (settings.clusters or {}).get(cluster_id)
    if not creds:
        return _no_credentials_result(req, cluster_id)

    namespace = _namespace(req)
    checked: list[str] = [
        f"kubernetes list pods namespace={namespace} cluster={cluster_id}",
    ]
    evidence: list[str] = [f"k8s:pods:list:{cluster_id}:{namespace}"]
    ruled_out: list[str] = []

    try:
        api = adapter_factory(creds)
        pods = api.list_pods(namespace)
    except FileNotFoundError:
        return WorkerResult(
            checked=["kubernetes credentials load"],
            findings=[f"Credentials file not found for cluster_id={cluster_id!r}"],
            evidence_refs=[f"k8s:credentials:file_missing:{cluster_id}"],
            ruled_out=[],
            confidence=0.1,
            next_suggested_check="Fix kubeconfig_path for this cluster_id in worker-k8s config",
        )
    except Exception as e:
        # Keep explicit messaging for common RBAC/Auth patterns from Kubernetes ApiException text.
        s = str(e)
        if "403" in s or "Forbidden" in s or "401" in s or "Unauthorized" in s:
            return _rbac_result(req, cluster_id, namespace, s)
        return WorkerResult(
            checked=checked,
            findings=[f"Kubernetes API error for cluster_id={cluster_id!r}: {s}"],
            evidence_refs=evidence,
            ruled_out=ruled_out,
            confidence=0.3,
            next_suggested_check="Check cluster connectivity, kubeconfig context, and API server reachability",
        )

    if not pods:
        ruled_out.append(f"No pods found in namespace={namespace!r}")
        return WorkerResult(
            checked=checked,
            findings=[f"No pods found in namespace {namespace!r} on cluster {cluster_id!r}"],
            evidence_refs=evidence,
            ruled_out=ruled_out,
            confidence=0.5,
            next_suggested_check="Verify namespace name and cluster mapping for this request",
        )

    running, failing, crashloop = _summarize_pods(pods)
    findings = [
        f"Namespace {namespace!r} on cluster {cluster_id!r}: total pods={len(pods)}, running={running}, failing={failing}",
    ]
    if crashloop > 0:
        findings.append(f"Detected {crashloop} pod(s) with waiting reason CrashLoopBackOff")
    else:
        ruled_out.append(f"No pods in CrashLoopBackOff in namespace {namespace!r} (current check)")

    if req.entity_type == "pod" and req.entity_name and req.entity_name not in {"unknown", "cluster-query"}:
        checked.append(f"kubernetes get pod name={req.entity_name} namespace={namespace} cluster={cluster_id}")
        evidence.append(f"k8s:pod:get:{cluster_id}:{namespace}:{req.entity_name}")
        match = next((p for p in pods if p.get("name") == req.entity_name), None)
        if match is None:
            ruled_out.append(f"Pod {req.entity_name!r} not found in namespace {namespace!r}")
        else:
            findings.append(
                f"Pod {req.entity_name!r} phase={match.get('phase') or 'unknown'} restart_count={match.get('restart_count', 0)}"
            )

    return WorkerResult(
        checked=checked,
        findings=findings,
        evidence_refs=evidence,
        ruled_out=ruled_out,
        confidence=0.86 if failing > 0 or crashloop > 0 else 0.82,
        next_suggested_check=(
            "Inspect events and logs for failing pods; verify RBAC scope for deeper checks"
            if failing > 0 or crashloop > 0
            else "If issue persists, check pod events and node conditions for this namespace"
        ),
    )
