"""Invoke / resume LangGraph with stable HTTP shapes (HIL / AD-003)."""

from __future__ import annotations

from typing import Any

from langgraph.types import Command


def pack_interrupts(raw: list[Any] | tuple[Any, ...] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for x in raw:
        if hasattr(x, "id") and hasattr(x, "value"):
            out.append({"id": getattr(x, "id"), "value": getattr(x, "value")})
    return out


def invoke_or_interrupt(graph: Any, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Single invoke; surfaces LangGraph interrupts as ``status: awaiting_approval``."""
    out: dict[str, Any] = dict(graph.invoke(payload, config=config))
    intr = out.pop("__interrupt__", None)
    tid = (config.get("configurable") or {}).get("thread_id")
    if intr:
        return {
            "status": "awaiting_approval",
            "thread_id": tid,
            "interrupts": pack_interrupts(intr),
            "state": out,
        }
    return {"status": "completed", "thread_id": tid, "state": out}


def resume_thread(graph: Any, resume: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Resume after ``interrupt()`` in ``await_approval`` using the same ``thread_id``."""
    out = dict(graph.invoke(Command(resume=resume), config=config))
    intr = out.pop("__interrupt__", None)
    tid = (config.get("configurable") or {}).get("thread_id")
    if intr:
        return {
            "status": "awaiting_approval",
            "thread_id": tid,
            "interrupts": pack_interrupts(intr),
            "state": out,
        }
    return {"status": "completed", "thread_id": tid, "state": out}
