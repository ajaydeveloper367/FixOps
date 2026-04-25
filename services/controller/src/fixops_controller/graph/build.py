"""Assemble LangGraph (AD-014): checkpoints, conditional edges, staged context in nodes."""

from __future__ import annotations

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


def _postgres_checkpointer():
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        return None
    conn = settings.database_url
    if conn.startswith("sqlite:"):
        return None
    if conn.startswith("postgresql+asyncpg://"):
        conn = conn.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        saver = PostgresSaver.from_conn_string(conn)
        saver.setup()
        return saver
    except Exception:
        return None


def build_compiled_graph(
    use_postgres_checkpoint: bool | None = None,
    interrupt_before_execute: bool | None = None,
):
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

    hitl = interrupt_before_execute
    if hitl is None:
        hitl = settings.environment == "production" and not settings.auto_approve_execute

    ib: list[str] | bool = ["await_approval"] if hitl else False
    return g.compile(checkpointer=checkpointer, interrupt_before=ib)
