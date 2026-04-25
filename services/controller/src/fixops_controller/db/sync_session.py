"""Sync DB access for LangGraph sync nodes (decision log writes)."""

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from fixops_controller.db.models import Base, DecisionLogEntry
from fixops_controller.settings import settings


def _sync_url(url: str) -> str:
    if url.startswith("sqlite:"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return url
    u = url.replace("postgresql+asyncpg://", "postgresql://")
    if u.startswith("postgresql://"):
        return u.replace("postgresql://", "postgresql+psycopg://", 1)
    return u


sync_engine = create_engine(_sync_url(settings.database_url), pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


def init_sync_schema() -> None:
    Base.metadata.create_all(sync_engine)


def append_decision_sync(investigation_id: str, step: str, payload: dict[str, Any]) -> None:
    with SyncSessionLocal() as s:
        s.add(DecisionLogEntry(investigation_id=investigation_id, step=step, payload=payload))
        s.commit()


def health_sync() -> bool:
    with SyncSessionLocal() as s:
        s.execute(text("SELECT 1"))
    return True
