from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from fixops_contract.version import CONTRACT_VERSION


class ContractVersion(BaseModel):
    """Sent on every boundary message so mismatches are obvious after repo splits."""

    contract_version: str = Field(default=CONTRACT_VERSION)


class AlertPayload(BaseModel):
    """Normalized alert the controller ingests (file, webhook, etc.)."""

    title: str = ""
    message: str = ""
    entity_type: Literal["pod", "deployment", "namespace", "unknown"] = "unknown"
    name: str | None = None
    namespace: str | None = None
    cluster_id: str | None = Field(
        default=None,
        description="Logical cluster (e.g. EKS name). When the worker uses a cluster map, must match a key there.",
    )
    raw_labels: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class WorkerInvestigationRequest(ContractVersion):
    """Controller → worker: compact context, no raw dumps of unrelated workers."""

    alert: AlertPayload
    stage: int = Field(default=1, ge=1, le=3)
    hints: dict[str, Any] = Field(default_factory=dict)


class WorkerResponse(ContractVersion):
    """Worker → controller: fixed contract (see DECISIONS AD-006)."""

    checked: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    next_suggested_check: str | None = None


class InvestigationReport(ContractVersion):
    """What the controller emits after one investigation pass."""

    alert: AlertPayload
    routed_worker: str
    worker: WorkerResponse
    summary_lines: list[str] = Field(default_factory=list)
    root_cause_summary: str | None = Field(
        default=None,
        description="One short human sentence: what actually failed (controller-derived).",
    )
    action_items: list[str] = Field(
        default_factory=list,
        description="Concrete next steps for the on-call engineer.",
    )
    conclusion: str | None = Field(
        default=None,
        description="Plain-language verdict: what was proven vs not, from evidence (controller-derived).",
    )
