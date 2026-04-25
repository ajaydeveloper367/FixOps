from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InventoryEntity(Base):
    __tablename__ = "inventory_entities"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String(256), index=True)
    to_id: Mapped[str] = mapped_column(String(256), index=True)
    relation: Mapped[str] = mapped_column(String(64), default="depends_on")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DecisionLogEntry(Base):
    """Durable audit trail — not only ephemeral JSONL (prod requirement).

    Graph nodes append many ``step`` values; HTTP ``POST .../resume`` appends ``hil_api_resume``
    with ``payload``: ``thread_id``, ``resume``, ``graph_status``.
    """

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(String(128), index=True)
    step: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagChunk(Base):
    """AD-009 — bounded retrieval; pgvector optional; tsvector for BM25-style."""

    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_uri: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
