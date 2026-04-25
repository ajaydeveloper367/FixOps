"""HTTP ingress — alerts and bounded query intents (AD-013) share the same graph."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from langgraph.errors import EmptyInputError
from pydantic import BaseModel, Field

from sqlalchemy.engine.url import make_url

from fixops_controller.api.auth import require_controller_api_key
from fixops_controller.api.graph_invoke import invoke_or_interrupt, resume_thread
from fixops_controller.db.sync_session import init_sync_schema
from fixops_controller.graph.build import build_compiled_graph, close_checkpoint_pool
from fixops_controller.inventory.seed import seed_inventory_and_graph
from fixops_controller.settings import settings


def _ensure_sqlite_parent_dir(url: str) -> None:
    u = make_url(url)
    if u.get_backend_name() != "sqlite":
        return
    db = u.database
    if not db or db == ":memory:":
        return
    Path(db).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_sqlite_parent_dir(settings.database_url)
    init_sync_schema()
    inv = Path(settings.inventory_seed_path)
    gr = Path(settings.graph_seed_path)
    if inv.exists() and gr.exists():
        seed_inventory_and_graph(inv, gr)
    app.state.graph = build_compiled_graph()
    yield
    close_checkpoint_pool()


app = FastAPI(title="FixOps Controller", lifespan=lifespan)


class RunInvestigationRequest(BaseModel):
    """Either pass `normalized` directly or `bounded_intent` for query path."""

    thread_id: str | None = None
    normalized: dict[str, Any] | None = None
    bounded_intent: dict[str, Any] | None = Field(
        default=None,
        description="AD-013 synthetic alert + session",
    )


class ResumeThreadRequest(BaseModel):
    """Payload passed to LangGraph ``Command(resume=...)`` (e.g. ``{\"granted\": true}``)."""

    resume: dict[str, Any] = Field(default_factory=dict)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _normalized_from_body(body: RunInvestigationRequest) -> dict[str, Any]:
    if body.bounded_intent:
        return {
            "source": "query",
            "environment": settings.environment,
            "raw": body.bounded_intent,
            "session_id": body.bounded_intent.get("session_id"),
        }
    if body.normalized:
        return body.normalized
    raise HTTPException(400, "Provide normalized or bounded_intent")


@app.post("/v1/investigations/run")
def run_investigation(
    body: RunInvestigationRequest,
    _: None = Depends(require_controller_api_key),
) -> dict[str, Any]:
    graph = app.state.graph
    normalized = _normalized_from_body(body)
    cfg: dict[str, Any] = {"configurable": {"thread_id": body.thread_id or "default"}}
    try:
        return invoke_or_interrupt(graph, {"normalized": normalized}, cfg)
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e


def _thread_has_pending_interrupt(graph: Any, cfg: dict[str, Any]) -> bool:
    """LangGraph only accepts ``Command(resume=...)`` while an ``interrupt()`` is pending."""
    snap = graph.get_state(cfg)
    return bool(snap.interrupts)


@app.post("/v1/threads/{thread_id}/resume")
def resume_investigation(
    thread_id: str,
    body: ResumeThreadRequest,
    _: None = Depends(require_controller_api_key),
) -> dict[str, Any]:
    """Resume a paused graph (same ``thread_id`` as ``/v1/investigations/run``)."""
    graph = app.state.graph
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if not _thread_has_pending_interrupt(graph, cfg):
        raise HTTPException(
            status_code=400,
            detail=(
                "No pending human-in-the-loop interrupt for this thread. "
                "Call POST /v1/threads/.../resume only after POST /v1/investigations/run "
                "returned status awaiting_approval for the same thread_id, and ensure "
                "require_human_approval is true in controller config."
            ),
        )
    try:
        return resume_thread(graph, body.resume, cfg)
    except EmptyInputError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get("/v1/threads/{thread_id}/snapshot")
def thread_snapshot(
    thread_id: str,
    _: None = Depends(require_controller_api_key),
) -> dict[str, Any]:
    """Debug: latest checkpoint values for a thread (optional)."""
    graph = app.state.graph
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    try:
        snap = graph.get_state(cfg)
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e
    return {"thread_id": thread_id, "values": snap.values, "next": snap.next}
