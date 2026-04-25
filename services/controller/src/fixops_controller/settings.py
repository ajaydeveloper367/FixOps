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
    worker_pipeline_base_url: str = "http://127.0.0.1:8084"
    worker_db_base_url: str = "http://127.0.0.1:8085"
    worker_app_rca_base_url: str = "http://127.0.0.1:8086"
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
    max_investigation_stages: int = 3
    stage1_token_budget: int = 3000
    stage2_token_budget: int = 2200
    stage3_token_budget: int = 1400
    stage1_tool_call_budget: int = 8
    stage2_tool_call_budget: int = 6
    stage3_tool_call_budget: int = 4
    confidence_high_threshold: float = 0.85
    confidence_low_threshold: float = 0.50
    rag_top_k: int = 3
    rag_char_budget: int = 1200
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
