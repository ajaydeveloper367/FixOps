# FixOps Agentic

Rules-first incident investigation: **one LangGraph controller**, **standalone HTTP workers**, **AD-006** payloads only, **Postgres** for inventory/graph/checkpoints/decision log, **human gate** before mutation (**AD-003**).

**Per-service configuration (independent deploy):**

| File | Service |
|------|---------|
| `config/controller.yaml` | Controller only — override path with `FIXOPS_CONTROLLER_CONFIG` |
| `config/worker-obs.yaml` | `worker-obs` only — override path with `FIXOPS_WORKER_OBS_CONFIG` |

Env vars `FIXOPS_*` / `FIXOPS_WORKER_*` still **override** YAML when set. Each container can mount **only its** YAML (or bake it into the image).

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

**Terminal 1 — worker (AD-006):** reads `config/worker-obs.yaml` (Prometheus JSON API: `http://localhost:6060` + `/api/v1/query` — not `/query`, which is the HTML UI). Run from repo root or set `FIXOPS_WORKER_OBS_CONFIG`. For pods, `/investigate` tries several instant queries in order (`up{namespace=…}`, `job` from `labels.app`, `namespace=default`, then `count(up)`) so local dev still gets a signal when alert namespaces do not match scrape labels.

```bash
uv run uvicorn fixops_worker_obs.app:app --host 127.0.0.1 --port 8081
```

**Terminal 2 — executor (stub):**

```bash
uv run uvicorn fixops_executor.app:app --host 127.0.0.1 --port 8082
```

**Terminal 3 — controller (no LLM — mock extract + mock RCA):**

```bash
export FIXOPS_MOCK_LLM=1
export FIXOPS_WORKER_OBS_BASE_URL=http://127.0.0.1:8081
export FIXOPS_EXECUTOR_URL=http://127.0.0.1:8082
export FIXOPS_ROUTING_RULES_PATH="$(pwd)/config/routing_rules.yaml"
uv run uvicorn fixops_controller.api.app:app --host 127.0.0.1 --port 8080
```

**Terminal 3 — controller (local LLM, e.g. Ollama OpenAI-compatible API):**

```bash
export FIXOPS_MOCK_LLM=0
export FIXOPS_LLM_BASE_URL=http://127.0.0.1:11434/v1
export FIXOPS_LLM_MODEL=llama3.2:latest
# Ollama often rejects json_object response_format; disable for local:
export FIXOPS_LLM_USE_JSON_RESPONSE_FORMAT=0
# Optional; omit if your server ignores auth:
# export FIXOPS_LLM_API_KEY=ollama
export FIXOPS_WORKER_OBS_BASE_URL=http://127.0.0.1:8081
export FIXOPS_EXECUTOR_URL=http://127.0.0.1:8082
export FIXOPS_ROUTING_RULES_PATH="$(pwd)/config/routing_rules.yaml"
uv run uvicorn fixops_controller.api.app:app --host 127.0.0.1 --port 8080
```

**Trigger a run:**

Use **compact JSON** or **jq** so the request body is valid (pretty-printed `$(cat …)` inside `-d "..."` often breaks the outer JSON).

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/investigations/run \
  -H 'Content-Type: application/json' \
  -d '{"thread_id":"demo-1","normalized":{"source":"alert","environment":"development","raw":{"alertname":"PodCrashLoopBackOff","namespace":"prod","pod":"checkout-api-7d8f9","labels":{"entity_type":"pod","app":"checkout-api"}}}}' | python3 -m json.tool
```

With **jq** (safe merge of the fixture file):

```bash
jq -n --slurpfile n fixtures/alert_pod_crash.json '{thread_id:"demo-1", normalized:$n[0]}' \
  | curl -sS -X POST http://127.0.0.1:8080/v1/investigations/run -H 'Content-Type: application/json' -d @- | python3 -m json.tool
