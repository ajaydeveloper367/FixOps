"""Pluggable worker-k8s credential backends (AD-012)."""

from __future__ import annotations

import json

from fixops_worker_k8s.credentials import resolve_credentials
from fixops_worker_k8s.settings import settings


def test_resolve_credentials_env_json_prefers_credentials_ref(monkeypatch) -> None:
    monkeypatch.setattr(settings, "credentials_backend", "env_json")
    monkeypatch.setattr(settings, "credentials_env_var", "FIXOPS_WORKER_K8S_CREDENTIALS_JSON")
    monkeypatch.setenv(
        "FIXOPS_WORKER_K8S_CREDENTIALS_JSON",
        json.dumps(
            {
                "dev-eks": {"kubeconfig_path": "~/.kube/dev.json"},
                "ref:dev-eks": {"kubeconfig_path": "~/.kube/dev-ref.json"},
            }
        ),
    )
    out = resolve_credentials("dev-eks", "ref:dev-eks")
    assert out is not None
    assert out["kubeconfig_path"].endswith("dev-ref.json")


def test_resolve_credentials_file_json(monkeypatch, tmp_path) -> None:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"ref:prod-eks": {"kubeconfig_path": "~/.kube/prod.json"}}))
    monkeypatch.setattr(settings, "credentials_backend", "file_json")
    monkeypatch.setattr(settings, "credentials_file", str(p))
    out = resolve_credentials("prod-eks", "ref:prod-eks")
    assert out is not None
    assert out["kubeconfig_path"].endswith("prod.json")
