from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXOPS_", extra="ignore")

    # Local default: file SQLite (no Postgres required). Override with FIXOPS_DATABASE_URL for Docker/prod.
    database_url: str = "sqlite:///./.fixops/controller.db"
    redis_url: str | None = None
    worker_obs_base_url: str = "http://localhost:8081"
    executor_url: str = "http://localhost:8082"
    routing_rules_path: str = "config/routing_rules.yaml"
    inventory_seed_path: str = "config/inventory.yaml"
    graph_seed_path: str = "config/graph_edges.yaml"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    mock_llm: bool = False
    checkpoint_backend: str = "memory"  # memory | postgres (postgres needs FIXOPS_DATABASE_URL + running DB)
    auto_approve_execute: bool = False
    environment: str = "development"  # production gates mutating paths


settings = Settings()
