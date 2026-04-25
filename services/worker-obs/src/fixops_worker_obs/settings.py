import os
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fixops_contract.config_yaml import load_worker_obs_yaml


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXOPS_WORKER_", extra="ignore")

    prometheus_base_url: str | None = None
    prometheus_query_path: str = "/api/v1/query"
    credentials_backend: str = "env"

    @model_validator(mode="before")
    @classmethod
    def _merge_config_yaml(cls, data: Any) -> Any:
        y = load_worker_obs_yaml()
        d = dict(data) if isinstance(data, dict) else {}
        merged = {**y, **d}
        if merged.get("prometheus_base_url") is None and (
            legacy := os.environ.get("FIXOPS_WORKER_PROMETHEUS_URL")
        ):
            merged["prometheus_base_url"] = legacy
        return merged


settings = Settings()
