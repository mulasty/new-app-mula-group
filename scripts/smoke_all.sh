#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

sh "${SCRIPT_DIR}/smoke_api.sh"
sh "${SCRIPT_DIR}/smoke_dashboard.sh"

echo "[smoke-all] OK"
