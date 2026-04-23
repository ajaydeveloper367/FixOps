from __future__ import annotations

from fixops_contract.models import AlertPayload


def route_worker(alert: AlertPayload) -> str:
    """
    Rules-first routing (LLM must not pick workers).
    Extend with inventory/graph later; today: Kubernetes path only.
    """
    if alert.entity_type in ("pod", "deployment", "namespace"):
        return "worker-k8s"
    if alert.name and alert.namespace:
        return "worker-k8s"
    return "worker-k8s"
