from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fixops_contract.config_yaml import load_worker_k8s_yaml


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXOPS_WORKER_K8S_", extra="ignore")

    credentials_backend: str = "local_map"
    default_cluster_id: str | None = "local"
    clusters: dict[str, dict[str, str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _merge_config_yaml(cls, data: Any) -> Any:
        y = load_worker_k8s_yaml()
        d = dict(data) if isinstance(data, dict) else {}
        merged = {**y, **d}
        raw_clusters = merged.get("clusters") or {}
        if isinstance(raw_clusters, list):
            # Optional list form:
            # clusters:
            #   - cluster_id: local
            #     kubeconfig_path: ~/.kube/config
            out: dict[str, dict[str, str]] = {}
            for row in raw_clusters:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("cluster_id") or "").strip()
                if not cid:
                    continue
                out[cid] = {k: str(v) for k, v in row.items() if k != "cluster_id" and v is not None}
            merged["clusters"] = out
        return merged


settings = Settings()
