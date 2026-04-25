"""Executor HTTP API — rejects unapproved plans in production mode."""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="FixOps Executor")


class ExecuteRequest(BaseModel):
    approved: bool = False
    plan: dict = Field(default_factory=dict)
    approval_token: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute")
def execute(body: ExecuteRequest) -> dict:
    env = os.environ.get("FIXOPS_ENVIRONMENT", "development")
    token_ok = body.approval_token == os.environ.get("FIXOPS_APPROVAL_TOKEN")
    if env == "production" and not body.approved:
        raise HTTPException(403, "approval required")
    if env == "production" and os.environ.get("FIXOPS_APPROVAL_TOKEN") and not token_ok:
        raise HTTPException(403, "invalid approval token")
    return {"status": "accepted", "executed": body.plan.get("actions", [])}
