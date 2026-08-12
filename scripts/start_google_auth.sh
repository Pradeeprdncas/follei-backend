#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ORIGIN="${API_ORIGIN:-http://127.0.0.1:8000}"
TENANT_NAME="${1:-Coirei}"
LOGIN_HINT="${2:-pradeep824567@gmail.com}"
response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT

curl --fail --silent --show-error \
  -X POST "${API_ORIGIN}/api/v1/auth/google/start" \
  -H 'Content-Type: application/json' \
  --data "$("${ROOT_DIR}/.venv/bin/python" -c 'import json,sys; print(json.dumps({"tenant_name":sys.argv[1]}))' "${TENANT_NAME}")" \
  >"${response_file}"

authorization_url="$("${ROOT_DIR}/.venv/bin/python" - "${response_file}" "${LOGIN_HINT}" <<'PY'
import json, sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

payload = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
url = urlsplit(payload["authorization_url"])
query = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True) if key != "login_hint"]
query.append(("login_hint", sys.argv[2]))
print(urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment)))
PY
)"

echo "[OK] Google OAuth start returned authorization_required."
echo "[INFO] Account hint: ${LOGIN_HINT}"
echo "[INFO] Authorization URL: ${authorization_url}"
"${ROOT_DIR}/scripts/open_browser_url.sh" "${authorization_url}"
