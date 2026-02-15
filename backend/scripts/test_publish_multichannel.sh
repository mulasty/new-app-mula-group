#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
TENANT_ID="${TENANT_ID:-}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"
PROJECT_ID="${PROJECT_ID:-}"
EMAIL="${EMAIL:-}"
PASSWORD="${PASSWORD:-secret12345!}"

auth_header=""
tenant_header=""

bootstrap_if_needed() {
  if [[ -n "${TENANT_ID}" && -n "${ACCESS_TOKEN}" ]]; then
    auth_header="Authorization: Bearer ${ACCESS_TOKEN}"
    tenant_header="X-Tenant-ID: ${TENANT_ID}"
    return
  fi

  suffix="$(python - <<'PY'
import uuid
print(str(uuid.uuid4())[:8])
PY
)"
  EMAIL="owner-${suffix}@multichannel.local"
  local company_name="Multichannel ${suffix}"
  local company_slug="multichannel-${suffix}"

  echo "[bootstrap] signing up test tenant..."
  local signup_payload
  signup_payload="$(cat <<JSON
{"company_name":"${company_name}","company_slug":"${company_slug}","owner_email":"${EMAIL}","owner_password":"${PASSWORD}"}
JSON
)"
  local signup_resp
  signup_resp="$(curl -sS -X POST "${API_BASE_URL}/signup" -H "Content-Type: application/json" -d "${signup_payload}")"
  TENANT_ID="$(printf '%s' "${signup_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["company"]["id"])
PY
)"

  echo "[bootstrap] logging in..."
  local login_resp
  login_resp="$(curl -sS -X POST "${API_BASE_URL}/auth/login" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: ${TENANT_ID}" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
  ACCESS_TOKEN="$(printf '%s' "${login_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["access_token"])
PY
)"

  auth_header="Authorization: Bearer ${ACCESS_TOKEN}"
  tenant_header="X-Tenant-ID: ${TENANT_ID}"
}

ensure_project() {
  if [[ -n "${PROJECT_ID}" ]]; then
    return
  fi
  echo "[setup] creating project..."
  local project_resp
  project_resp="$(curl -sS -X POST "${API_BASE_URL}/projects" \
    -H "Content-Type: application/json" \
    -H "${auth_header}" \
    -H "${tenant_header}" \
    -d '{"name":"Multichannel Publish Project"}')"
  PROJECT_ID="$(printf '%s' "${project_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["id"])
PY
)"
}

ensure_website_channel() {
  echo "[setup] ensuring website channel..."
  curl -sS -X POST "${API_BASE_URL}/channels" \
    -H "Content-Type: application/json" \
    -H "${auth_header}" \
    -H "${tenant_header}" \
    -d "{\"project_id\":\"${PROJECT_ID}\",\"type\":\"website\",\"name\":\"Website\"}" >/dev/null
}

bootstrap_if_needed
ensure_project
ensure_website_channel

echo "Tenant: ${TENANT_ID}"
echo "Project: ${PROJECT_ID}"

echo "[run] fetching active channels..."
channels_resp="$(curl -sS "${API_BASE_URL}/channels?project_id=${PROJECT_ID}" \
  -H "${auth_header}" \
  -H "${tenant_header}")"
python - <<'PY' "${channels_resp}"
import json,sys
items=json.loads(sys.argv[1]).get("items",[])
active=[x for x in items if (x.get("status") or "active")=="active"]
print(f"Total channels: {len(items)} | Active channels: {len(active)}")
for item in active:
    print(f" - {item.get('type')} :: {item.get('name')}")
PY

echo "[run] creating post..."
post_resp="$(curl -sS -X POST "${API_BASE_URL}/posts" \
  -H "Content-Type: application/json" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -d "{\"project_id\":\"${PROJECT_ID}\",\"title\":\"Multichannel smoke\",\"content\":\"Publishing test body https://example.com/demo.mp4\",\"status\":\"draft\"}")"
post_id="$(printf '%s' "${post_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["id"])
PY
)"

echo "[run] publish now..."
curl -sS -X POST "${API_BASE_URL}/posts/${post_id}/publish-now" \
  -H "Content-Type: application/json" \
  -H "${auth_header}" \
  -H "${tenant_header}" >/dev/null

echo "[run] waiting for terminal status..."
terminal_status=""
for i in $(seq 1 40); do
  posts_resp="$(curl -sS "${API_BASE_URL}/posts?project_id=${PROJECT_ID}" \
    -H "${auth_header}" \
    -H "${tenant_header}")"
  status_value="$(python - <<'PY' "${posts_resp}" "${post_id}"
import json,sys
payload=json.loads(sys.argv[1])
post_id=sys.argv[2]
for item in payload.get("items",[]):
    if item.get("id")==post_id:
        print(item.get("status",""))
        break
PY
)"
  if [[ -n "${status_value}" ]]; then
    echo "Attempt ${i}: ${status_value}"
    if [[ "${status_value}" == "published" || "${status_value}" == "published_partial" || "${status_value}" == "failed" ]]; then
      terminal_status="${status_value}"
      break
    fi
  fi
  sleep 3
done

if [[ -z "${terminal_status}" ]]; then
  echo "Publish did not reach terminal status in time"
  exit 1
fi

echo "[run] loading timeline..."
timeline_resp="$(curl -sS "${API_BASE_URL}/posts/${post_id}/timeline" \
  -H "${auth_header}" \
  -H "${tenant_header}")"
python - <<'PY' "${timeline_resp}"
import json,sys
items=json.loads(sys.argv[1]).get("items",[])
success=[x for x in items if x.get("event_type")=="ChannelPublishSucceeded"]
failed=[x for x in items if x.get("event_type")=="ChannelPublishFailed"]
auth_failed=[x for x in items if x.get("event_type")=="ChannelAuthFailed"]
print(f"Timeline total: {len(items)}")
print(f"ChannelPublishSucceeded: {len(success)}")
print(f"ChannelPublishFailed: {len(failed)}")
print(f"ChannelAuthFailed: {len(auth_failed)}")
if items:
    print(f"Latest event: {items[0].get('event_type')} status={items[0].get('status')}")
PY

echo "Multichannel publish smoke completed: ${terminal_status}"
