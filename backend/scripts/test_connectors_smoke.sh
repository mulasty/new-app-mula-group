#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
PLATFORM="${PLATFORM:-x}" # one of: tiktok,threads,x,pinterest
PASSWORD="${PASSWORD:-secret12345!}"

if [[ ! "$PLATFORM" =~ ^(tiktok|threads|x|pinterest)$ ]]; then
  echo "Unsupported PLATFORM='$PLATFORM'. Use: tiktok|threads|x|pinterest"
  exit 1
fi

suffix="$(python - <<'PY'
import uuid
print(str(uuid.uuid4())[:8])
PY
)"

email="owner-${suffix}@connectors.local"
company_name="Connector Smoke ${suffix}"
company_slug="connector-smoke-${suffix}"

echo "[1/8] Signing up tenant..."
signup_payload="$(cat <<JSON
{"company_name":"${company_name}","company_slug":"${company_slug}","owner_email":"${email}","owner_password":"${PASSWORD}"}
JSON
)"
signup_resp="$(curl -sS -X POST "${API_BASE_URL}/signup" -H "Content-Type: application/json" -d "${signup_payload}")"
tenant_id="$(printf '%s' "${signup_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["company"]["id"])
PY
)"
echo "Tenant: ${tenant_id}"

echo "[2/8] Logging in..."
login_resp="$(curl -sS -X POST "${API_BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: ${tenant_id}" \
  -d "{\"email\":\"${email}\",\"password\":\"${PASSWORD}\"}")"
access_token="$(printf '%s' "${login_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["access_token"])
PY
)"

auth_header="Authorization: Bearer ${access_token}"
tenant_header="X-Tenant-ID: ${tenant_id}"

echo "[3/8] Creating project..."
project_resp="$(curl -sS -X POST "${API_BASE_URL}/projects" \
  -H "Content-Type: application/json" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -d "{\"name\":\"Connector Smoke Project\"}")"
project_id="$(printf '%s' "${project_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["id"])
PY
)"
echo "Project: ${project_id}"

echo "[4/8] Starting ${PLATFORM} OAuth..."
oauth_resp="$(curl -sS "${API_BASE_URL}/channels/${PLATFORM}/oauth/start?project_id=${project_id}&redirect=false" \
  -H "${auth_header}" \
  -H "${tenant_header}")"
oauth_url="$(printf '%s' "${oauth_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["authorization_url"])
PY
)"
echo "Open this URL in browser and finish OAuth:"
echo "${oauth_url}"
echo
read -r -p "After completing OAuth in browser, press Enter to continue..."

echo "[5/8] Verifying connected channel..."
channels_resp="$(curl -sS "${API_BASE_URL}/channels?project_id=${project_id}" \
  -H "${auth_header}" \
  -H "${tenant_header}")"
python - <<'PY' "${channels_resp}" "${PLATFORM}"
import json,sys
payload=json.loads(sys.argv[1])
platform=sys.argv[2]
items=payload.get("items",[])
if not any(item.get("type")==platform for item in items):
    raise SystemExit(f"No connected channel of type '{platform}' found")
print(f"Connected channels: {len(items)}")
PY

echo "[6/8] Creating draft post..."
post_resp="$(curl -sS -X POST "${API_BASE_URL}/posts" \
  -H "Content-Type: application/json" \
  -H "${auth_header}" \
  -H "${tenant_header}" \
  -d "{\"project_id\":\"${project_id}\",\"title\":\"Connector smoke ${PLATFORM}\",\"content\":\"Smoke test content https://example.com/demo.mp4\",\"status\":\"draft\"}")"
post_id="$(printf '%s' "${post_resp}" | python - <<'PY'
import json,sys
print(json.load(sys.stdin)["id"])
PY
)"
echo "Post: ${post_id}"

echo "[7/8] Triggering publish-now..."
curl -sS -X POST "${API_BASE_URL}/posts/${post_id}/publish-now" \
  -H "Content-Type: application/json" \
  -H "${auth_header}" \
  -H "${tenant_header}" >/dev/null

echo "[8/8] Polling status + timeline..."
published_status=""
for i in $(seq 1 30); do
  posts_resp="$(curl -sS "${API_BASE_URL}/posts?project_id=${project_id}" \
    -H "${auth_header}" \
    -H "${tenant_header}")"
  current_status="$(python - <<'PY' "${posts_resp}" "${post_id}"
import json,sys
payload=json.loads(sys.argv[1])
post_id=sys.argv[2]
for item in payload.get("items",[]):
    if item.get("id")==post_id:
        print(item.get("status",""))
        break
PY
)"
  if [[ -n "${current_status}" ]]; then
    echo "Attempt ${i}: status=${current_status}"
    if [[ "${current_status}" == "published" || "${current_status}" == "published_partial" || "${current_status}" == "failed" ]]; then
      published_status="${current_status}"
      break
    fi
  fi
  sleep 5
done

timeline_resp="$(curl -sS "${API_BASE_URL}/posts/${post_id}/timeline" \
  -H "${auth_header}" \
  -H "${tenant_header}")"
python - <<'PY' "${timeline_resp}"
import json,sys
items=json.loads(sys.argv[1]).get("items",[])
print(f"Timeline events: {len(items)}")
if items:
    last=items[0]
    print(f"Latest event: {last.get('event_type')} status={last.get('status')}")
PY

if [[ -z "${published_status}" ]]; then
  echo "Publish result did not reach terminal state within timeout"
  exit 1
fi

echo "Smoke completed. Final status: ${published_status}"
