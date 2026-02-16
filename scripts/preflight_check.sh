#!/usr/bin/env sh
set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "[preflight] python interpreter not found (python3/python)" >&2
    exit 1
  fi
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

echo "[preflight] checking API health at ${API_BASE_URL}"
health_json="$(curl -fsS "${API_BASE_URL}/health")"

HEALTH_JSON="${health_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["HEALTH_JSON"])
services = payload.get("services") or {}
assert services.get("database") == "up", "database is not up"
assert services.get("redis") == "up", "redis is not up"
assert services.get("worker_alive") is True, "worker heartbeat missing"
print("[preflight] startup checks passed (db/redis/worker heartbeat)")
PY

echo "[preflight] checking readiness"
ready_json="$(curl -fsS "${API_BASE_URL}/ready")"
READY_JSON="${ready_json}" "${PYTHON_BIN}" - <<'PY'
import json
import os
payload = json.loads(os.environ["READY_JSON"])
assert payload.get("status") == "ready", payload
print("[preflight] readiness check passed")
PY

echo "[preflight] running smoke workflows"
API_BASE_URL="${API_BASE_URL}" DASHBOARD_URL="${DASHBOARD_URL}" sh "${SCRIPT_DIR}/smoke_all.sh"

echo "[preflight] checklist complete"
