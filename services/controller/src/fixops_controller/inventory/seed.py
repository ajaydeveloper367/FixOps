"""Load YAML inventory + graph into Postgres (AD-010, AD-004)."""

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete
from sqlalchemy.orm import Session

from fixops_controller.db.models import GraphEdge, InventoryEntity
from fixops_controller.db.sync_session import SyncSessionLocal


def _load(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def seed_inventory_and_graph(
    inventory_path: str | Path,
    graph_path: str | Path,
) -> None:
    inv = _load(Path(inventory_path))
    graph = _load(Path(graph_path))

    with SyncSessionLocal() as s:
        for cluster in inv.get("clusters", []):
            cid = cluster["cluster_id"]
            row = {
                "id": f"cluster:{cid}",
                "entity_type": "cluster",
                "data": {
                    "cluster_id": cid,
                    "credentials_ref": cluster.get("credentials_ref"),
                    "prometheus_url": cluster.get("prometheus_url"),
                },
            }
            _upsert_entity(s, row)
        for svc in inv.get("services", []):
            sid = svc["service_id"]
            row = {
                "id": f"service:{sid}",
                "entity_type": "service",
                "data": {
                    "service_id": sid,
                    "service_name": svc.get("service_name", sid),
                    "cluster_id": svc.get("cluster_id"),
                    "credentials_ref": svc.get("credentials_ref"),
                },
            }
            _upsert_entity(s, row)
        s.execute(delete(GraphEdge))
        for e in graph.get("edges", []):
            s.add(
                GraphEdge(
                    from_id=e["from"],
                    to_id=e["to"],
                    relation=e.get("relation", "depends_on"),
                    meta=e.get("meta") or {},
                )
            )
        s.commit()


def _upsert_entity(s: Session, row: dict[str, Any]) -> None:
    s.merge(
        InventoryEntity(
            id=row["id"],
            entity_type=row["entity_type"],
            data=row["data"],
        )
    )
