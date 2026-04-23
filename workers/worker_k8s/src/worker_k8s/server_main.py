"""Run the worker HTTP service (uvicorn)."""

from __future__ import annotations

import uvicorn

from worker_k8s.config import WorkerK8sSettings
from worker_k8s.http_server import app


def main() -> None:
    s = WorkerK8sSettings()
    uvicorn.run(
        app,
        host=s.http_host,
        port=s.http_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
