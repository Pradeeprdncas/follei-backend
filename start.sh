#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${ROOT_DIR}/logs/runtime"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
PORT="${PORT:-8000}"
FULL_PROFILE=0
NO_INFRA=0
CHECK_ONLY=0
INSTALL_BROWSER=0
KEEP_RUNNING=0

usage() {
  cat <<'EOF'
Usage: ./start.sh [--full] [--no-infra] [--check] [--install-browser] [--keep-running]

  default            API + indexing + knowledge sync + Google sync + website crawl
  --full             Also start analysis, lead scoring, mail, flow, and HubSpot workers
  --no-infra         Do not run Docker Compose; use externally managed infrastructure
  --check            Validate configuration/imports and print the service plan only
  --install-browser  Install Playwright Chromium for JavaScript-heavy website crawling
  --keep-running     Reuse already-running Follei services instead of restarting them
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) FULL_PROFILE=1 ;;
    --no-infra) NO_INFRA=1 ;;
    --check) CHECK_ONLY=1 ;;
    --install-browser) INSTALL_BROWSER=1 ;;
    --keep-running) KEEP_RUNNING=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "[ERROR] Unknown option: $1"; usage; exit 2 ;;
  esac
  shift
done

mkdir -p "${RUNTIME_DIR}"
[[ -f "${ROOT_DIR}/.env" ]] || { echo "[ERROR] ${ROOT_DIR}/.env is missing."; exit 1; }

venv_has_pip() {
  [[ -x "$1" ]] && "$1" -m pip --version >/dev/null 2>&1
}

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="${PYTHON_BIN}"
elif venv_has_pip "${ROOT_DIR}/.venv/bin/python"; then
  PYTHON="${ROOT_DIR}/.venv/bin/python"
elif venv_has_pip "${ROOT_DIR}/venv/bin/python"; then
  PYTHON="${ROOT_DIR}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "[ERROR] Python was not found. Set PYTHON_BIN or create .venv."
  exit 1
fi

echo "[1/6] Checking the lightweight runtime imports..."
check_core_imports() {
  (
    cd "${ROOT_DIR}"
    "${PYTHON}" -c "import alembic,fastapi,psycopg2,uvicorn,kafka,qdrant_client,pymongo,boto3,redis; from app.main import app; from app.workers.indexing_consumer import IndexingWorker; from app.workers.knowledge_sync_consumer import KnowledgeSyncWorker; from app.workers.google_workspace_worker import GoogleWorkspaceWorker; from app.workers.website_ingestion_worker import WebsiteIngestionWorker"
  )
}

if ! check_core_imports >/dev/null 2>&1; then
  if ! venv_has_pip "${ROOT_DIR}/.venv/bin/python"; then
    echo "[INFO] Creating the lightweight .venv..."
    if ! "${PYTHON}" -m venv "${ROOT_DIR}/.venv"; then
      echo "[ERROR] Python cannot create a virtual environment with pip."
      echo "        Debian/Ubuntu: sudo apt install python3-venv"
      echo "        Then run ./start.sh again."
      exit 1
    fi
  fi
  PYTHON="${ROOT_DIR}/.venv/bin/python"
  echo "[INFO] Installing requirements-core.txt..."
  "${PYTHON}" -m pip install -r "${ROOT_DIR}/requirements-core.txt"
fi
check_core_imports

echo "[INFO] Effective OAuth redirect URIs:"
(
  cd "${ROOT_DIR}"
  "${PYTHON}" - <<'PY'
from app.config.settings import get_settings

settings = get_settings()
print(f"  GOOGLE_AUTH_OAUTH_REDIRECT_URI={settings.GOOGLE_AUTH_OAUTH_REDIRECT_URI}")
print(f"  GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI={settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI}")
print(f"  GMAIL_OAUTH_REDIRECT_URI={settings.GMAIL_OAUTH_REDIRECT_URI}")
PY
)

if [[ "${FULL_PROFILE}" == "1" ]] && ! "${PYTHON}" -c "import torch,transformers,peft,soundfile,librosa,noisereduce,gtts" >/dev/null 2>&1; then
  echo "[INFO] Installing the optional local/voice AI dependencies..."
  "${PYTHON}" -m pip install -r "${ROOT_DIR}/requirements-optional-ai.txt"
fi

if [[ "${INSTALL_BROWSER}" == "1" ]]; then
  echo "[2/6] Installing Playwright Chromium..."
  "${PYTHON}" -m playwright install chromium
else
  echo "[2/6] Browser installation skipped (use --install-browser when needed)."
fi

