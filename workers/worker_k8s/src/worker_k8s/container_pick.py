"""Pick which container to pull logs for (multi-container pods)."""

from __future__ import annotations

import re

from fixops_contract.models import AlertPayload

from worker_k8s.adapters.kubernetes_api import PodSnapshot


def infer_container_name(alert: AlertPayload, pod: PodSnapshot | None) -> str | None:
    raw = alert.extra.get("container") if alert.extra else None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    m = re.search(
        r"failed\s+container\s+(\S+?)\s+in\s+pod",
        alert.message or "",
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m2 = re.search(
        r"Back-off\s+restarting\s+failed\s+container\s+(\S+)",
        alert.message or "",
        flags=re.IGNORECASE,
    )
    if m2:
        return m2.group(1).strip()
    if not pod or not pod.exists or not pod.container_states:
        return None
    # Prefer a container in CrashLoopBackOff / ImagePullBackOff, else highest restarts
    for st in pod.container_states:
        if st.waiting_reason in ("CrashLoopBackOff", "ImagePullBackOff", "CreateContainerConfigError"):
            return st.name
    return max(pod.container_states, key=lambda s: s.restart_count).name


_LOG_SIGNAL = re.compile(
    r"\b(logs?|logging|stderr|stdout|stack\s*trace|traceback|exception|panic|fatal)\b",
    re.IGNORECASE,
)
_ISSUE_SIGNAL = re.compile(
    r"(error\s+on|errors?\s+in|can't\s+access|cannot\s+access|failed\s+to|unable\s+to|"
    r"access\s+denied|denied|forbidden|unauthorized|not\s+authorized|"
    r"\b403\b|\b404\b|\b500\b|timeout|connection\s+refused|no\s+such\s+bucket|s3\b)",
    re.IGNORECASE,
)


def alert_suggests_log_evidence(alert: AlertPayload) -> bool:
    """
    True when the alert is about log lines / soft failures, even if the pod is Running
    with zero restarts (no CrashLoopBackOff).
    """
    ex = alert.extra or {}
    raw = ex.get("investigate_logs")
    if raw in (True, "true", "1", "yes", "on"):
        return True
    blob = f"{alert.title or ''} {alert.message or ''}"
    if _LOG_SIGNAL.search(blob) or _ISSUE_SIGNAL.search(blob):
        return True
    return False


def should_pull_logs(pod: PodSnapshot | None) -> bool:
    if not pod or not pod.exists or not pod.container_states:
        return False
    for st in pod.container_states:
        if st.waiting_reason in (
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "CreateContainerConfigError",
            "ErrImagePull",
        ):
            return True
        if st.restart_count > 0 and (
            st.terminated_reason is not None or st.exit_code is not None
        ):
            return True
    return False
