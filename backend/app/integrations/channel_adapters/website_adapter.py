from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.publishing_service import generate_unique_company_slug
from app.domain.models.channel import Channel
from app.domain.models.post import Post
from app.domain.models.website_publication import WebsitePublication
from app.integrations.channel_adapters.base_adapter import BaseChannelAdapter


class WebsiteAdapter(BaseChannelAdapter):
    channel_type = "website"

    def __init__(self, db: Session) -> None:
        self.db = db

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": True,
            "video": True,
            "reels": False,
            "shorts": False,
            "max_length": 50000,
        }

    async def validate_credentials(self) -> None:
        return None

    async def refresh_credentials(self) -> None:
        return None

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        return self._publish(post=post, channel=channel, media_metadata=None)

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        # Foundation phase: website adapter keeps media path compatible by reusing text publish.
        return await self.publish_text(post=post, channel=channel)

    def _publish(self, *, post: Post, channel: Channel, media_metadata: dict | None) -> dict:
        existing = self.db.execute(
            select(WebsitePublication).where(
                WebsitePublication.company_id == post.company_id,
                WebsitePublication.post_id == post.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "external_post_id": str(existing.id),
                "idempotent": True,
                "channel_type": self.channel_type,
                "platform": self.channel_type,
            }

        slug = generate_unique_company_slug(self.db, company_id=post.company_id, title=post.title, post_id=post.id)
        publication = WebsitePublication(
            company_id=post.company_id,
            project_id=post.project_id,
            post_id=post.id,
            slug=slug,
            title=post.title,
            content=post.content,
            published_at=datetime.now(UTC),
        )
        self.db.add(publication)
        self.db.flush()
        return {
            "external_post_id": str(publication.id),
            "slug": slug,
            "idempotent": False,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "media": media_metadata,
        }
