#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
CONNECTION_ID="${1:-d95e9d70-2e64-45f8-a00e-44be1af14e67}"
RUN_ID="${2:-484305e1-44d6-4cac-b4cc-66c572250d3c}"
ACCESS_TOKEN="${FOLLEI_ACCESS_TOKEN:-}"

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[ERROR] Set FOLLEI_ACCESS_TOKEN to a real token returned by login or Google exchange."
  echo "        This verifier intentionally does not mint an internal JWT."
  exit 2
fi

request_json() {
  local label="$1" path="$2" destination="$3"
  echo "[CHECK] ${label}"
  local metrics
  metrics="$(curl --fail --show-error --silent \
    --connect-timeout 3 --max-time 15 \
    --output "${destination}" \
    --write-out 'HTTP %{http_code} in %{time_total}s' \
    "${API_BASE_URL}${path}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")"
  echo "[PASS] ${label}: ${metrics}"
}

request_json "API health" "/health/" "/tmp/follei-health.json"
request_json "Google connections" "/api/v1/integrations/google-workspace/connections" "/tmp/follei-google-connections.json"
request_json "Google Gmail insights" "/api/v1/integrations/google-workspace/connections/${CONNECTION_ID}/insights" "/tmp/follei-google-insights.json"
request_json "Google ingestion run" "/api/v1/onboarding/runs/${RUN_ID}" "/tmp/follei-google-run.json"

cd "${ROOT_DIR}"
"${ROOT_DIR}/.venv/bin/python" - <<'PY'
import json

connections = json.load(open("/tmp/follei-google-connections.json", encoding="utf-8"))["data"]["connections"]
insights = json.load(open("/tmp/follei-google-insights.json", encoding="utf-8"))["data"]["gmail"]
run = json.load(open("/tmp/follei-google-run.json", encoding="utf-8"))["data"]
print(json.dumps({
    "connections": connections,
    "run": {key: run[key] for key in ("status", "stage", "terminal", "counts")},
    "gmail": {key: insights[key] for key in ("analysis_status", "needs_confirmation", "counts", "metrics", "observations")},
}, indent=2))
PY

echo "[PASS] Google Workspace verification completed."
