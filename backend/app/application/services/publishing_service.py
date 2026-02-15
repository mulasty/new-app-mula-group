import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.channel import Channel, ChannelStatus, ChannelType
from app.domain.models.post import Post
from app.domain.models.publish_event import PublishEvent
from app.domain.models.website_publication import WebsitePublication

logger = logging.getLogger(__name__)

SLUG_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+")


def emit_publish_event(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    post_id: UUID,
    event_type: str,
    status: str,
    attempt: int = 1,
    channel_id: UUID | None = None,
    metadata_json: dict | None = None,
) -> PublishEvent:
    event = PublishEvent(
        company_id=company_id,
        project_id=project_id,
        post_id=post_id,
        channel_id=channel_id,
        event_type=event_type,
        status=status,
        attempt=attempt,
        metadata_json=metadata_json or {},
    )
    db.add(event)
    return event


def build_slug_base(title: str) -> str:
    normalized = SLUG_SANITIZE_PATTERN.sub("-", title.lower()).strip("-")
    return normalized or "post"


def generate_unique_company_slug(db: Session, *, company_id: UUID, title: str, post_id: UUID) -> str:
    base = build_slug_base(title)
    suffix = str(post_id).split("-")[0]
    candidate = f"{base}-{suffix}"

    exists = db.execute(
        select(WebsitePublication.id).where(
            WebsitePublication.company_id == company_id,
            WebsitePublication.slug == candidate,
        )
    ).scalar_one_or_none()
    if exists is None:
        return candidate

    timestamp_suffix = int(datetime.now(UTC).timestamp())
    return f"{candidate}-{timestamp_suffix}"


def get_active_website_channel(db: Session, *, company_id: UUID, project_id: UUID) -> Channel | None:
    return db.execute(
        select(Channel).where(
            Channel.company_id == company_id,
            Channel.project_id == project_id,
            Channel.type == ChannelType.WEBSITE.value,
            Channel.status == ChannelStatus.ACTIVE.value,
        )
    ).scalar_one_or_none()


def get_existing_website_publication(db: Session, *, company_id: UUID, post_id: UUID) -> WebsitePublication | None:
    return db.execute(
        select(WebsitePublication).where(
            WebsitePublication.company_id == company_id,
            WebsitePublication.post_id == post_id,
        )
    ).scalar_one_or_none()


def publish_post_async(company_id: UUID, post_id: UUID, countdown: int | None = None) -> None:
    from workers.tasks import publish_post  # local import to avoid import cycle

    publish_post.apply_async(
        kwargs={
            "company_id": str(company_id),
            "post_id": str(post_id),
        },
        countdown=countdown,
    )
    logger.info(
        "publish_post_enqueued company_id=%s post_id=%s countdown=%s",
        company_id,
        post_id,
        countdown if countdown is not None else 0,
    )
