#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.fixops-services"
PID_DIR="${RUNTIME_DIR}/pids"
LOG_DIR="${RUNTIME_DIR}/logs"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

if [[ -x "${ROOT_DIR}/.venv/bin/uv" ]]; then
  UV_BIN="${ROOT_DIR}/.venv/bin/uv"
elif command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
else
  echo "uv not found. Install uv or create .venv with uv available." >&2
  exit 1
fi

SERVICES=(
  "controller|fixops_controller.api.app:app|8080"
  "worker-obs|fixops_worker_obs.app:app|8081"
  "executor|fixops_executor.app:app|8082"
  "worker-k8s|fixops_worker_k8s.app:app|8083"
  "worker-pipeline|fixops_worker_pipeline.app:app|8084"
  "worker-db|fixops_worker_db.app:app|8085"
  "worker-app-rca|fixops_worker_app_rca.app:app|8086"
)

usage() {
  cat <<'EOF'
Usage:
  ./fixops-services.sh start [service-name]
  ./fixops-services.sh stop [service-name]
  ./fixops-services.sh status [service-name]

Examples:
  ./fixops-services.sh start
  ./fixops-services.sh status controller
  ./fixops-services.sh stop worker-k8s
EOF
}

service_line() {
  local target="$1"
  local line
  for line in "${SERVICES[@]}"; do
    if [[ "${line%%|*}" == "${target}" ]]; then
      echo "${line}"
      return 0
    fi
  done
  return 1
}

pid_file() {
  echo "${PID_DIR}/$1.pid"
}

log_file() {
  echo "${LOG_DIR}/$1.log"
}

is_running() {
  local name="$1"
  local pf
  pf="$(pid_file "${name}")"
  if [[ ! -f "${pf}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${pf}")"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  kill -0 "${pid}" >/dev/null 2>&1
}

start_one() {
  local line="$1"
  local name module port
  IFS='|' read -r name module port <<<"${line}"

  if is_running "${name}"; then
    echo "[start] ${name}: already running (pid $(cat "$(pid_file "${name}")"))"
    return 0
  fi

  rm -f "$(pid_file "${name}")"
  local lf
  lf="$(log_file "${name}")"
  (
    cd "${ROOT_DIR}"
    nohup "${UV_BIN}" run uvicorn "${module}" --host 127.0.0.1 --port "${port}" >"${lf}" 2>&1 &
    echo $! >"$(pid_file "${name}")"
  )
  sleep 0.4
  if is_running "${name}"; then
    echo "[start] ${name}: started (pid $(cat "$(pid_file "${name}")"), port ${port})"
  else
    echo "[start] ${name}: failed to start, check ${lf}" >&2
    return 1
  fi
}

stop_one() {
  local line="$1"
  local name module port
  IFS='|' read -r name module port <<<"${line}"

  if ! is_running "${name}"; then
    local probe
    probe="$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}/healthz" 2>/dev/null || true)"
    if [[ "${probe}" == "200" ]]; then
      echo "[stop]  ${name}: running but unmanaged (no pid file); stop it from its original terminal/process"
      return 0
    fi
    rm -f "$(pid_file "${name}")"
    echo "[stop]  ${name}: not running"
    return 0
  fi

  local pid
  pid="$(cat "$(pid_file "${name}")")"
  kill "${pid}" >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi
  rm -f "$(pid_file "${name}")"
  echo "[stop]  ${name}: stopped"
}

status_one() {
  local line="$1"
  local name module port
  IFS='|' read -r name module port <<<"${line}"
  local health="n/a"
  local pid="-"
  if is_running "${name}"; then
    pid="$(cat "$(pid_file "${name}")")"
    health="$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}/healthz" 2>/dev/null || true)"
    [[ -z "${health}" ]] && health="000"
    printf "[status] %-15s running(managed) pid=%-7s port=%-5s health=%s\n" "${name}" "${pid}" "${port}" "${health}"
  else
    health="$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}/healthz" 2>/dev/null || true)"
    [[ -z "${health}" ]] && health="000"
    if [[ "${health}" == "200" ]]; then
      printf "[status] %-15s running(unmanaged) pid=%-7s port=%-5s health=%s\n" "${name}" "-" "${port}" "${health}"
    else
      printf "[status] %-15s stopped pid=%-7s port=%-5s health=%s\n" "${name}" "-" "${port}" "000"
    fi
  fi
}

run_for_selection() {
  local action="$1"
  local selected="${2:-}"
  local line
  if [[ -n "${selected}" ]]; then
    if ! line="$(service_line "${selected}")"; then
      echo "Unknown service: ${selected}" >&2
      exit 1
    fi
    "${action}_one" "${line}"
    return 0
  fi

  for line in "${SERVICES[@]}"; do
    "${action}_one" "${line}"
  done
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi
  local cmd="$1"
  local selected="${2:-}"
  case "${cmd}" in
    start) run_for_selection start "${selected}" ;;
    stop) run_for_selection stop "${selected}" ;;
    status) run_for_selection status "${selected}" ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
