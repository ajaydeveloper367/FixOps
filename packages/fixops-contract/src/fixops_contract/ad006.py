"""AD-006 — fixed worker response contract (compact JSON only across controller boundary)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkerInvestigateRequest(BaseModel):
    """Payload from controller → worker. Refs only for credentials (AD-012)."""

    investigation_id: str
    stage: int = Field(default=1, ge=1, le=3, description="AD-005 staged context stage")
    cluster_id: str | None = None
    credentials_ref: str | None = None
    entity_type: str
    entity_name: str
    namespace: str | None = None
    alert_class: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    compact_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Bounded structured hints from inventory/graph — never raw logs",
    )
    token_budget: int = Field(default=4000, ge=500, le=32000)
    tool_call_budget: int = Field(default=8, ge=0, le=64)


class WorkerResult(BaseModel):
    """AD-006 structured worker output."""

    checked: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    next_suggested_check: str | None = None

    @field_validator("confidence")
    @classmethod
    def confidence_finite(cls, v: float) -> float:
        if v != v:  # NaN
            raise ValueError("confidence must be a finite float")
        return v
