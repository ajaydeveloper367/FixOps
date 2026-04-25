"""Typed Kubernetes adapter (AD-007)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class KubernetesPort(Protocol):
    def list_pods(self, namespace: str) -> list[dict[str, Any]]: ...

    def read_pod(self, namespace: str, name: str) -> dict[str, Any] | None: ...


class KubernetesApiAdapter:
    def __init__(self, *, kubeconfig_path: str | None, context: str | None = None) -> None:
        from kubernetes import client, config

        if kubeconfig_path:
            cfg = str(Path(kubeconfig_path).expanduser())
            config.load_kube_config(config_file=cfg, context=context)
        else:
            config.load_incluster_config()
        self._v1 = client.CoreV1Api()

    def list_pods(self, namespace: str) -> list[dict[str, Any]]:
        items = self._v1.list_namespaced_pod(namespace=namespace).items
        return [_pod_to_dict(p) for p in items]

    def read_pod(self, namespace: str, name: str) -> dict[str, Any] | None:
        p = self._v1.read_namespaced_pod(name=name, namespace=namespace)
        if p is None:
            return None
        return _pod_to_dict(p)


def _pod_to_dict(pod: Any) -> dict[str, Any]:
    meta = getattr(pod, "metadata", None)
    st = getattr(pod, "status", None)
    spec = getattr(pod, "spec", None)
    statuses = getattr(st, "container_statuses", None) or []
    restart_count = sum(int(getattr(cs, "restart_count", 0) or 0) for cs in statuses)
    waiting_reasons = []
    for cs in statuses:
        state = getattr(cs, "state", None)
        waiting = getattr(state, "waiting", None) if state else None
        reason = getattr(waiting, "reason", None) if waiting else None
        if reason:
            waiting_reasons.append(str(reason))
    return {
        "name": getattr(meta, "name", None),
        "namespace": getattr(meta, "namespace", None),
        "phase": getattr(st, "phase", None),
        "node_name": getattr(spec, "node_name", None),
        "restart_count": restart_count,
        "waiting_reasons": waiting_reasons,
    }


def build_kubernetes_adapter(creds: dict[str, str]) -> KubernetesPort:
    return KubernetesApiAdapter(
        kubeconfig_path=creds.get("kubeconfig_path"),
        context=creds.get("context"),
    )
