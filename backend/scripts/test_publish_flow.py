import json
import sys
import time
import uuid
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_BASE_URL = "http://localhost:8000"


def api_request(method: str, path: str, *, tenant_id: str | None = None, token: str | None = None, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(f"{API_BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except HTTPError as exc:
        message = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {message}") from exc


def main() -> int:
    global API_BASE_URL
    if len(sys.argv) > 1:
        API_BASE_URL = sys.argv[1].rstrip("/")

    suffix = str(uuid.uuid4())[:8]
    signup_email = f"owner-{suffix}@test.local"
    signup_password = "secret123"

    signup_payload = {
        "company_name": f"Control Center {suffix}",
        "company_slug": f"control-center-{suffix}",
        "owner_email": signup_email,
        "owner_password": signup_password,
    }
    signup = api_request("POST", "/signup", payload=signup_payload)
    tenant_id = signup["company"]["id"]
    print(f"[1] Signed up tenant: {tenant_id}")

    login = api_request(
        "POST",
        "/auth/login",
        tenant_id=tenant_id,
        payload={"email": signup_email, "password": signup_password},
    )
    access_token = login["access_token"]
    print("[2] Logged in owner")

    project = api_request(
        "POST",
        "/projects",
        tenant_id=tenant_id,
        token=access_token,
        payload={"name": "Publishing Demo"},
    )
    project_id = project["id"]
    print(f"[3] Created project: {project_id}")

    channel = api_request(
        "POST",
        "/channels",
        tenant_id=tenant_id,
        token=access_token,
        payload={"project_id": project_id, "type": "website"},
    )
    print(f"[4] Created website channel: {channel['id']}")

    post = api_request(
        "POST",
        "/posts",
        tenant_id=tenant_id,
        token=access_token,
        payload={"project_id": project_id, "title": "Hello Website", "content": "First publication"},
    )
    post_id = post["id"]
    print(f"[5] Created post draft: {post_id}")

    now_iso = datetime.now(UTC).isoformat()
    scheduled = api_request(
        "POST",
        f"/posts/{post_id}/schedule",
        tenant_id=tenant_id,
        token=access_token,
        payload={"publish_at": now_iso},
    )
    print(f"[6] Scheduled post at: {scheduled['publish_at']}")

    deadline = time.time() + 90
    published = None
    while time.time() < deadline:
        posts = api_request(
            "GET",
            f"/posts?project_id={project_id}",
            tenant_id=tenant_id,
            token=access_token,
        )
        items = posts.get("items", [])
        found = next((item for item in items if item["id"] == post_id), None)
        if found and found["status"] == "published":
            published = found
            break
        time.sleep(3)

    if not published:
        raise RuntimeError("Post did not reach published status within timeout")

    timeline = api_request("GET", f"/posts/{post_id}/timeline", tenant_id=tenant_id, token=access_token)
    publications = api_request(
        "GET",
        f"/website/publications?project_id={project_id}",
        tenant_id=tenant_id,
        token=access_token,
    )
    print(f"[7] Post published successfully: {published['id']}")
    print(f"[8] Timeline events: {len(timeline.get('items', []))}")
    print(f"[9] Website publications: {len(publications.get('items', []))}")
    print("Flow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
