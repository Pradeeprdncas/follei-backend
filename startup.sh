#!/usr/bin/env bash
# Backward-compatible entrypoint. New documentation and automation use start.sh.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT_DIR}/start.sh" "$@"
