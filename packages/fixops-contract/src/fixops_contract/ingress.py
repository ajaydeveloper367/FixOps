"""AD-013 — alerts and ad-hoc queries share the same pipeline after normalization."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedIngress(BaseModel):
    """Internal shape after normalize_ingress."""

    source: Literal["alert", "query"]
    environment: str = Field(default="development", description="production | staging | development")
    raw: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    thread_id: str | None = None


class BoundedIntent(BaseModel):
    """Synthetic alert + session for query path (AD-013)."""

    synthetic_alert: dict[str, Any]
    session_id: str
    summary: str = Field(..., max_length=512)
