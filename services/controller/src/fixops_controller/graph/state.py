"""LangGraph state — compact dicts at boundaries; no raw log fields."""

from typing import Any, TypedDict


class OpsState(TypedDict, total=False):
    investigation_id: str
    normalized: dict[str, Any]
    extracted: dict[str, Any]
    route: dict[str, Any]
    stage: int
    staged_context: dict[str, Any]
    worker_results: list[dict[str, Any]]
    merged: dict[str, Any]
    confidence_band: str
    escalate: bool
    rca: dict[str, Any]
    approval: dict[str, Any]
    execution: dict[str, Any] | None
    errors: list[str]
