from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# controller/src/controller/config.py → controller/ (mini-project root)
_CONTROLLER_ROOT = Path(__file__).resolve().parent.parent.parent


def _default_decision_log_path() -> Path:
    """Under the controller mini-project (`controller/data/`) for easy volume mounts."""
    return _CONTROLLER_ROOT / "data" / "decisions.jsonl"


class ControllerSettings(BaseSettings):
    """
    Controller-only configuration.
    Env prefix: CONTROLLER_
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTROLLER_",
        env_file=(
            _CONTROLLER_ROOT / "controller.env",
            Path(".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    decision_log_path: Path = Field(
        default_factory=_default_decision_log_path,
        description="Append-only JSONL audit log (default: controller/data/decisions.jsonl).",
    )

    llm_base_url: str | None = Field(
        default=None,
        description="Ollama OpenAI-compatible base for optional narrative summary.",
    )
    llm_model: str | None = None
    llm_timeout_seconds: float = 120.0

    worker_k8s_base_url: str | None = Field(
        default=None,
        description="Base URL of the standalone worker-k8s HTTP service, e.g. http://127.0.0.1:8080",
    )
    worker_k8s_timeout_seconds: float = Field(
        default=300.0,
        ge=10.0,
        description="HTTP read timeout for POST /v1/investigate (K8s calls can be slow).",
    )
