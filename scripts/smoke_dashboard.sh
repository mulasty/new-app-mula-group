#!/usr/bin/env sh
set -eu

DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}"

echo "[smoke-dashboard] DASHBOARD_URL=${DASHBOARD_URL}"

http_code="$(curl -s -o /tmp/control_center_dashboard_smoke.html -w "%{http_code}" "${DASHBOARD_URL}/")"
if [ "${http_code}" != "200" ]; then
  echo "[smoke-dashboard] unexpected status code: ${http_code}" >&2
  exit 1
fi

if ! grep -q "id=\"root\"" /tmp/control_center_dashboard_smoke.html; then
  echo "[smoke-dashboard] root mount point not found" >&2
  exit 1
fi

echo "[smoke-dashboard] OK"
