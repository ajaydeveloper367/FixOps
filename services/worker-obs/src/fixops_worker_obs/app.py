"""Worker HTTP surface — only AD-006 payloads cross the boundary."""

from fastapi import FastAPI, HTTPException
from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult

from fixops_worker_obs.adapters.grafana import get_grafana_adapter
from fixops_worker_obs.adapters.loki import get_loki_adapter
from fixops_worker_obs.adapters.prometheus import get_prometheus_adapter
from fixops_worker_obs.logic import investigate

app = FastAPI(title="FixOps Worker Observability")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/investigate")
def investigate_http(req: WorkerInvestigateRequest) -> WorkerResult:
    try:
        prom = get_prometheus_adapter()
        loki = get_loki_adapter()
        grafana = get_grafana_adapter()
        return investigate(req, prom, loki=loki, grafana=grafana)
    except Exception as e:
        raise HTTPException(500, detail=str(e)) from e
