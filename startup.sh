#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${ROOT_DIR}/logs/runtime"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
PORT="${PORT:-8000}"
mkdir -p "${RUNTIME_DIR}"

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  echo "[ERROR] ${ROOT_DIR}/.env is missing."
  exit 1
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="${PYTHON_BIN}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON="${ROOT_DIR}/.venv/bin/python"
elif [[ -x "${ROOT_DIR}/venv/bin/python" ]]; then
  PYTHON="${ROOT_DIR}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "[ERROR] Python was not found. Set PYTHON_BIN or create .venv."
  exit 1
fi

echo "[1/6] Checking Python and mail-worker imports..."
"${PYTHON}" -c "import fastapi, uvicorn; from app.workers.mail_operations_worker import MailOperationsWorker; from app.services.communications.gmail_auto_reply import GmailAutoReplyService"

echo "[2/6] Starting local infrastructure..."
if command -v docker >/dev/null 2>&1; then
  docker compose -p follei-backend-team -f "${COMPOSE_FILE}" up -d \
    postgres redis qdrant minio ferretdb-postgres ferretdb zookeeper kafka
else
  echo "[WARN] Docker is unavailable; expecting infrastructure to be externally managed."
fi

echo "[3/6] Applying database schema..."
(
  cd "${ROOT_DIR}"
  "${PYTHON}" -m app.database.bootstrap
  "${PYTHON}" -m alembic upgrade head
)

is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(head -n 1 "${pid_file}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

start_service() {
  local name="$1"
  local marker="$2"
  shift 2
  local pid_file="${RUNTIME_DIR}/${marker}.pid"
  local out_log="${RUNTIME_DIR}/${marker}.out.log"
  local err_log="${RUNTIME_DIR}/${marker}.err.log"

  if is_running "${pid_file}"; then
    echo "[OK] ${name} already running (PID $(head -n 1 "${pid_file}"))."
    return
  fi

  (
    cd "${ROOT_DIR}"
    nohup "${PYTHON}" -u "$@" >>"${out_log}" 2>>"${err_log}" &
    echo "$!" >"${pid_file}"
  )
  sleep 1
  if ! is_running "${pid_file}"; then
    echo "[ERROR] ${name} did not remain running. See ${err_log}."
    exit 1
  fi
  echo "[OK] ${name} started (PID $(head -n 1 "${pid_file}"))."
}

echo "[4/6] Starting API and workers..."
start_service "Follei API" "api" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
start_service "Indexing worker" "indexing-worker" -m app.workers.indexing_consumer
start_service "Knowledge-sync worker" "knowledge-sync-worker" -m app.workers.knowledge_sync_consumer
start_service "Conversation-analysis worker" "analysis-worker" -m app.analysis.workers.analysis_worker
start_service "Lead-scoring worker" "lead-scoring-worker" -m app.workers.lead_scoring_worker
start_service "Mail operations worker" "mail-operations-worker" -m app.workers.mail_operations_worker
start_service "Flow execution worker" "flow-execution-worker" -m app.workers.flow_execution_worker

echo "[5/6] Waiting for API health..."
health_url="http://127.0.0.1:${PORT}/health/"
for _ in $(seq 1 90); do
  if curl --fail --silent "${health_url}" | grep -q '"status":"healthy"'; then
    break
  fi
  sleep 1
done
if ! curl --fail --silent "${health_url}" | grep -q '"status":"healthy"'; then
  echo "[ERROR] API did not become healthy. See ${RUNTIME_DIR}/api.err.log."
  exit 1
fi

echo "[6/6] Follei is ready."
echo "Tenant console: http://127.0.0.1:${PORT}/tenant"
echo "Voice console:  http://127.0.0.1:${PORT}/user"
echo "API docs:       http://127.0.0.1:${PORT}/docs"
echo "Mail worker:    Gmail inbound + campaigns + email outbox + retries"
echo "Flow worker:    active lead nurturing flows"
