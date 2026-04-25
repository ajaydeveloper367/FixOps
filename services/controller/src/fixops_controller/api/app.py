"""HTTP ingress — alerts and bounded query intents (AD-013) share the same graph."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sqlalchemy.engine.url import make_url

from fixops_controller.db.sync_session import init_sync_schema
from fixops_controller.graph.build import build_compiled_graph
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


app = FastAPI(title="FixOps Controller", lifespan=lifespan)


class RunInvestigationRequest(BaseModel):
    """Either pass `normalized` directly or `bounded_intent` for query path."""

    thread_id: str | None = None
    normalized: dict[str, Any] | None = None
    bounded_intent: dict[str, Any] | None = Field(
        default=None,
        description="AD-013 synthetic alert + session",
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/investigations/run")
def run_investigation(body: RunInvestigationRequest) -> dict[str, Any]:
    graph = app.state.graph
    if body.bounded_intent:
        syn = body.bounded_intent.get("synthetic_alert") or {}
        normalized = {
            "source": "query",
            "environment": settings.environment,
            "raw": body.bounded_intent,
            "session_id": body.bounded_intent.get("session_id"),
        }
    elif body.normalized:
        normalized = body.normalized
    else:
        raise HTTPException(400, "Provide normalized or bounded_intent")
    cfg: dict[str, Any] = {"configurable": {"thread_id": body.thread_id or "default"}}
    try:
        out = graph.invoke({"normalized": normalized}, config=cfg)
    except Exception as e:
        raise HTTPException(502, detail=str(e)) from e
    return {"state": out}
