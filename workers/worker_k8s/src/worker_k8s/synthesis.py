"""Turn raw cluster facts into WorkerResponse (deterministic path)."""

from __future__ import annotations

import json
from typing import Any

from fixops_contract.models import AlertPayload, WorkerResponse
from fixops_contract.ollama_json import OllamaJsonConfig, complete_json
from fixops_contract.version import CONTRACT_VERSION

from worker_k8s.adapters.kubernetes_api import EventSummary, PodSnapshot


def build_facts_bundle(
    *,
    alert: AlertPayload,
    pod: PodSnapshot | None,
    deployment: dict[str, Any] | None,
    events: list[EventSummary],
    pod_logs: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "alert": alert.model_dump(),
        "pod": None
        if pod is None
        else {
            "exists": pod.exists,
            "name": pod.name,
            "namespace": pod.namespace,
            "phase": pod.phase,
            "reason": pod.reason,
            "message": pod.message,
            "container_waiting_reason": pod.container_waiting_reason,
            "last_state_terminated_reason": pod.last_state_terminated_reason,
            "restart_count": pod.restart_count,
            "container_states": [
                {
                    "name": c.name,
                    "restart_count": c.restart_count,
                    "waiting_reason": c.waiting_reason,
                    "terminated_reason": c.terminated_reason,
                    "exit_code": c.exit_code,
                    "signal": c.signal,
                    "terminated_message": c.terminated_message,
                }
                for c in pod.container_states
            ],
        },
        "pod_logs": pod_logs or {},
        "deployment": deployment,
        "events": [
            {
                "ref": e.ref,
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "involved_kind": e.involved_kind,
                "involved_name": e.involved_name,
            }
            for e in events
        ],
    }


def _log_tail(text: str, *, max_lines: int = 15, max_chars: int = 4000) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    blob = "\n".join(lines[-max_lines:])
    if len(blob) > max_chars:
        return blob[-max_chars:]
    return blob


