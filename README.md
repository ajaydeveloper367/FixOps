# FixOps

Agentic operations / RCA controller with pluggable workers. This repo contains:

| Path | Role |
|------|------|
| `packages/fixops_contract` | Shared Pydantic models + tiny Ollama JSON helper |
| `controller` | Rules-first routing, orchestration, decision log, CLI (calls workers over HTTP) |
| `workers/worker_k8s` | Standalone Kubernetes investigator HTTP service + optional file CLI |

Design intent lives under `context/comparison/` (GOAL, DECISIONS).

**Runbook (start worker → controller → send alert):** [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) · **One-shot local demo:** `./scripts/run-local-investigation.sh [alert.json]`

## Requirements

- Python **3.11+**
- A reachable Kubernetes API (`KUBECONFIG` or in-cluster)
- Optional: **Ollama** (OpenAI-compatible), separate URLs/models per component

## Install (editable)

**Do not use bare `pip3` on the system Python** (Homebrew/macOS): you will get `externally-managed-environment` ([PEP 668](https://peps.python.org/pep-0668/)). Always use a **venv** (or `pipx`).

From the repo root:

```bash
cd /path/to/FixOps
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e "./packages/fixops_contract"
python3 -m pip install -e "./workers/worker_k8s"
python3 -m pip install -e "./controller"
```

`fixops-contract` must be installed first. **Controller** and **worker-k8s** are separate deployables: the controller does **not** depend on the `worker-k8s` Python package at runtime—only on **`httpx`** and a configured **`CONTROLLER_WORKER_K8S_BASE_URL`**.

After activation, run CLIs with `fixops-controller` (or `.venv/bin/fixops-controller` without activating).

## Configure

**Per mini-project (tracked):** edit **`controller/controller.env`** (controller only) and **`workers/worker_k8s/worker-k8s.env`** (worker only). Paths are resolved from each package, so you do **not** need a specific `cwd`. Optional overrides: **`.env`** in the **current working directory** when the process runs (often repo root; gitignored).

**Controller** (env prefix `CONTROLLER_`):

- **`CONTROLLER_WORKER_K8S_BASE_URL`** — required for `investigate` (e.g. `http://127.0.0.1:8080`). If unset, the CLI exits with a clear error: Kubernetes cannot be investigated.
- `CONTROLLER_WORKER_K8S_TIMEOUT_SECONDS` — HTTP timeout for `POST /v1/investigate` (default 300).
- `CONTROLLER_DECISION_LOG_PATH` — default `controller/data/decisions.jsonl` (good mount point in prod)
- `CONTROLLER_LLM_BASE_URL` / `CONTROLLER_LLM_MODEL` — Ollama (on by default in `controller/controller.env`); comment out to disable

**K8s worker** (env prefix `WORKER_K8S_`):

- `WORKER_K8S_HTTP_HOST` / `WORKER_K8S_HTTP_PORT` — bind for `fixops-worker-k8s-serve` (defaults `0.0.0.0:8080`)
- **`WORKER_K8S_CLUSTER_MAP_PATH`** — YAML mapping `alert.cluster_id` → `{ kubeconfig, context }` for **multi-cluster** from one worker. Default in **`worker-k8s.env`** points at **`workers/worker_k8s/cluster-map.local.yaml`** (`local` / `docker-desktop` → `~/.kube/config`). Comment it out to fall back to single-cluster `KUBECONFIG` only. See `examples/worker-k8s/cluster-map.example.yaml` for EKS-style entries.
- `WORKER_K8S_KUBECONFIG` — single-cluster: path to kubeconfig (optional when cluster map is used; uses default loader if unset)
- `WORKER_K8S_KUBE_CONTEXT` — single-cluster: kube context name (optional; maps to `kube_context` in settings)
- `WORKER_K8S_LLM_BASE_URL` / `WORKER_K8S_LLM_MODEL` — Ollama (on by default in `workers/worker_k8s/worker-k8s.env`); comment out to disable; worker falls back to deterministic synthesis if the model call fails

### Ollama on your Mac (when `ollama list` says “could not connect”)

Helper script (copy anywhere, e.g. `cp scripts/ollama-llama.sh ~/ollama-llama.sh`): **`scripts/ollama-llama.sh`** — `status` | `start` | `stop` | `url` | `chat`.

1. **Start the daemon** (pick one):
   - GUI: open the **Ollama** app from Applications (it listens on `127.0.0.1:11434`).
   - CLI: `ollama serve` (leave that terminal open; or run under `tmux`/LaunchAgent).

2. **Confirm models**: `ollama list` — pull if needed: `ollama pull llama3.2`

3. **Smoke-test the same API FixOps uses** (first run can load the model for **minutes**; later calls are faster):

```bash
curl -sS http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:latest","messages":[{"role":"user","content":"Say OK in one word."}],"temperature":0}'
```

4. **Wire FixOps** — URLs/models are seeded in **`controller/controller.env`** and **`workers/worker_k8s/worker-k8s.env`**. For one-off overrides, add prefixed keys to **`.env`** (cwd when you run the CLI).

If the **controller runs inside Docker** while Ollama stays on the host, set the URLs in the relevant `*.env` to `http://host.docker.internal:11434/v1` instead of `127.0.0.1`.

## Run

See **[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md)** for step-by-step: start **`fixops-worker-k8s-serve`**, run **`fixops-controller investigate …`**, alert JSON contract, and optional **`curl`** to the worker.

Quick demo (starts worker if port is free, runs one investigation, tears down worker it started):

```bash
chmod +x scripts/run-local-investigation.sh   # once
./scripts/run-local-investigation.sh examples/alerts/loki-promtail-s3-error.json
```

For **CrashLoopBackOff** cases, use `examples/alerts/grafana-crashloop.json` (edit names if yours differ). The worker pulls **per-container `lastState` (exit code / reason)** and **previous + current log tails** for the inferred container (`extra.container` or parsed from the alert message). When logs indicate **Grafana datasource / duplicate default** issues, it also reads **mounted ConfigMaps** to list **which** names are marked `isDefault: true`.

Machine-readable full report:

```bash
fixops-controller investigate examples/alerts/grafana-crashloop.json --json
```

Inspect JSONL decisions:

```bash
tail -n 1 controller/data/decisions.jsonl | python3 -m json.tool
```

## Worker-only (debug)

```bash
# File-based: build a WorkerInvestigationRequest JSON (see contract), then:
fixops-worker-k8s request.json

# HTTP: serve POST /v1/investigate (what the controller uses)
fixops-worker-k8s-serve
```

## Alert JSON schema

```bash
fixops-controller print-alert-schema
```
