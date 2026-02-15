from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.domain.models.user import User
from app.integrations.channel_adapters import get_adapter_capabilities, list_registered_adapter_types
from app.interfaces.api.deps import get_current_user, require_tenant_id

router = APIRouter(prefix="/connectors", tags=["connectors"])


DISPLAY_NAMES = {
    "website": "Website",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "threads": "Threads",
    "x": "X / Twitter",
    "pinterest": "Pinterest",
    "youtube": "YouTube",
}

OAUTH_PATHS = {
    "linkedin": "/channels/linkedin/oauth/start",
    "facebook": "/channels/meta/oauth/start",
    "instagram": "/channels/meta/oauth/start",
    "tiktok": "/channels/tiktok/oauth/start",
    "threads": "/channels/threads/oauth/start",
    "x": "/channels/x/oauth/start",
    "pinterest": "/channels/pinterest/oauth/start",
}

KNOWN_PLATFORMS = [
    "linkedin",
    "facebook",
    "instagram",
    "tiktok",
    "threads",
    "x",
    "pinterest",
    "youtube",
    "website",
]


@router.get("/available", status_code=status.HTTP_200_OK)
def list_available_connectors(
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    discovered = set(list_registered_adapter_types())
    platforms = [*KNOWN_PLATFORMS]
    for discovered_platform in sorted(discovered):
        if discovered_platform not in platforms:
            platforms.append(discovered_platform)
    items = []
    for platform in platforms:
        available = platform in discovered
        capabilities = get_adapter_capabilities(platform) if available else {}
        items.append(
            {
                "platform": platform,
                "display_name": DISPLAY_NAMES.get(platform, platform.title()),
                "capabilities": capabilities,
                "oauth_start_path": OAUTH_PATHS.get(platform),
                "available": available,
            }
        )
    return {"items": items}
