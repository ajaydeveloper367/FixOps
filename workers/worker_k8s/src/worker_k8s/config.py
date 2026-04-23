from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# worker_k8s/src/worker_k8s/config.py → workers/worker_k8s/ (mini-project root)
_WORKER_K8S_ROOT = Path(__file__).resolve().parent.parent.parent


class WorkerK8sSettings(BaseSettings):
    """
    All worker-k8s configuration is isolated here.
    Env prefix: WORKER_K8S_
    Example: WORKER_K8S_KUBECONFIG=/path/to/kubeconfig
    """

    model_config = SettingsConfigDict(
        env_prefix="WORKER_K8S_",
        env_file=(
            _WORKER_K8S_ROOT / "worker-k8s.env",
            Path(".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kubeconfig: Path | None = Field(
        default=None,
        description="Path to kubeconfig. If unset, default loader rules apply.",
    )
    kube_context: str | None = Field(
        default=None,
        description="Active kube context name, if kubeconfig is used (single-cluster mode).",
    )

    cluster_map_path: Path | None = Field(
        default=None,
        description=(
            "YAML file mapping alert.cluster_id → kubeconfig path + optional context. "
            "When set, alerts must include cluster_id matching a key (see worker README)."
        ),
    )

    llm_base_url: str | None = Field(
        default=None,
        description="Ollama OpenAI-compatible base, e.g. http://127.0.0.1:11434/v1",
    )
    llm_model: str | None = None
    llm_timeout_seconds: float = 120.0

    http_host: str = Field(
        default="0.0.0.0",
        description="Bind address for fixops-worker-k8s-serve.",
    )
    http_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Listen port for the HTTP worker.",
    )

    @field_validator("cluster_map_path", mode="after")
    @classmethod
    def resolve_cluster_map_relative(cls, v: Path | None) -> Path | None:
        if v is None:
            return None
        if v.is_absolute():
            return v
        return (_WORKER_K8S_ROOT / v).resolve()

    @field_validator("http_host", mode="before")
    @classmethod
    def strip_host(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v
