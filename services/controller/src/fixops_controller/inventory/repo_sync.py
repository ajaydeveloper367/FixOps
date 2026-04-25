from typing import Any

from sqlalchemy import or_, select

from fixops_controller.db.models import GraphEdge, InventoryEntity
from fixops_controller.db.sync_session import SyncSessionLocal


def list_inventory_entities_sync() -> list[dict[str, Any]]:
    with SyncSessionLocal() as s:
        rows = s.scalars(select(InventoryEntity)).all()
        return [{"id": r.id, "entity_type": r.entity_type, "data": dict(r.data or {})} for r in rows]


def graph_neighbors_sync(entity_id: str) -> list[dict[str, Any]]:
    with SyncSessionLocal() as s:
        rows = s.scalars(
            select(GraphEdge).where(or_(GraphEdge.from_id == entity_id, GraphEdge.to_id == entity_id))
        ).all()
        return [{"from": r.from_id, "to": r.to_id, "relation": r.relation, "meta": dict(r.meta or {})} for r in rows]
