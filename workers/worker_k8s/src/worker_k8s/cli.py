"""Optional CLI to run the worker alone (debug)."""

from __future__ import annotations

import json
import sys

from fixops_contract.models import WorkerInvestigationRequest

from worker_k8s.config import WorkerK8sSettings
from worker_k8s.worker import K8sWorker


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: fixops-worker-k8s <request.json>", file=sys.stderr)
        raise SystemExit(2)
    path = sys.argv[1]
    raw = json.loads(open(path, encoding="utf-8").read())
    req = WorkerInvestigationRequest.model_validate(raw)
    worker = K8sWorker(WorkerK8sSettings())
    out = worker.investigate(req)
    print(out.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