```

If **`controller_api_key`** is set in `config/controller.yaml` (or **`FIXOPS_CONTROLLER_API_KEY`**), add **`Authorization: Bearer <key>`** or **`X-API-Key: <key>`** to **`/v1/investigations/run`**, **`/v1/threads/.../resume`**, and **`/v1/threads/.../snapshot`**. **`/healthz`** stays open for probes.

If **`detail`** mentions **`Expecting value`** or **empty message content**, the controller reached **Ollama** but the model returned **empty or non-JSON** text; keep **`ollama serve`**, try another model, or set **`mock_llm: true`** in `config/controller.yaml` to test the rest of the pipeline without the LLM.

Response shape:

- **`status": "completed"`** — graph finished (same `thread_id`). Body includes **`state`** (graph output).
- **`status": "awaiting_approval"`** — paused at human gate when **`require_human_approval: true`** in `config/controller.yaml`. Body includes **`interrupts`** (each has `id` + `value`) and **`state`** (RCA, etc.). Call resume with the **same** `thread_id`.

**Resume after approval (same `thread_id`):**

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/threads/demo-1/resume" \
  -H 'Content-Type: application/json' \
  -d '{"resume": {"granted": true, "approved_by": "you@example.com"}}'
```

**Debug checkpoint:** `GET http://127.0.0.1:8080/v1/threads/{thread_id}/snapshot`

For local one-shot runs without a second HTTP call, set **`require_human_approval: false`** in `config/controller.yaml`.

**Local Postgres (`config/controller.yaml`):** the controller uses **`database_url`** for the decision log / inventory and **`checkpoint_backend: postgres`** for LangGraph HIL state. **`GRANT ALL ON DATABASE`** and **`GRANT ALL ON ALL TABLES`** do not grant **`CREATE` on schema `public`**, which is required to create *new* tables (e.g. LangGraph `checkpoint_*`). If you see “permission denied for schema public”, run the small extra grants file as a role that can grant on `public` (DB owner is enough—not necessarily a cluster superuser):

```bash
psql "postgresql://…@127.0.0.1:5432/fixops" -f scripts/postgres_fixops_grants.sql
```

Override the URL or password with **`FIXOPS_DATABASE_URL`** (see `config/controller.yaml` comments). Integration check: `pytest tests/integration/test_postgres_checkpoint.py -m integration -v`.

## Workers today and next steps

**Workers implemented as separate HTTP services today: one** — `services/worker-obs` (`worker-obs`, observability / Prometheus-shaped checks, AD-006).

Also in the repo (not counted as domain workers): **`services/executor`** (post-approval mutations only) and **`services/mcp-fixops-obs`** (tool surface, MCP).

**Reasonable next steps (architecture order):**

1. **Second domain worker** — e.g. `worker-k8s` (events/pods) behind an adapter or MCP; register in `routing_rules.yaml` + controller env registry.
2. **HIL polish** — auth on `POST /v1/threads/{thread_id}/resume`, approval audit store, richer interrupt payload.
3. **Real observability** — tune `config/worker-obs.yaml` (or env) for Prometheus/Loki; optionally MCP from the worker.
4. **RAG (AD-009)** — bounded chunks into RCA stage; pgvector or BM25 in Postgres.
5. **Production Postgres** — checkpoints + decision log + inventory on the same DB as in Docker Compose.

## CI (GitHub Actions)

On push / PR: **Ruff** on `services/`, `packages/`, `tests/`; **`pytest -m "not integration"`** (fast unit suite); a separate job runs **`pytest -m integration`** (Prometheus / Postgres checks **skip** on the default runner unless you add services or secrets).

Local match for the default job:

```bash
uv sync && uv run pytest -q -m "not integration"
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
| `config/` | `controller.yaml`, `worker-obs.yaml`, `routing_rules.yaml`, `inventory.yaml`, `graph_edges.yaml` |
| `fixtures/` | Sample alert + query-intent JSON |

## Add a worker

1. Implement `POST /investigate` returning **AD-006** (`WorkerResult` in contract).
2. Accept **refs only** (`credentials_ref`, `cluster_id`); resolve secrets inside the worker (**AD-012**).
3. Register `worker_id` → base URL in controller settings / env and add **routing rules** in `config/routing_rules.yaml`.
4. Never call other workers; only the controller invokes you.

## Routing

Deterministic **YAML** table (`config/routing_rules.yaml`): match `entity_type`, `alert_class`, etc. The LLM only fills `ExtractedEntity`; it does **not** pick the next hop.

Reference example projects under `context/exampleProjects/` for hardened tools/MCP patterns — **do not** adopt their orchestration as the controller.
