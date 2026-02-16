#!/usr/bin/env sh
set -eu

LOCK_FILE="${ALEMBIC_LOCK_FILE:-/tmp/control-center-alembic.lock}"
LOCK_TIMEOUT_SECONDS="${ALEMBIC_LOCK_TIMEOUT_SECONDS:-120}"

if ! command -v flock >/dev/null 2>&1; then
  echo "flock is required for migration lockfile strategy" >&2
  exit 1
fi

echo "Acquiring Alembic migration lock: ${LOCK_FILE}"
flock -w "${LOCK_TIMEOUT_SECONDS}" "${LOCK_FILE}" alembic upgrade head
echo "Alembic migration lock released"
