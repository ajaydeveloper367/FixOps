"""Turn worker output into a short root-cause line and action items (controller-side)."""

from __future__ import annotations

import re

from fixops_contract.models import AlertPayload, WorkerResponse

from controller.conclusion import logs_were_pulled


def derive_root_cause_and_actions(
    alert: AlertPayload, worker: WorkerResponse
) -> tuple[str | None, list[str]]:
    blob = "\n".join(worker.findings)
    root: str | None = None

    # Prefer ConfigMap scan (most specific)
    for line in worker.findings:
        if line.startswith("ConfigMap ") and "isDefault=true" in line:
            root = line
            break
        if line.startswith("Across mounted provisioning"):
            root = line
            break

    if root is None:
        m = re.search(
            r"Datasource provisioning error:\s*([^\n\"]+)",
            blob,
            flags=re.IGNORECASE,
        )
        if m:
            root = m.group(1).strip()
        else:
            m2 = re.search(r'error="([^"]+)"', blob)
            if m2:
                root = m2.group(1).strip()
            else:
                m3 = re.search(r"Error:\s*([^\n]+)", blob)
                if m3:
                    root = m3.group(1).strip()[:400]

    actions: list[str] = []
    low = blob.lower()
    if "isdefault=true" in low or "only one datasource" in low:
        actions.append(
            "Open the Grafana datasource provisioning that this pod mounts (Helm: "
            "`kube-prometheus-stack` / Grafana `additionalDataSources` / sidecar ConfigMaps)."
        )
        actions.append(
            "Ensure **exactly one** datasource has `isDefault: true` for the Grafana organization "
            "(remove `isDefault` from the others, or set them to false)."
        )
        actions.append(
            "After editing the ConfigMap/Helm values, apply them and **restart** the Grafana workload "
            "(rollout restart / delete pod) and re-check logs."
        )
    if "imagepullbackoff" in low or "errimagepull" in low:
        actions.append("Fix image name/tag and registry pull secrets; verify `imagePullSecrets` on the Pod.")
    if "oomkilled" in low:
        actions.append("Raise memory limits/requests or reduce workload memory; confirm node has capacity.")

    if not actions and logs_were_pulled(worker):
        actions.append(
            "If the alert text does not appear in this tail: use "
            "`kubectl logs POD -c CONTAINER --since=24h --tail=500` or query Loki with the exact error string."
        )
        actions.append(
            "To always pull logs for soft failures while `Running`: add keywords to title/message or set "
            "`extra.investigate_logs: true` on the alert payload."
        )
    elif not actions and worker.confidence >= 0.5:
        actions.append(
            "Review `findings` and `evidence_refs` in the full worker output (`--json`) for next steps."
        )

    low_alert = f"{alert.title or ''} {alert.message or ''}".lower()
    if (
        logs_were_pulled(worker)
        and re.search(r"\b(s3|bucket|aws)\b", low_alert)
        and not any("datasource" in a.lower() for a in actions)
        and not any("IRSA" in a for a in actions)
    ):
        actions.append(
            "For object-storage access from the pod: verify bucket name/region, IRSA (or static creds), "
            "and IAM policy against what the container expects."
        )

    return root, actions
