"""
When Grafana logs show datasource provisioning / duplicate-default errors,
inspect mounted ConfigMaps and list which datasource names are marked default.
"""

from __future__ import annotations

import re

import yaml

from worker_k8s.adapters.kubernetes_api import KubernetesApiAdapter


def _logs_suggest_datasource_conflict(blob: str) -> bool:
    b = blob.lower()
    return "datasource" in b and "provision" in b and "default" in b


def _defaults_in_yaml(text: str) -> list[str]:
    """Return datasource names that have isDefault true (Grafana provisioning)."""
    try:
        data = yaml.safe_load(text)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    ds_list = data.get("datasources")
    if not isinstance(ds_list, list):
        return []
    out: list[str] = []
    for item in ds_list:
        if not isinstance(item, dict):
            continue
        if item.get("isDefault") is True:
            out.append(str(item.get("name") or item.get("uid") or "unknown"))
    return out


def scan_grafana_datasource_defaults(
    adapter: KubernetesApiAdapter,
    *,
    namespace: str,
    pod_name: str,
    container_name: str,
    log_blob: str,
) -> tuple[list[str], list[str]]:
    """
    Returns (extra_findings, extra_checked_refs).
    """
    if not _logs_suggest_datasource_conflict(log_blob):
        return [], []

    try:
        cm_names = adapter.list_configmap_names_for_container(
            namespace, pod_name, container_name
        )
    except Exception as e:
        return [
            f"Could not list ConfigMaps for container {container_name!r}: {e!r}"
        ], []

    extra_findings: list[str] = []
    checked: list[str] = []

    per_file_defaults: list[tuple[str, str, list[str]]] = []

    for cm_name in cm_names:
        checked.append(f"configmap/{namespace}/{cm_name}")
        try:
            data = adapter.read_config_map_data(namespace, cm_name)
        except Exception as e:
            extra_findings.append(f"ConfigMap {cm_name!r}: read failed: {e!r}")
            continue
        for key, raw in data.items():
            if not raw or not isinstance(raw, str):
                continue
            lk = key.lower()
            if "datasource" not in lk and not lk.endswith((".yaml", ".yml")):
                continue
            defaults = _defaults_in_yaml(raw)
            if defaults:
                per_file_defaults.append((cm_name, key, defaults))

    multi_in_one = [x for x in per_file_defaults if len(x[2]) >= 2]
    for cm_name, key, defaults in multi_in_one:
        extra_findings.append(
            f"ConfigMap {cm_name!r} key {key!r}: {len(defaults)} datasources have isDefault=true "
            f"in the same file: {', '.join(defaults)}. Keep exactly one isDefault: true in this file."
        )

    detail_lines: list[str] = []
    for cm_name, key, names in per_file_defaults:
        for n in names:
            detail_lines.append(f"{n!r} (ConfigMap {cm_name!r}, key {key!r})")
    unique_detail = list(dict.fromkeys(detail_lines))
    if len(unique_detail) > 1 and not multi_in_one:
        extra_findings.append(
            "Across mounted provisioning, more than one datasource is marked default: "
            + "; ".join(unique_detail)
            + ". Grafana merges these files — keep exactly one isDefault: true overall."
        )
    elif len(unique_detail) == 1 and "only one datasource" in log_blob.lower() and not multi_in_one:
        extra_findings.append(
            f"Mounted provisioning shows one isDefault=true entry: {unique_detail[0]}. "
            "If Grafana still errors, look for another provisioning source (Secret, extra volume, or init job)."
        )

    # If YAML scan found nothing, still point at likely files from log
    if not extra_findings and "datasource.yaml" in log_blob.lower():
        m = re.search(r"datasource\.yaml", log_blob, flags=re.IGNORECASE)
        if m:
            extra_findings.append(
                "Logs reference generated `datasource.yaml` under provisioning. "
                "Inspect ConfigMaps mounted into this pod (sidecar output) for multiple `isDefault: true`."
            )

    return extra_findings, checked
