#!/usr/bin/env bash
# Start worker-k8s (if needed), run fixops-controller investigate, optionally stop worker.
# Usage: ./scripts/run-local-investigation.sh [path/to/alert.json]
# Env: WORKER_K8S_HTTP_PORT (default 8080), CONTROLLER_WORKER_K8S_BASE_URL (optional override)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
BIN="${ROOT}/.venv/bin"
WORKER_PORT="${WORKER_K8S_HTTP_PORT:-8080}"
DEFAULT_WORKER_URL="http://127.0.0.1:${WORKER_PORT}"
WORKER_URL="${CONTROLLER_WORKER_K8S_BASE_URL:-${DEFAULT_WORKER_URL}}"
# Only auto-start a local worker when the controller URL is the default localhost URL.
AUTO_START_LOCAL=1
if [[ -n "${CONTROLLER_WORKER_K8S_BASE_URL:-}" && "${CONTROLLER_WORKER_K8S_BASE_URL}" != "${DEFAULT_WORKER_URL}" ]]; then
  AUTO_START_LOCAL=0
fi
ALERT_JSON="${1:-examples/alerts/loki-promtail-s3-error.json}"

if [[ ! -x "${BIN}/fixops-worker-k8s-serve" || ! -x "${BIN}/fixops-controller" ]]; then
  echo "error: missing ${BIN}/fixops-worker-k8s-serve or fixops-controller" >&2
  echo "  Run: pip install -e ./packages/fixops_contract -e ./workers/worker_k8s -e ./controller" >&2
  exit 1
fi

if [[ ! -f "${ALERT_JSON}" ]]; then
  echo "error: alert file not found: ${ALERT_JSON}" >&2
  exit 1
fi

STARTED_WORKER=0
WORKER_PID=""
BASE_URL="${WORKER_URL%/}"

if curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1; then
  echo "Using existing worker at ${WORKER_URL}"
elif [[ "${AUTO_START_LOCAL}" -eq 1 ]]; then
  echo "Starting worker on port ${WORKER_PORT} …"
  export WORKER_K8S_HTTP_PORT="${WORKER_PORT}"
  "${BIN}/fixops-worker-k8s-serve" &
  WORKER_PID=$!
  STARTED_WORKER=1
  for _ in $(seq 1 60); do
    if curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1; then
      echo "Worker is up (pid ${WORKER_PID})"
      break
    fi
    sleep 0.25
  done
  if ! curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1; then
    echo "error: worker did not become healthy at ${WORKER_URL}" >&2
    kill "${WORKER_PID}" 2>/dev/null || true
    exit 1
  fi
else
  echo "error: CONTROLLER_WORKER_K8S_BASE_URL is set to ${WORKER_URL} but /healthz is not reachable." >&2
  echo "  Start that worker yourself, or unset CONTROLLER_WORKER_K8S_BASE_URL to use ${DEFAULT_WORKER_URL}" >&2
  exit 1
fi

cleanup() {
  if [[ "${STARTED_WORKER}" -eq 1 && -n "${WORKER_PID}" ]]; then
    kill "${WORKER_PID}" 2>/dev/null || true
    wait "${WORKER_PID}" 2>/dev/null || true
    echo "Stopped worker (pid ${WORKER_PID})"
  fi
}
trap cleanup EXIT

export CONTROLLER_WORKER_K8S_BASE_URL="${WORKER_URL}"
echo "Running: fixops-controller investigate ${ALERT_JSON}"
echo "---"
"${BIN}/fixops-controller" investigate "${ALERT_JSON}"