print_plan() {
  echo "Core Python services:"
  echo "  1. API (OAuth, validation, onboarding checks, retrieval)"
  echo "  2. Indexing worker (parse, classify, chunk, embed)"
  echo "  3. Knowledge-sync worker (FerretDB/Qdrant projection)"
  echo "  4. Google Workspace sync worker"
  echo "  5. Website ingestion worker"
  if [[ "${FULL_PROFILE}" == "1" ]]; then
    echo "Optional full-profile workers: analysis, lead scoring, mail, flows, HubSpot"
  fi
}

if [[ "${CHECK_ONLY}" == "1" ]]; then
  print_plan
  echo "[OK] Runtime check passed; nothing was started."
  exit 0
fi

echo "[3/6] Starting required infrastructure..."
if [[ "${NO_INFRA}" == "0" ]] && command -v docker >/dev/null 2>&1; then
  docker compose -p follei-backend-team -f "${COMPOSE_FILE}" up -d \
    postgres redis qdrant minio ferretdb-postgres ferretdb zookeeper kafka
elif [[ "${NO_INFRA}" == "0" ]]; then
  echo "[WARN] Docker is unavailable; expecting infrastructure to be externally managed."
else
  echo "[SKIP] Docker Compose disabled by --no-infra."
fi

echo "[4/6] Reconciling the database and queue..."
(
  cd "${ROOT_DIR}"
  "${PYTHON}" "${ROOT_DIR}/scripts/ensure_local_postgres_access.py"
  "${PYTHON}" "${ROOT_DIR}/scripts/wait_for_kafka.py" --timeout 120
  "${PYTHON}" -m app.database.bootstrap
)

is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(head -n 1 "${pid_file}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

stop_existing_service() {
  local name="$1" marker="$2"
  local pid_file="${RUNTIME_DIR}/${marker}.pid"
  if ! is_running "${pid_file}"; then
    return
  fi
  local pid
  pid="$(head -n 1 "${pid_file}")"
  echo "[INFO] Restarting ${name} (stopping PID ${pid}) so code and .env changes are loaded."
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -TERM "${pid}" 2>/dev/null || true
    sleep 1
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    kill -KILL "${pid}" 2>/dev/null || true
  fi
  if [[ -f "${pid_file}" ]]; then
    mv "${pid_file}" "${pid_file}.previous"
  fi
}

start_service() {
  local name="$1" marker="$2"
  shift 2
  local pid_file="${RUNTIME_DIR}/${marker}.pid"
  local out_log="${RUNTIME_DIR}/${marker}.out.log"
  local err_log="${RUNTIME_DIR}/${marker}.err.log"
  if [[ "${KEEP_RUNNING}" == "1" ]] && is_running "${pid_file}"; then
    echo "[OK] ${name} already running (PID $(head -n 1 "${pid_file}"))."
    return
  fi
  stop_existing_service "${name}" "${marker}"
  (
    cd "${ROOT_DIR}"
    nohup "${PYTHON}" -u "$@" >>"${out_log}" 2>>"${err_log}" &
    echo "$!" >"${pid_file}"
  )
  sleep 1
  is_running "${pid_file}" || { echo "[ERROR] ${name} failed; see ${err_log}."; exit 1; }
  echo "[OK] ${name} started (PID $(head -n 1 "${pid_file}"))."
}

echo "[5/6] Starting the core service profile..."
start_service "Follei API" "api" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
start_service "Indexing worker" "indexing-worker" -m app.workers.indexing_consumer
start_service "Knowledge-sync worker" "knowledge-sync-worker" -m app.workers.knowledge_sync_consumer
start_service "Google Workspace worker" "google-workspace-worker" -m app.workers.google_workspace_worker
start_service "Website ingestion worker" "website-ingestion-worker" -m app.workers.website_ingestion_worker

if [[ "${FULL_PROFILE}" == "1" ]]; then
  start_service "Conversation-analysis worker" "analysis-worker" -m app.analysis.workers.analysis_worker
  start_service "Lead-scoring worker" "lead-scoring-worker" -m app.workers.lead_scoring_worker
  start_service "Mail operations worker" "mail-operations-worker" -m app.workers.mail_operations_worker
  start_service "Flow execution worker" "flow-execution-worker" -m app.workers.flow_execution_worker
  start_service "HubSpot sync worker" "hubspot-sync-worker" -m app.workers.hubspot_sync_worker
fi

health_url="http://127.0.0.1:${PORT}/health/"
for _ in $(seq 1 90); do
  curl --fail --silent "${health_url}" | grep -q '"status":"healthy"' && break
  sleep 1
done
curl --fail --silent "${health_url}" | grep -q '"status":"healthy"' || {
  echo "[ERROR] API did not become healthy. See ${RUNTIME_DIR}/api.err.log."
  exit 1
}

echo "[6/6] Follei core runtime is ready."
print_plan
echo "API docs: http://127.0.0.1:${PORT}/docs"
echo "Logs/PIDs: ${RUNTIME_DIR}"
