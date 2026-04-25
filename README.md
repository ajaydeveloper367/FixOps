# FixOps Agentic

Rules-first incident investigation: **one LangGraph controller**, **standalone HTTP workers**, **AD-006** payloads only, **Postgres** for inventory/graph/checkpoints/decision log, **human gate** before mutation (**AD-003**).

**Specs (source of truth):**

- `context/comparison/GOAL.md`
- `context/comparison/DECISIONS.md` (AD-001 … AD-014)
- `.cursor/rules/fixops-agentic-northstar.mdc`
- `context/comparison/fixops-architecture-master.html`

## Quick start (recommended): project `.venv` + `uv`

Use **only** the virtualenv at the repo root (`.venv`). Dependency installs go through **`uv`** (`uv.lock` is the lockfile).

**1. Install `uv`** (pick one):

- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh` (then ensure `uv` is on your `PATH`), or `brew install uv`
- **No global `uv`?** One-time bootstrap *inside* a fresh venv (still ends on `uv` for everything else):

  ```bash
  cd /path/to/FixOps
  python3.12 -m venv .venv
  source .venv/bin/activate
  pip install 'uv>=0.5'
  uv sync
  ```

**2. Sync the workspace** (creates/updates `.venv`, installs all members + the `dev` group):

```bash
cd /path/to/FixOps
uv sync
```

**3. Run tests** (uses the project interpreter; no need to activate first):

```bash
uv run pytest -q
```

Optional: `source .venv/bin/activate` if you prefer a classic shell session.

Tests use a **temporary SQLite** DB unless you set `FIXOPS_DATABASE_URL` (see `tests/conftest.py`).

**Commit `uv.lock`** with application changes so CI and teammates resolve the same graph.

Fallback without `uv`: `pip install -r requirements-dev.txt` (same editable packages; prefer `uv` when you can).

## Run services locally

Use `uv run` so commands always use the project `.venv`.

**Terminal 1 — worker (AD-006):**

```bash
uv run uvicorn fixops_worker_obs.app:app --host 127.0.0.1 --port 8081
```

**Terminal 2 — executor (stub):**

```bash
uv run uvicorn fixops_executor.app:app --host 127.0.0.1 --port 8082
```

**Terminal 3 — controller:**

```bash
export FIXOPS_MOCK_LLM=1
export FIXOPS_CHECKPOINT_BACKEND=memory
export FIXOPS_WORKER_OBS_BASE_URL=http://127.0.0.1:8081
export FIXOPS_EXECUTOR_URL=http://127.0.0.1:8082
export FIXOPS_ROUTING_RULES_PATH="$(pwd)/config/routing_rules.yaml"
uv run uvicorn fixops_controller.api.app:app --host 127.0.0.1 --port 8080
```

**Trigger a run:**

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/investigations/run \
  -H 'Content-Type: application/json' \
  -d "{\"normalized\": $(cat fixtures/alert_pod_crash.json)}"
```

## Docker Compose

```bash
docker compose up --build
```

Controller: `http://localhost:8080` (Postgres checkpoints + seed inventory on startup).

Optional MCP image: `docker compose --profile mcp up mcp-fixops-obs`.

## Layout

| Path | Role |
|------|------|
| `packages/fixops-contract` | Pydantic AD-006 + ingress types |
| `services/controller` | LangGraph graph, routing, API, decision log |
| `services/worker-obs` | Observability worker (Prometheus adapter / stub) |
| `services/mcp-fixops-obs` | stdio MCP (`prometheus_query`) |
| `services/executor` | Approved actions only (stub) |
| `config/` | `routing_rules.yaml`, `inventory.yaml`, `graph_edges.yaml` |
| `fixtures/` | Sample alert + query-intent JSON |

## Add a worker

1. Implement `POST /investigate` returning **AD-006** (`WorkerResult` in contract).
2. Accept **refs only** (`credentials_ref`, `cluster_id`); resolve secrets inside the worker (**AD-012**).
3. Register `worker_id` → base URL in controller settings / env and add **routing rules** in `config/routing_rules.yaml`.
4. Never call other workers; only the controller invokes you.

## Routing

Deterministic **YAML** table (`config/routing_rules.yaml`): match `entity_type`, `alert_class`, etc. The LLM only fills `ExtractedEntity`; it does **not** pick the next hop.

Reference example projects under `context/exampleProjects/` for hardened tools/MCP patterns — **do not** adopt their orchestration as the controller.
