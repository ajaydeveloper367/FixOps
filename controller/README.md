# fixops-controller

Orchestrates investigations: **router** (rules) → **HTTP call to worker-k8s** → **decision log** + optional **LLM summary**.

The controller does **not** embed the Kubernetes worker. Set **`CONTROLLER_WORKER_K8S_BASE_URL`** (see `controller/controller.env`) to a running **`fixops-worker-k8s-serve`** instance.

Configure with env prefix **`CONTROLLER_`** (see `controller.config.ControllerSettings`). Defaults live in **`controller/controller.env`** next to this mini-project; optional **`.env`** in cwd overrides.

**Decision log:** default path is **`controller/data/decisions.jsonl`** (created on first run). Mount a volume on **`controller/data/`** in prod. The directory is listed in the repo root `.gitignore`.

Optional LLM (Ollama OpenAI-compatible): `CONTROLLER_LLM_BASE_URL`, `CONTROLLER_LLM_MODEL`.

Run (after the worker is listening on that base URL):

```bash
fixops-controller investigate examples/alerts/pod-missing.json
```