def deterministic_response(
    *,
    alert: AlertPayload,
    pod: PodSnapshot | None,
    deployment: dict[str, Any] | None,
    events: list[EventSummary],
    pod_logs: dict[str, dict[str, str]] | None = None,
) -> WorkerResponse:
    checked: list[str] = []
    findings: list[str] = []
    evidence: list[str] = []
    ruled_out: list[str] = []
    confidence = 0.55

    if pod:
        checked.append(f"pod/{pod.namespace}/{pod.name}")
        if pod.exists:
            if not pod.container_states:
                findings.append(
                    "Pod exists but no containerStatuses were returned (unusual); check RBAC or API version."
                )
                evidence.append(f"pod_status/{pod.namespace}/{pod.name}/empty_container_statuses")
                confidence = max(confidence, 0.45)
            for c in pod.container_states:
                checked.append(
                    f"container_status/{pod.namespace}/{pod.name}/{c.name}"
                )
                parts = [
                    f"container={c.name!r}",
                    f"restarts={c.restart_count}",
                    f"waiting={c.waiting_reason!r}",
                    f"last_exit_code={c.exit_code!r}",
                    f"last_terminated_reason={c.terminated_reason!r}",
                ]
                if c.terminated_message:
                    parts.append(f"terminated_message={c.terminated_message!r}")
                findings.append("Pod status: " + ", ".join(parts) + ".")
                evidence.append(
                    f"pod_status/{pod.namespace}/{pod.name}/container/{c.name}"
                )
                if c.terminated_reason == "OOMKilled":
                    confidence = max(confidence, 0.9)
                elif c.waiting_reason == "CrashLoopBackOff":
                    confidence = max(confidence, 0.86)
                elif c.waiting_reason == "ImagePullBackOff" or c.waiting_reason == "ErrImagePull":
                    confidence = max(confidence, 0.88)

            if pod.last_state_terminated_reason == "OOMKilled":
                findings.append(
                    "At least one container last termination reason is OOMKilled (memory limit or node pressure)."
                )
                evidence.append(
                    f"pod_status/{pod.namespace}/{pod.name}/lastState/terminated/OOMKilled"
                )
                ruled_out.append("Pod object missing / 404 (false): pod exists.")
                confidence = max(confidence, 0.9)
            elif pod.container_waiting_reason in ("CrashLoopBackOff", "ImagePullBackOff"):
                findings.append(
                    f"At least one container is waiting: {pod.container_waiting_reason}."
                )
                evidence.append(
                    f"pod_status/{pod.namespace}/{pod.name}/waiting/{pod.container_waiting_reason}"
                )
                ruled_out.append("Pod not missing; kubelet is restarting or cannot pull image.")
                confidence = max(confidence, 0.86)
            elif pod.phase == "Running" and pod.restart_count == 0:
                findings.append("Pod exists, phase Running, no restarts observed on summary.")
                evidence.append(f"pod_status/{pod.namespace}/{pod.name}/phase/Running")
                ruled_out.append("No restart storm on aggregated counters.")
                confidence = max(confidence, 0.72)
            elif pod.phase == "Running":
                findings.append(
                    f"Pod phase Running but restart_count={pod.restart_count} (unstable or probe churn)."
                )
                evidence.append(f"pod_status/{pod.namespace}/{pod.name}/restarts/{pod.restart_count}")
                confidence = max(confidence, 0.78)
            else:
                findings.append(
                    f"Pod exists; phase={pod.phase}, reason={pod.reason}, message={pod.message!r}."
                )
                evidence.append(f"pod_status/{pod.namespace}/{pod.name}/phase/{pod.phase}")
                confidence = max(confidence, 0.7)

            if pod_logs:
                if pod.phase == "Running" and pod.restart_count == 0:
                    findings.append(
                        "Pulled recent container logs even though pod phase is Running with "
                        "no restarts: alert text indicates log-line / access / silent failure signals."
                    )
                    evidence.append(f"policy/pod_logs/{pod.namespace}/{pod.name}/alert_driven")
                for cname, bundle in pod_logs.items():
                    prev = bundle.get("previous") or ""
                    cur = bundle.get("current") or ""
                    if prev.strip():
                        checked.append(
                            f"logs/{pod.namespace}/{pod.name}/{cname}/previous"
                        )
                        tail = _log_tail(prev)
                        findings.append(
                            f"Previous-instance log tail for container {cname!r} (often shows the crash):\n{tail}"
                        )
                        evidence.append(
                            f"pod_logs/{pod.namespace}/{pod.name}/{cname}/previous"
                        )
                        confidence = max(confidence, 0.88)
                    if cur.strip():
                        checked.append(
                            f"logs/{pod.namespace}/{pod.name}/{cname}/current"
                        )
                        tailc = _log_tail(cur, max_lines=8)
                        findings.append(
                            f"Current-instance log tail for container {cname!r}:\n{tailc}"
                        )
                        evidence.append(
                            f"pod_logs/{pod.namespace}/{pod.name}/{cname}/current"
                        )
        else:
            findings.append(
                f"Pod {pod.name!r} not found in namespace {pod.namespace!r} (deleted or never created)."
            )
            evidence.append(f"k8s_api/404/pod/{pod.namespace}/{pod.name}")
            ruled_out.append("OOMKilled on current pod object (pod absent).")
            confidence = 0.72

    if deployment:
        checked.append(f"deployment/{deployment['namespace']}/{deployment['name']}")
        dr = deployment.get("ready_replicas")
        dd = deployment.get("replicas_desired")
        findings.append(
            f"Deployment replicas: desired={dd}, ready={dr}."
        )
        evidence.append(f"deployment/{deployment['namespace']}/{deployment['name']}/replicas")
        if dr == dd and dr not in (None, 0):
            ruled_out.append("Deployment not obviously scaled to zero for readiness mismatch.")
            confidence = max(confidence, 0.74)

    if events:
        checked.append(f"events/{alert.namespace}/recent")
        top = events[:12]
        for e in top:
            evidence.append(e.ref)
        msg_blob = " ".join(e.message for e in top if e.message)
        if pod and pod.exists and (
            "Back-off" in msg_blob
            or "back-off" in msg_blob.lower()
            or "CrashLoopBackOff" in msg_blob
        ):
            findings.append(
                "Namespace events include Back-off / CrashLoopBackOff signals for this workload (kubelet view)."
            )
            confidence = max(confidence, 0.84)
        if pod and not pod.exists:
            if any(
                "deleted" in e.message.lower() or "delete" in e.message.lower()
                for e in top
                if e.message
            ):
                findings.append(
                    "Events reference delete/killing consistent with manual or controller-initiated removal."
                )
                confidence = max(confidence, 0.8)
            if "OOMKilled" in msg_blob or "evicted" in msg_blob.lower():
                findings.append(
                    "Events mention OOMKilled/eviction-related signals; correlate with limits/node pressure."
                )
                confidence = max(confidence, 0.84)

    if not findings:
        findings.append(
            "Insufficient targeted signals; provide namespace/name or check RBAC scope."
        )
        confidence = 0.35

    return WorkerResponse(
        contract_version=CONTRACT_VERSION,
        checked=checked,
        findings=findings,
        evidence_refs=evidence,
        ruled_out=ruled_out,
        confidence=min(1.0, confidence),
        next_suggested_check=None,
    )


def llm_response(
    *,
    ollama: OllamaJsonConfig,
    facts: dict[str, Any],
) -> WorkerResponse:
    system = (
        "You are a Kubernetes incident investigator. "
        "Return ONLY a JSON object with keys: "
        "checked (string[]), findings (string[]), evidence_refs (string[]), "
        "ruled_out (string[]), confidence (number 0..1), next_suggested_check (string|null). "
        "Every finding must cite evidence_refs entries that appear in the user JSON facts.events[].ref "
        "or pod/deployment paths you infer from facts. If unsure, lower confidence below 0.6."
    )
    user = json.dumps(facts, indent=2)[:12000]
    raw = complete_json(ollama, system=system, user=user)
    return WorkerResponse.model_validate({**raw, "contract_version": CONTRACT_VERSION})
