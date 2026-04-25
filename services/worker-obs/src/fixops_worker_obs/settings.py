from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXOPS_WORKER_", extra="ignore")

    prometheus_url: str | None = None
    credentials_backend: str = "env"  # env | file (pluggable AD-012)


settings = Settings()
