"""AD-012 worker-side credential resolution with pluggable backends."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fixops_worker_k8s.settings import settings


def _as_map(obj: object) -> dict[str, dict[str, str]]:
    if not isinstance(obj, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for k, v in obj.items():
        ks = str(k).strip()
        if not ks or not isinstance(v, dict):
            continue
        out[ks] = {str(ik): str(iv) for ik, iv in v.items() if ik is not None and iv is not None}
    return out


def _resolve_local_map(cluster_id: str | None, credentials_ref: str | None) -> dict[str, str] | None:
    if cluster_id:
        c = (settings.clusters or {}).get(cluster_id)
        if c:
            return c
    if credentials_ref:
        ref = (settings.credential_refs or {}).get(credentials_ref)
        if ref:
            return ref
    return None


def _resolve_env_json(cluster_id: str | None, credentials_ref: str | None) -> dict[str, str] | None:
    raw = os.environ.get(settings.credentials_env_var, "")
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    mapping = _as_map(parsed)
    if credentials_ref and credentials_ref in mapping:
        return mapping[credentials_ref]
    if cluster_id and cluster_id in mapping:
        return mapping[cluster_id]
    return None


def _resolve_file_json(cluster_id: str | None, credentials_ref: str | None) -> dict[str, str] | None:
    p = (settings.credentials_file or "").strip()
    if not p:
        return None
    path = Path(p).expanduser()
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text())
    except Exception:
        return None
    mapping = _as_map(parsed)
    if credentials_ref and credentials_ref in mapping:
        return mapping[credentials_ref]
    if cluster_id and cluster_id in mapping:
        return mapping[cluster_id]
    return None


def resolve_credentials(cluster_id: str | None, credentials_ref: str | None) -> dict[str, str] | None:
    backend = (settings.credentials_backend or "local_map").strip().lower()
    if backend == "local_map":
        return _resolve_local_map(cluster_id, credentials_ref)
    if backend == "env_json":
        return _resolve_env_json(cluster_id, credentials_ref)
    if backend == "file_json":
        return _resolve_file_json(cluster_id, credentials_ref)
    # Unknown backend: fail closed.
    return None
