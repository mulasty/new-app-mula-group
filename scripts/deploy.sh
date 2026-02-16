#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-}"
if [[ -z "$ENVIRONMENT" ]]; then
  echo "usage: scripts/deploy.sh <staging|production>"
  exit 1
fi

if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
  echo "invalid environment: $ENVIRONMENT"
  exit 1
fi

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.staging"
if [[ "$ENVIRONMENT" == "production" ]]; then
  COMPOSE_FILE="docker-compose.prod.yml"
  ENV_FILE=".env.production"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE"
  exit 1
fi

echo "[deploy] environment=$ENVIRONMENT compose=$COMPOSE_FILE"

# Preflight checks before deployment.
bash scripts/preflight_check.sh

# Pull latest images if configured and then build fallback.
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull || true
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up --build -d

# Post-deploy smoke checks.
bash scripts/smoke_all.sh

echo "[deploy] deployment completed"
