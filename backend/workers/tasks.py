import logging
from datetime import UTC, datetime
from uuid import UUID

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select

from app.application.services.publishing_service import (
    emit_publish_event,
    generate_unique_company_slug,
    get_active_website_channel,
    get_existing_website_publication,
    publish_post_async,
)
from app.domain.models.post import Post, PostStatus
from app.domain.models.website_publication import WebsitePublication
from app.infrastructure.db.session import SessionLocal
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

RETRY_COUNTDOWNS = [30, 120, 300, 900, 1800]
MAX_RETRIES = len(RETRY_COUNTDOWNS)


@celery_app.task(name="workers.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="workers.tasks.schedule_due_posts")
def schedule_due_posts() -> dict:
    now = datetime.now(UTC)
    enqueued = 0

    with SessionLocal() as db:
        due_posts = db.execute(
            select(Post).where(
                Post.status == PostStatus.SCHEDULED.value,
                Post.publish_at.is_not(None),
                Post.publish_at <= now,
            )
        ).scalars().all()

        for post in due_posts:
            post.status = PostStatus.PUBLISHING.value
            post.last_error = None
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                event_type="PostPublishingStarted",
                status="ok",
                metadata_json={"source": "scheduler"},
            )
            publish_post_async(post.company_id, post.id)
            enqueued += 1

        db.commit()

    logger.info("scheduler_run completed enqueued=%s due_checked_at=%s", enqueued, now.isoformat())
    return {"enqueued": enqueued}


@celery_app.task(bind=True, name="workers.tasks.publish_post", max_retries=MAX_RETRIES, acks_late=True)
def publish_post(self, company_id: str, post_id: str) -> dict:
    company_uuid = UUID(company_id)
    post_uuid = UUID(post_id)
    attempt = self.request.retries + 1

    with SessionLocal() as db:
        post = db.execute(
            select(Post).where(Post.id == post_uuid, Post.company_id == company_uuid)
        ).scalar_one_or_none()
        if post is None:
            logger.warning("publish_post_not_found company_id=%s post_id=%s", company_id, post_id)
            return {"status": "missing"}

        if post.status not in {PostStatus.PUBLISHING.value, PostStatus.SCHEDULED.value}:
            logger.info(
                "publish_post_skip_invalid_state company_id=%s post_id=%s status=%s",
                company_id,
                post_id,
                post.status,
            )
            return {"status": "skipped", "post_status": post.status}

        existing_publication = get_existing_website_publication(db, company_id=company_uuid, post_id=post_uuid)
        if existing_publication is not None:
            post.status = PostStatus.PUBLISHED.value
            post.last_error = None
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                channel_id=None,
                event_type="PostPublished",
                status="ok",
                attempt=attempt,
                metadata_json={"idempotent": True, "publication_id": str(existing_publication.id)},
            )
            db.commit()
            logger.info(
                "publish_post_idempotent_success company_id=%s post_id=%s publication_id=%s",
                company_id,
                post_id,
                existing_publication.id,
            )
            return {"status": "published", "idempotent": True}

        try:
            channel = get_active_website_channel(db, company_id=company_uuid, project_id=post.project_id)
            if channel is None:
                raise ValueError("Active website channel not found for project")

            slug = generate_unique_company_slug(db, company_id=company_uuid, title=post.title, post_id=post.id)
            publication = WebsitePublication(
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                slug=slug,
                title=post.title,
                content=post.content,
                published_at=datetime.now(UTC),
            )
            db.add(publication)
            db.flush()

            post.status = PostStatus.PUBLISHED.value
            post.last_error = None
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                channel_id=channel.id,
                event_type="ChannelPublishSucceeded",
                status="ok",
                attempt=attempt,
                metadata_json={"channel_type": channel.type, "publication_id": str(publication.id)},
            )
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                channel_id=channel.id,
                event_type="PostPublished",
                status="ok",
                attempt=attempt,
                metadata_json={"publication_id": str(publication.id)},
            )
            db.commit()
            logger.info(
                "publish_post_success company_id=%s post_id=%s project_id=%s channel_id=%s",
                company_id,
                post_id,
                post.project_id,
                channel.id,
            )
            return {"status": "published", "publication_id": str(publication.id)}
        except Exception as exc:
            db.rollback()
            failed_post = db.execute(
                select(Post).where(Post.id == post_uuid, Post.company_id == company_uuid)
            ).scalar_one_or_none()
            if failed_post is not None:
                failed_post.status = PostStatus.FAILED.value
                failed_post.last_error = str(exc)
                emit_publish_event(
                    db,
                    company_id=failed_post.company_id,
                    project_id=failed_post.project_id,
                    post_id=failed_post.id,
                    event_type="ChannelPublishFailed",
                    status="error",
                    attempt=attempt,
                    metadata_json={"error": str(exc)},
                )
                emit_publish_event(
                    db,
                    company_id=failed_post.company_id,
                    project_id=failed_post.project_id,
                    post_id=failed_post.id,
                    event_type="PostPublishFailed",
                    status="error",
                    attempt=attempt,
                    metadata_json={"error": str(exc)},
                )
                db.commit()

            if self.request.retries >= MAX_RETRIES:
                logger.exception(
                    "publish_post_max_retries company_id=%s post_id=%s error=%s",
                    company_id,
                    post_id,
                    exc,
                )
                return {"status": "failed", "error": str(exc)}

            countdown = RETRY_COUNTDOWNS[self.request.retries]
            with SessionLocal() as db_retry:
                retry_post = db_retry.execute(
                    select(Post).where(Post.id == post_uuid, Post.company_id == company_uuid)
                ).scalar_one_or_none()
                if retry_post is not None:
                    retry_post.status = PostStatus.PUBLISHING.value
                    db_retry.add(retry_post)
                    db_retry.commit()

            logger.warning(
                "publish_post_retry company_id=%s post_id=%s attempt=%s next_countdown=%s error=%s",
                company_id,
                post_id,
                attempt,
                countdown,
                exc,
            )
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                return {"status": "failed", "error": str(exc)}
