from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fixops_contract.config_yaml import load_controller_yaml


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXOPS_", extra="ignore")

    database_url: str = "sqlite:///./.fixops/controller.db"
    redis_url: str | None = None
    worker_obs_base_url: str = "http://127.0.0.1:8081"
    worker_k8s_base_url: str = "http://127.0.0.1:8083"
    executor_url: str = "http://127.0.0.1:8082"
    routing_rules_path: str = "config/routing_rules.yaml"
    inventory_seed_path: str = "config/inventory.yaml"
    graph_seed_path: str = "config/graph_edges.yaml"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_use_json_response_format: bool = True
    mock_llm: bool = False
    checkpoint_backend: str = "memory"
    auto_approve_execute: bool = False
    # When true, await_approval uses LangGraph interrupt() until POST .../resume (AD-003).
    # When false, approval is auto-granted after RCA (local / CI one-shot).
    require_human_approval: bool = True
    environment: str = "development"
    # When set (YAML or FIXOPS_CONTROLLER_API_KEY), POST /run, /resume, and GET /snapshot require it.
    controller_api_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _merge_config_yaml(cls, data: Any) -> Any:
        y = load_controller_yaml()
        d = dict(data) if isinstance(data, dict) else {}
        return {**y, **d}


settings = Settings()
