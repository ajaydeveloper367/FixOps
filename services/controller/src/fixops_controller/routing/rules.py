"""Deterministic routing (AD-002). LLM output is only `ExtractedEntity`; rules pick the worker."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fixops_contract.entities import ExtractedEntity


@dataclass(frozen=True)
class RouteDecision:
    worker_id: str
    worker_base_url: str
    cluster_id: str | None
    credentials_ref: str | None
    inventory_match_id: str | None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_routing_table(path: str | Path) -> dict[str, Any]:
    return _load_yaml(Path(path))


def resolve_route(
    extracted: ExtractedEntity,
    routing: dict[str, Any],
    inventory_entities: list[dict[str, Any]],
    worker_registry: dict[str, str],
) -> RouteDecision:
    """
    Pure function for unit tests. `worker_registry` maps worker_id -> base_url.
    `inventory_entities` rows: {id, entity_type, data: {...}}.
    """
    rules: list[dict[str, Any]] = routing.get("rules") or []
    default_worker_id: str = routing.get("default_worker_id", "worker-obs")
    default_url = worker_registry.get(default_worker_id, "")

    cluster_id: str | None = None
    credentials_ref: str | None = None
    inventory_match_id: str | None = None

    for row in inventory_entities:
        data = row.get("data") or {}
        if row.get("entity_type") == "service" and data.get("service_name") == extracted.entity_name:
            inventory_match_id = row.get("id")
            cluster_id = data.get("cluster_id")
            credentials_ref = data.get("credentials_ref")
            break
        if row.get("entity_type") == "cluster" and data.get("cluster_id") == extracted.entity_name:
            inventory_match_id = row.get("id")
            cluster_id = data.get("cluster_id")
            credentials_ref = data.get("credentials_ref")
            break

    for rule in rules:
        match = rule.get("match") or {}
        if _rule_matches(match, extracted):
            wid = rule["worker_id"]
            return RouteDecision(
                worker_id=wid,
                worker_base_url=worker_registry.get(wid, default_url),
                cluster_id=cluster_id,
                credentials_ref=credentials_ref,
                inventory_match_id=inventory_match_id,
            )

    return RouteDecision(
        worker_id=default_worker_id,
        worker_base_url=default_url,
        cluster_id=cluster_id,
        credentials_ref=credentials_ref,
        inventory_match_id=inventory_match_id,
    )


def _rule_matches(match: dict[str, Any], extracted: ExtractedEntity) -> bool:
    if "entity_type" in match and match["entity_type"] != extracted.entity_type:
        return False
    if "alert_class" in match and match["alert_class"] != extracted.alert_class:
        return False
    if "entity_name_prefix" in match:
        prefix = match["entity_name_prefix"]
        if not extracted.entity_name.startswith(prefix):
            return False
    return True


def inventory_rows_from_db(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({"id": r.id, "entity_type": r.entity_type, "data": dict(r.data or {})})
    return out
