"""Assemble LangGraph (AD-014): checkpoints, conditional edges, staged context in nodes."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from fixops_controller.graph.nodes import (
    node_await_approval,
    node_confidence,
    node_executor,
    node_extract,
    node_invoke_worker,
    node_merge,
    node_normalize,
    node_rca,
    node_route,
    node_stage_context,
    route_after_approval,
)
from fixops_controller.graph.state import OpsState
from fixops_controller.settings import settings

logger = logging.getLogger(__name__)

# LangGraph PostgresSaver needs a long-lived pool (``from_conn_string`` is a short-lived context).
_checkpoint_pool: Any = None


def close_checkpoint_pool() -> None:
    """Close the LangGraph Postgres pool (e.g. FastAPI shutdown). Safe to call multiple times."""
    global _checkpoint_pool
    if _checkpoint_pool is not None:
        try:
            _checkpoint_pool.close()
        finally:
            _checkpoint_pool = None


def _postgres_checkpointer() -> Any:
    global _checkpoint_pool
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "checkpoint_backend=postgres requires langgraph checkpoint postgres and psycopg_pool"
        ) from e

    conn = settings.database_url
    if conn.startswith("sqlite:"):
        return None
    sync_uri = conn
    if sync_uri.startswith("postgresql+asyncpg://"):
        sync_uri = sync_uri.replace("postgresql+asyncpg://", "postgresql://", 1)

    if _checkpoint_pool is not None:
        try:
            _checkpoint_pool.close()
        except Exception:
            logger.exception("while closing previous checkpoint pool")

    _checkpoint_pool = ConnectionPool(
        sync_uri,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    saver = PostgresSaver(_checkpoint_pool)
    saver.setup()
    return saver


def build_compiled_graph(use_postgres_checkpoint: bool | None = None):
    g = StateGraph(OpsState)
    g.add_node("normalize", node_normalize)
    g.add_node("extract", node_extract)
    g.add_node("route", node_route)
    g.add_node("stage_context", node_stage_context)
    g.add_node("invoke_worker", node_invoke_worker)
    g.add_node("merge", node_merge)
    g.add_node("confidence", node_confidence)
    g.add_node("rca", node_rca)
    g.add_node("await_approval", node_await_approval)
    g.add_node("executor", node_executor)

    g.set_entry_point("normalize")
    g.add_edge("normalize", "extract")
    g.add_edge("extract", "route")
    g.add_edge("route", "stage_context")
    g.add_edge("stage_context", "invoke_worker")
    g.add_edge("invoke_worker", "merge")
    g.add_edge("merge", "confidence")
    g.add_edge("confidence", "rca")
    g.add_edge("rca", "await_approval")
    g.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {"executor": "executor", "end": END},
    )
    g.add_edge("executor", END)

    use_pg = settings.checkpoint_backend == "postgres" if use_postgres_checkpoint is None else use_postgres_checkpoint
    checkpointer: Any = MemorySaver()
    if use_pg:
        pg = _postgres_checkpointer()
        if pg is not None:
            checkpointer = pg
        else:
            raise RuntimeError(
                "checkpoint_backend=postgres but database_url is sqlite or Postgres checkpointer "
                "could not be created; use postgresql+asyncpg://... and see logs."
            )

    return g.compile(checkpointer=checkpointer)
