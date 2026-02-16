#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-owner+aiq+$(date +%s)@controlcenter.local}"
PASSWORD="${PASSWORD:-devpassword123}"
COMPANY="${COMPANY:-AI Quality Tenant}"

json_get() {
  python3 -c "import json,sys,functools,operator; value=functools.reduce(operator.getitem, sys.argv[1].split('.'), json.load(sys.stdin)); print(value)" "$1"
}

echo "[ai-quality] signup"
SIGNUP=$(curl -sS -X POST "$API_BASE_URL/signup" -H "Content-Type: application/json" -d "{\"company_name\":\"$COMPANY\",\"owner_email\":\"$EMAIL\",\"owner_password\":\"$PASSWORD\"}" || true)
TENANT_ID=$(echo "$SIGNUP" | json_get "company.id" 2>/dev/null || true)
if [[ -z "${TENANT_ID:-}" ]]; then
  echo "[ai-quality] signup may already exist, trying login with tenant from env"
  TENANT_ID="${TENANT_ID_OVERRIDE:-}"
fi
if [[ -z "${TENANT_ID:-}" ]]; then
  echo "TENANT_ID missing. Set TENANT_ID_OVERRIDE if account already exists."
  exit 1
fi

echo "[ai-quality] login"
LOGIN=$(curl -sS -X POST "$API_BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
ACCESS_TOKEN=$(echo "$LOGIN" | json_get "access_token")
AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"
TENANT_HEADER="X-Tenant-ID: $TENANT_ID"

echo "[ai-quality] enable flags"
FLAGS=$(curl -sS -H "$AUTH_HEADER" -H "$TENANT_HEADER" "$API_BASE_URL/feature-flags")
for KEY in v1_ai_quality_engine v1_ai_quality_gate; do
  FLAG_ID=$(echo "$FLAGS" | python3 -c "import json,sys; key=sys.argv[1]; payload=json.load(sys.stdin); print(next((i.get('id') for i in payload.get('items',[]) if i.get('key')==key), ''))" "$KEY")
  curl -sS -X PATCH "$API_BASE_URL/feature-flags/$FLAG_ID" -H "$AUTH_HEADER" -H "$TENANT_HEADER" -H "Content-Type: application/json" -d '{"enabled_for_tenant":true}' >/dev/null
  echo "  - enabled $KEY"
done

echo "[ai-quality] create project"
PROJECT=$(curl -sS -X POST "$API_BASE_URL/projects" -H "$AUTH_HEADER" -H "$TENANT_HEADER" -H "Content-Type: application/json" -d '{"name":"AIQ Demo"}')
PROJECT_ID=$(echo "$PROJECT" | json_get "id")

echo "[ai-quality] create brand profile"
curl -sS -X POST "$API_BASE_URL/brand-profiles" -H "$AUTH_HEADER" -H "$TENANT_HEADER" -H "Content-Type: application/json" -d "{\"project_id\":\"$PROJECT_ID\",\"brand_name\":\"Control Center\",\"language\":\"pl\",\"tone\":\"professional\",\"do_list\":[],\"dont_list\":[\"guaranteed\"],\"forbidden_claims\":[\"guaranteed ROI\"],\"preferred_hashtags\":[]}" >/dev/null

echo "[ai-quality] create risky post"
POST_JSON=$(curl -sS -X POST "$API_BASE_URL/posts" -H "$AUTH_HEADER" -H "$TENANT_HEADER" -H "Content-Type: application/json" -d "{\"project_id\":\"$PROJECT_ID\",\"title\":\"GUARANTEED ROI!!!\",\"content\":\"Contact us now at sales@example.com for guaranteed ROI!!!!\"}")
POST_ID=$(echo "$POST_JSON" | json_get "id")

echo "[ai-quality] run quality check"
REPORT=$(curl -sS -X POST "$API_BASE_URL/posts/$POST_ID/quality-check" -H "$AUTH_HEADER" -H "$TENANT_HEADER" -H "Content-Type: application/json" -d '{}')
echo "$REPORT"

echo "[ai-quality] publish-now should be blocked"
set +e
BLOCKED=$(curl -sS -o /tmp/ai_quality_publish_blocked.json -w "%{http_code}" -X POST "$API_BASE_URL/posts/$POST_ID/publish-now" -H "$AUTH_HEADER" -H "$TENANT_HEADER")
set -e
if [[ "$BLOCKED" != "409" ]]; then
  echo "Expected 409, got $BLOCKED"
  cat /tmp/ai_quality_publish_blocked.json
  exit 1
fi

echo "[ai-quality] approve and publish-now"
curl -sS -X POST "$API_BASE_URL/posts/$POST_ID/approve" -H "$AUTH_HEADER" -H "$TENANT_HEADER" >/dev/null
curl -sS -X POST "$API_BASE_URL/posts/$POST_ID/publish-now" -H "$AUTH_HEADER" -H "$TENANT_HEADER" >/dev/null

echo "[ai-quality] OK"
