#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME_DIR="${ROOT_DIR}/logs/runtime"

services=(
  "Follei API|api"
  "Indexing worker|indexing-worker"
  "Knowledge sync|knowledge-sync-worker"
  "Google Workspace|google-workspace-worker"
  "Website ingestion|website-ingestion-worker"
)

if [[ "${2:-}" == "--full" ]]; then
  services+=(
    "Conversation analysis|analysis-worker"
    "Lead scoring|lead-scoring-worker"
    "Mail operations|mail-operations-worker"
    "Flow execution|flow-execution-worker"
    "HubSpot sync|hubspot-sync-worker"
  )
fi

if ! command -v gnome-terminal >/dev/null 2>&1 || [[ -z "${DISPLAY:-}" ]]; then
  echo "[WARN] A graphical terminal is unavailable. Follow logs with:"
  echo "       tail -n 100 -F ${RUNTIME_DIR}/*.out.log ${RUNTIME_DIR}/*.err.log"
  exit 0
fi

open_tab() {
  local mode="$1" title="$2" out_log="$3" err_log="$4"
  gnome-terminal "${mode}" --title="${title}" -- \
    bash -lc "printf '\033]0;%s\007' '${title}'; echo '=== ${title} ==='; echo 'stdout: ${out_log}'; echo 'stderr: ${err_log}'; exec tail -n 100 -F '${out_log}' '${err_log}'" \
    >/dev/null 2>&1
}

mode="--window"
for item in "${services[@]}"; do
  IFS='|' read -r title stem <<<"${item}"
  out_log="${RUNTIME_DIR}/${stem}.out.log"
  err_log="${RUNTIME_DIR}/${stem}.err.log"
  touch "${out_log}" "${err_log}"
  # Commands following `--` consume the rest of a gnome-terminal invocation,
  # so each tab must be requested separately. GNOME Terminal's D-Bus server
  # attaches `--tab` calls to the most recently opened window.
  open_tab "${mode}" "${title}" "${out_log}" "${err_log}"
  mode="--tab"
done
