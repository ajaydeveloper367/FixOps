"""HTTP API for the K8s worker (standalone service)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from fixops_contract.models import WorkerInvestigationRequest, WorkerResponse

from worker_k8s.cluster_map import load_cluster_credentials_map
from worker_k8s.config import WorkerK8sSettings
from worker_k8s.worker import K8sWorker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Fail fast if multi-cluster map path is set but invalid."""
    s = WorkerK8sSettings()
    if s.cluster_map_path:
        load_cluster_credentials_map(s.cluster_map_path)
    yield


app = FastAPI(
    title="fixops-worker-k8s",
    summary="Kubernetes investigation worker (FixOps contract).",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/investigate", response_model=WorkerResponse)
def investigate(req: WorkerInvestigationRequest) -> WorkerResponse:
    worker = K8sWorker(WorkerK8sSettings())
    return worker.investigate(req)
