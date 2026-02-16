#!/usr/bin/env sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "[smoke-api] python interpreter not found (python3/python)" >&2
    exit 1
  fi
fi

echo "[smoke-api] API_BASE_URL=${API_BASE_URL}"

health_json="$(curl -fsS "${API_BASE_URL}/health")"
ready_json="$(curl -fsS "${API_BASE_URL}/ready")"
curl -fsS "${API_BASE_URL}/metrics" >/dev/null

HEALTH_JSON="${health_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["HEALTH_JSON"])
assert payload.get("status") in {"ok", "degraded"}, payload
services = payload.get("services") or {}
assert services.get("database") == "up", payload
assert services.get("redis") == "up", payload
assert services.get("worker_alive") is True, payload
print("[smoke-api] health checks passed")
PY

READY_JSON="${ready_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["READY_JSON"])
assert payload.get("status") == "ready", payload
print("[smoke-api] ready check passed")
PY

timestamp="$(date +%s)"
signup_payload="$(cat <<EOF
{"company_name":"Smoke ${timestamp}","owner_email":"smoke.${timestamp}@local.test","owner_password":"Passw0rd!123"}
EOF
)"

signup_json="$(curl -fsS -X POST "${API_BASE_URL}/signup" -H "Content-Type: application/json" -d "${signup_payload}")"

tenant_id="$(SIGNUP_JSON="${signup_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["SIGNUP_JSON"])
print(payload["company"]["id"])
PY
)"

email="smoke.${timestamp}@local.test"
login_payload="$(cat <<EOF
{"email":"${email}","password":"Passw0rd!123"}
EOF
)"

login_json="$(curl -fsS -X POST "${API_BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: ${tenant_id}" \
  -d "${login_payload}")"

access_token="$(LOGIN_JSON="${login_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["LOGIN_JSON"])
print(payload["access_token"])
PY
)"

auth_header="Authorization: Bearer ${access_token}"
tenant_header="X-Tenant-ID: ${tenant_id}"

project_json="$(curl -fsS -X POST "${API_BASE_URL}/projects" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke Project"}')"

project_id="$(PROJECT_JSON="${project_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["PROJECT_JSON"])
print(payload["id"])
PY
)"

curl -fsS -X POST "${API_BASE_URL}/channels" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\":\"${project_id}\",\"type\":\"website\"}" >/dev/null

curl -fsS -X POST "${API_BASE_URL}/posts" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\":\"${project_id}\",\"title\":\"Smoke\",\"content\":\"Smoke content\"}" >/dev/null

curl -fsS "${API_BASE_URL}/feature-flags" \
  -H "${auth_header}" \
  -H "${tenant_header}" >/dev/null

curl -fsS "${API_BASE_URL}/billing/current" \
  -H "${auth_header}" \
  -H "${tenant_header}" >/dev/null

echo "[smoke-api] workflow checks passed"
echo "[smoke-api] OK"
