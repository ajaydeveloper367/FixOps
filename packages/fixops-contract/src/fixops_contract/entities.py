"""Strict schema for entity extraction (LLM output validated to this model; routing is separate)."""

from pydantic import BaseModel, Field


class ExtractedEntity(BaseModel):
    """Result of schema-bound LLM extraction (AD-002). Not a routing decision."""

    entity_type: str = Field(
        ...,
        description="e.g. pod, deployment, service, topic, dag",
    )
    entity_name: str
    namespace: str | None = None
    alert_class: str | None = Field(default=None, description="Normalized alert class / firing rule id")
    labels: dict[str, str] = Field(default_factory=dict)
