# Getting started: worker, controller, and the alert contract

FixOps splits **orchestration** (controller) from **Kubernetes reads** (worker). They communicate only over **HTTP** using a shared **contract** (Pydantic models in `packages/fixops_contract`).

---

## 1. One-time setup

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e "./packages/fixops_contract"
python3 -m pip install -e "./workers/worker_k8s"
python3 -m pip install -e "./controller"
```

The **worker** process must be able to reach a Kubernetes API (`KUBECONFIG` on the machine where the worker runs, or in-cluster credentials). The **controller** does not need kube access if it only calls the worker over the network.

---

## 2. Configuration (defaults are already wired for local dev)

| Piece | File | What matters |
|--------|------|----------------|
| Worker | `workers/worker_k8s/worker-k8s.env` | `WORKER_K8S_CLUSTER_MAP_PATH` → `cluster-map.local.yaml` maps `cluster_id` `local` / `docker-desktop` to `~/.kube/config`. HTTP bind: `WORKER_K8S_HTTP_PORT` (default `8080`). |
| Controller | `controller/controller.env` | **`CONTROLLER_WORKER_K8S_BASE_URL`** must match the worker URL (default `http://127.0.0.1:8080`). |

Optional: copy an alert under `examples/alerts/` and set `name`, `namespace`, and `cluster_id` to match your cluster and the keys in `workers/worker_k8s/cluster-map.local.yaml`.

---

## 3. Start the Kubernetes worker (HTTP service)

In **terminal A**, from repo root (venv activated):

```bash
export KUBECONFIG=/path/to/kubeconfig   # only if you do not use ~/.kube/config
fixops-worker-k8s-serve
```

You should see Uvicorn listening (by default on **0.0.0.0:8080**). Quick check:

```bash
curl -sS http://127.0.0.1:8080/healthz
# {"status":"ok"}
```

The worker exposes:

- `GET /healthz` — liveness
- `POST /v1/investigate` — body is JSON matching **`WorkerInvestigationRequest`** (wraps **`AlertPayload`** + `stage`, etc.)

---

## 4. Start the controller (CLI)

In **terminal B**, same repo and venv:

```bash
fixops-controller investigate path/to/alert.json
```

The controller reads **`controller/controller.env`**, POSTs the built request to **`CONTROLLER_WORKER_K8S_BASE_URL`**, then prints panels (and optionally `--json` for the full report).

If the worker URL is missing, you get: *Kubernetes worker is not configured…*  
If the worker is down or unreachable: *Kubernetes worker is not available…*

---

## 5. What “sending an alert” means here

An **alert** is a JSON file that validates as **`AlertPayload`**. Minimal fields the worker cares about:

- **`cluster_id`** — when a cluster map is enabled, must match a key under `clusters:` (e.g. `local`).
- **`namespace`** — required for API queries.
- **`name`** — pod or deployment name (depending on **`entity_type`**).
- **`entity_type`** — typically `pod` or `deployment`.
- **`title` / `message`** — human text; used for heuristics (e.g. log-related wording).
- **`extra`** (optional) — e.g. `{ "container": "grafana", "investigate_logs": true }`.

Dump the JSON schema anytime:

```bash
fixops-controller print-alert-schema
```

Example files live under **`examples/alerts/`** (e.g. `loki-promtail-s3-error.json`).

---

## 6. Send an alert without the controller (call the worker directly)

Useful for debugging the worker only. `POST /v1/investigate` expects a full **`WorkerInvestigationRequest`** JSON (not a bare `AlertPayload`). The controller builds that for you; with curl, wrap the alert like this:

```bash
cd /path/to/FixOps
source .venv/bin/activate
python3 -c "
from pathlib import Path
from fixops_contract.models import WorkerInvestigationRequest, AlertPayload
alert = AlertPayload.model_validate_json(Path('examples/alerts/loki-promtail-s3-error.json').read_text())
req = WorkerInvestigationRequest(alert=alert, stage=1)
print(req.model_dump_json())
" | curl -sS -X POST http://127.0.0.1:8080/v1/investigate \
  -H "Content-Type: application/json" \
  -d @-
```

---

## 7. One-shot script (worker + investigate)

From the repo root:

```bash
./scripts/run-local-investigation.sh
./scripts/run-local-investigation.sh examples/alerts/grafana-crashloop.json
```

The script starts the worker if nothing is already listening on the chosen port, runs **`fixops-controller investigate`** against your alert (default: `examples/alerts/loki-promtail-s3-error.json`), then stops the worker **only if this script started it**.

Environment:

- **`WORKER_K8S_HTTP_PORT`** — worker listen port when the script starts a local worker (default `8080`).
- **`CONTROLLER_WORKER_K8S_BASE_URL`** — if **unset**, the script targets `http://127.0.0.1:$WORKER_K8S_HTTP_PORT` and may start that worker. If you **set** it to another host, the script **does not** start a worker; that URL must already pass `GET /healthz`.

---

## 8. Decision log

Each successful `investigate` appends a line to **`controller/data/decisions.jsonl`** (path overridable with `CONTROLLER_DECISION_LOG_PATH`).

```bash
tail -n 1 controller/data/decisions.jsonl | python3 -m json.tool
```
