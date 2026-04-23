# worker-k8s

Kubernetes investigator: uses **adapters** for API access and returns the shared `WorkerResponse` contract.

Configure with env prefix **`WORKER_K8S_`** (see `worker_k8s.config.WorkerK8sSettings`). Defaults live in **`worker-k8s.env`** next to this mini-project; optional **`.env`** in cwd overrides.

**Logs without CrashLoop:** if the alert `title` / `message` looks like a **log-line or access** issue (e.g. “error on … logs”, “S3”, “403”), the worker still **tails container logs** even when the pod is **Running** with **0 restarts**. To force that path, set `"extra": { "investigate_logs": true }` on the alert.

Optional LLM: `WORKER_K8S_LLM_BASE_URL`, `WORKER_K8S_LLM_MODEL` (Ollama OpenAI-compatible, e.g. `http://127.0.0.1:11434/v1`).

## Multi-cluster (one worker, many EKS / kubeconfigs)

Set **`WORKER_K8S_CLUSTER_MAP_PATH`** to a YAML file (see `examples/worker-k8s/cluster-map.example.yaml`). It must define a non-empty top-level **`clusters:`** map: each key is a **`cluster_id`**, each value has **`kubeconfig`** (path to a file) and optional **`context`** (AWS EKS ARNs are typical).

**Relative paths** for `WORKER_K8S_CLUSTER_MAP_PATH` are resolved from the **`workers/worker_k8s/`** directory (next to `worker-k8s.env`). A ready-made **`cluster-map.local.yaml`** is shipped with `local` and `docker-desktop` entries pointing at **`~/.kube/config`**; it is enabled by default in **`worker-k8s.env`** so alerts can use `"cluster_id": "local"` (or `"docker-desktop"`).

When this is set, every alert must include **`cluster_id`** matching one of those keys. The worker builds an **isolated Kubernetes client per request** (no shared global kubeconfig), so concurrent investigations for different clusters do not interfere.

If **`WORKER_K8S_CLUSTER_MAP_PATH`** is unset, the worker uses the legacy single-cluster settings **`WORKER_K8S_KUBECONFIG`** / **`WORKER_K8S_KUBE_CONTEXT`** (or in-cluster / default loader).

## HTTP service (standalone)

The controller talks to this worker **only over HTTP** (`POST /v1/investigate`). Bind address/port:

- `WORKER_K8S_HTTP_HOST` (default `0.0.0.0`)
- `WORKER_K8S_HTTP_PORT` (default `8080`)

Run:

```bash
fixops-worker-k8s-serve
```

Health: `GET /healthz`. Investigation: `POST /v1/investigate` with a JSON body matching `WorkerInvestigationRequest` (same schema as the file-based `fixops-worker-k8s request.json` CLI).
