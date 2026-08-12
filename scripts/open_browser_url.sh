#!/usr/bin/env bash
set -Eeuo pipefail

url="${1:-}"
if [[ ! "${url}" =~ ^https?:// ]]; then
  echo "[ERROR] Expected an http(s) URL." >&2
  exit 2
fi
if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  echo "[ERROR] No graphical desktop is available." >&2
  echo "Open this URL manually: ${url}" >&2
  exit 1
fi

# xdg-open may report success while adding a background tab to an existing
# Chrome window on another Wayland workspace. Prefer a new foreground browser
# window so an interactive OAuth prompt is visible to the user.
if command -v google-chrome >/dev/null 2>&1; then
  output="$(google-chrome --new-window "${url}" 2>&1 || true)"
  sleep 1
  if pgrep -x chrome >/dev/null 2>&1 || pgrep -f '/opt/google/chrome/chrome' >/dev/null 2>&1; then
    echo "[OK] Opened a new Google Chrome window."
    [[ -n "${output}" ]] && echo "${output}"
    exit 0
  fi
fi

if command -v gio >/dev/null 2>&1 && gio open "${url}"; then
  echo "[OK] Opened the URL with the desktop's default browser."
  exit 0
fi
if command -v xdg-open >/dev/null 2>&1 && xdg-open "${url}"; then
  echo "[OK] Opened the URL with xdg-open."
  exit 0
fi

echo "[ERROR] The desktop browser could not be opened." >&2
echo "Open this URL manually: ${url}" >&2
exit 1
