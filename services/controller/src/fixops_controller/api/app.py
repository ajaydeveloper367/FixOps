"""HTTP ingress — strict ``/run`` (AD-013) and planner ``/run-planned`` (AD-015) share the same graph."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from langgraph.errors import EmptyInputError
from pydantic import BaseModel, Field, model_validator

from sqlalchemy.engine.url import make_url

from fixops_controller.api.auth import require_controller_api_key
from fixops_controller.api.graph_invoke import invoke_or_interrupt, resume_thread
from fixops_controller.db.sync_session import init_sync_schema
from fixops_controller.graph.build import build_compiled_graph, close_checkpoint_pool
from fixops_controller.inventory.seed import seed_inventory_and_graph
from fixops_controller.llm.planner import plan_flexible_input, planner_mode_label
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


class RunPlannedInvestigationRequest(BaseModel):
    """Planner-backed ingress (AD-015): NL and/or messy JSON → same ``normalized`` as strict ``/run``."""

    thread_id: str | None = None
    message: str | None = Field(
        default=None,
        description="Natural language alert description or operational question.",
    )
    payload: dict[str, Any] | None = Field(
        default=None,
        description="Semi-structured webhook body or partial alert; merged by planner.",
    )
    environment: str | None = Field(
        default=None,
        description="Override default environment for the planned normalized object.",
    )

    @model_validator(mode="after")
    def _require_message_or_payload(self):
        if self.payload is None and (self.message is None or not str(self.message).strip()):
            raise ValueError("Provide a non-empty message and/or payload")
        return self


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
        out = invoke_or_interrupt(graph, {"normalized": normalized}, cfg)
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e
    return out


@app.post("/v1/investigations/run-planned")
def run_planned_investigation(
    body: RunPlannedInvestigationRequest,
    _: None = Depends(require_controller_api_key),
) -> dict[str, Any]:
    """
    LLM or mock planner converts ``message`` / ``payload`` into canonical ``normalized``,
    then runs the same LangGraph as ``POST /v1/investigations/run`` (no planner on strict path).
    """
    graph = app.state.graph
    try:
        normalized = plan_flexible_input(
            message=body.message,
            payload=body.payload,
            default_environment=body.environment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(502, detail=f"planner failed: {e}") from e
    cfg: dict[str, Any] = {"configurable": {"thread_id": body.thread_id or "default"}}
    try:
        out = invoke_or_interrupt(graph, {"normalized": normalized}, cfg)
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e
    out["planning"] = {
        "normalized": normalized,
        "planner_mode": planner_mode_label(),
    }
    return out


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
        out = resume_thread(graph, body.resume, cfg)
    except EmptyInputError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e
    inv = (out.get("state") or {}).get("investigation_id") or thread_id
    _audit_hil_api_resume(
        investigation_id=str(inv),
        thread_id=thread_id,
        resume=dict(body.resume),
        graph_status=str(out.get("status") or ""),
    )
    return out


def _audit_hil_api_resume(
    *,
    investigation_id: str,
    thread_id: str,
    resume: dict[str, Any],
    graph_status: str,
) -> None:
    """Persist HTTP-level resume (AD-003 audit); uses late import so tests can patch ``sync_session``."""
    from fixops_controller.db.sync_session import append_decision_sync

    append_decision_sync(
        investigation_id,
        "hil_api_resume",
        {
            "thread_id": thread_id,
            "resume": resume,
            "graph_status": graph_status,
        },
    )


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
