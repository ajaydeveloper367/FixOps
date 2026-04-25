"""Worker HTTP surface — only AD-006 payloads cross the boundary."""

from fastapi import FastAPI, HTTPException
from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult

from fixops_worker_pipeline.logic import investigate

app = FastAPI(title="FixOps Worker Pipeline")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/investigate")
def investigate_http(req: WorkerInvestigateRequest) -> WorkerResult:
    try:
        return investigate(req)
    except Exception as e:
        raise HTTPException(500, detail=str(e)) from e
