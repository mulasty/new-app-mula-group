import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from croniter import croniter
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.publishing_service import emit_publish_event, publish_post_async
from app.application.services.ai_quality_service import (
    apply_quality_to_content_metadata,
    choose_content_status,
    evaluate_text,
    get_or_create_policy,
)
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.ai_provider import (
    AIContentRequest,
    AIProviderError,
    DEFAULT_POST_TEXT_OUTPUT_SCHEMA,
    get_ai_provider,
)
from app.domain.models.automation_event import AutomationEvent
from app.domain.models.automation_rule import (
    AutomationActionType,
    AutomationRule,
    AutomationTriggerType,
)
from app.domain.models.automation_run import AutomationRun, AutomationRunStatus
from app.domain.models.campaign import Campaign
from app.domain.models.content_item import ContentItem, ContentItemSource, ContentItemStatus
from app.domain.models.content_template import ContentTemplate, ContentTemplateType
from app.domain.models.post import Post, PostStatus
from app.domain.models.publish_event import PublishEvent

logger = logging.getLogger(__name__)

EVENT_CURSOR_KEY = "automation:event_rules:last_publish_event_at"


@dataclass(frozen=True)
class AutomationDispatchResult:
    runs_created: int
    rules_checked: int


def emit_automation_event(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    run_id: UUID,
    event_type: str,
    status: str,
    metadata_json: dict[str, Any] | None = None,
) -> AutomationEvent:
    event = AutomationEvent(
        company_id=company_id,
        project_id=project_id,
        run_id=run_id,
        event_type=event_type,
        status=status,
        metadata_json=metadata_json or {},
    )
    db.add(event)
    return event


def _build_rule_fingerprint(rule: AutomationRule, now: datetime) -> str:
    # Minute-level fingerprint prevents duplicate queueing bursts from beat overlap.
    minute_bucket = now.replace(second=0, microsecond=0).isoformat()
    return f"{rule.id}:{rule.trigger_type}:{minute_bucket}"


def _has_recent_run(db: Session, *, company_id: UUID, project_id: UUID, rule_id: UUID, window_minutes: int = 5) -> bool:
    window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)
    existing = db.execute(
        select(AutomationRun.id).where(
            AutomationRun.company_id == company_id,
            AutomationRun.project_id == project_id,
            AutomationRun.rule_id == rule_id,
            AutomationRun.created_at >= window_start,
            AutomationRun.status.in_(
                [
                    AutomationRunStatus.QUEUED.value,
                    AutomationRunStatus.RUNNING.value,
                    AutomationRunStatus.SUCCESS.value,
                    AutomationRunStatus.PARTIAL.value,
                ]
            ),
        )
    ).scalar_one_or_none()
    return existing is not None


def create_automation_run(
    db: Session,
    *,
    rule: AutomationRule,
    trigger_reason: str,
    trigger_metadata: dict[str, Any] | None = None,
) -> AutomationRun:
    now = datetime.now(UTC)
    fingerprint = _build_rule_fingerprint(rule, now)
    if _has_recent_run(db, company_id=rule.company_id, project_id=rule.project_id, rule_id=rule.id):
        raise ValueError("recent_run_exists")

    run = AutomationRun(
        company_id=rule.company_id,
        project_id=rule.project_id,
        rule_id=rule.id,
        status=AutomationRunStatus.QUEUED.value,
        stats_json={
            "trigger_reason": trigger_reason,
            "triggered_at": now.isoformat(),
            "rule_fingerprint": fingerprint,
            **(trigger_metadata or {}),
        },
    )
    db.add(run)
    db.flush()
    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="AutomationRunQueued",
        status="ok",
        metadata_json={
            "rule_id": str(rule.id),
            "trigger_reason": trigger_reason,
            **(trigger_metadata or {}),
        },
    )
    return run


def enqueue_automation_run(run_id: UUID) -> None:
    from workers.tasks import execute_automation_run  # local import to avoid circular imports

    execute_automation_run.apply_async(kwargs={"run_id": str(run_id)})


def _is_rule_due_by_interval(db: Session, rule: AutomationRule, now: datetime) -> bool:
    interval_seconds = int((rule.trigger_config_json or {}).get("interval_seconds") or 0)
    if interval_seconds <= 0:
        return False
    last_run_time = db.execute(
        select(func.max(AutomationRun.created_at)).where(
            AutomationRun.company_id == rule.company_id,
            AutomationRun.project_id == rule.project_id,
            AutomationRun.rule_id == rule.id,
        )
    ).scalar_one_or_none()
    if last_run_time is None:
        return True
    return now >= last_run_time + timedelta(seconds=interval_seconds)


def _is_rule_due_by_cron(db: Session, rule: AutomationRule, now: datetime) -> bool:
    cron_expr = str((rule.trigger_config_json or {}).get("cron") or "").strip()
    if not cron_expr:
        return False
    try:
        last_scheduled_at = croniter(cron_expr, now).get_prev(datetime)
    except Exception:
        logger.warning("automation_rule_invalid_cron rule_id=%s cron=%s", rule.id, cron_expr)
        return False
    last_run_time = db.execute(
        select(func.max(AutomationRun.created_at)).where(
            AutomationRun.company_id == rule.company_id,
            AutomationRun.project_id == rule.project_id,
            AutomationRun.rule_id == rule.id,
        )
    ).scalar_one_or_none()
    if last_run_time is None:
        return True
    return last_run_time < last_scheduled_at


def dispatch_due_time_rules(db: Session, now: datetime | None = None) -> AutomationDispatchResult:
    checked_now = now or datetime.now(UTC)
    rules = db.execute(
        select(AutomationRule).where(
            AutomationRule.is_enabled.is_(True),
            AutomationRule.trigger_type.in_(
                [AutomationTriggerType.CRON.value, AutomationTriggerType.INTERVAL.value]
            ),
        )
    ).scalars().all()

    created_runs = 0
    for rule in rules:
        due = False
        if rule.trigger_type == AutomationTriggerType.CRON.value:
            due = _is_rule_due_by_cron(db, rule, checked_now)
        elif rule.trigger_type == AutomationTriggerType.INTERVAL.value:
            due = _is_rule_due_by_interval(db, rule, checked_now)

        if not due:
            continue

        try:
            run = create_automation_run(
                db,
                rule=rule,
                trigger_reason="time_trigger",
                trigger_metadata={"trigger_type": rule.trigger_type},
            )
            enqueue_automation_run(run.id)
            created_runs += 1
        except ValueError:
            continue

    return AutomationDispatchResult(runs_created=created_runs, rules_checked=len(rules))


def _event_rule_matches_publish_event(rule: AutomationRule, event: PublishEvent) -> bool:
    config = rule.trigger_config_json or {}
    allowed_event_types = config.get("event_types") or []
    allowed_statuses = config.get("statuses") or []
    if allowed_event_types and event.event_type not in allowed_event_types:
        return False
    if allowed_statuses and event.status not in allowed_statuses:
        return False
    return True


def _read_event_cursor(redis_client: Redis) -> datetime:
    raw = redis_client.get(EVENT_CURSOR_KEY)
    if not raw:
        return datetime.now(UTC) - timedelta(minutes=5)
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC) - timedelta(minutes=5)


def _write_event_cursor(redis_client: Redis, timestamp: datetime) -> None:
    redis_client.set(EVENT_CURSOR_KEY, timestamp.isoformat())


def dispatch_event_triggered_rules(db: Session, redis_client: Redis) -> AutomationDispatchResult:
    cursor = _read_event_cursor(redis_client)
    publish_events = db.execute(
        select(PublishEvent)
        .where(PublishEvent.created_at > cursor)
        .order_by(PublishEvent.created_at.asc())
    ).scalars().all()
    if not publish_events:
        return AutomationDispatchResult(runs_created=0, rules_checked=0)

    rules = db.execute(
        select(AutomationRule).where(
            AutomationRule.is_enabled.is_(True),
            AutomationRule.trigger_type == AutomationTriggerType.EVENT.value,
        )
    ).scalars().all()

    created_runs = 0
    for event in publish_events:
        for rule in rules:
            if rule.company_id != event.company_id or rule.project_id != event.project_id:
                continue
            if not _event_rule_matches_publish_event(rule, event):
                continue
            try:
                run = create_automation_run(
                    db,
                    rule=rule,
                    trigger_reason="event_trigger",
                    trigger_metadata={
                        "trigger_event_id": str(event.id),
                        "publish_event_type": event.event_type,
                        "publish_event_status": event.status,
                    },
                )
                enqueue_automation_run(run.id)
                created_runs += 1
            except ValueError:
                continue

    latest_event_time = publish_events[-1].created_at
    if latest_event_time is not None:
        _write_event_cursor(redis_client, latest_event_time)

    return AutomationDispatchResult(runs_created=created_runs, rules_checked=len(rules))


def _check_guardrails(db: Session, *, rule: AutomationRule, now: datetime, title: str | None = None) -> list[str]:
    violations: list[str] = []
    guardrails = rule.guardrails_json or {}

    max_posts_per_day_project = int(guardrails.get("max_posts_per_day_project") or 0)
    if max_posts_per_day_project > 0:
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        posts_today = db.execute(
            select(func.count(Post.id)).where(
                Post.company_id == rule.company_id,
                Post.project_id == rule.project_id,
                Post.created_at >= day_start,
                Post.created_at < day_end,
            )
        ).scalar_one()
        if int(posts_today or 0) >= max_posts_per_day_project:
            violations.append("max_posts_per_day_project")

    quiet_hours = guardrails.get("quiet_hours") or {}
    start_raw = str(quiet_hours.get("start") or "").strip()
    end_raw = str(quiet_hours.get("end") or "").strip()
    if start_raw and end_raw:
        try:
            start_hour = int(start_raw.split(":")[0])
            end_hour = int(end_raw.split(":")[0])
            now_hour = now.hour
            if start_hour <= end_hour:
                in_quiet = start_hour <= now_hour < end_hour
            else:
                in_quiet = now_hour >= start_hour or now_hour < end_hour
            if in_quiet:
                violations.append("quiet_hours")
        except (TypeError, ValueError):
            pass

    blackout_dates = {str(item) for item in (guardrails.get("blackout_dates") or [])}
    if now.date().isoformat() in blackout_dates:
        violations.append("blackout_date")

    duplicate_topic_days = int(guardrails.get("duplicate_topic_days") or 0)
    if duplicate_topic_days > 0 and title:
        since = now - timedelta(days=duplicate_topic_days)
        duplicate = db.execute(
            select(ContentItem.id).where(
                ContentItem.company_id == rule.company_id,
                ContentItem.project_id == rule.project_id,
                ContentItem.title == title,
                ContentItem.created_at >= since,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            violations.append("duplicate_topic")

    return violations


def _action_generate_post(db: Session, run: AutomationRun, rule: AutomationRule) -> dict[str, Any]:
    action_config = rule.action_config_json or {}
    campaign = None
    if rule.campaign_id:
        campaign = db.execute(
            select(Campaign).where(
                Campaign.id == rule.campaign_id,
                Campaign.company_id == run.company_id,
                Campaign.project_id == run.project_id,
            )
        ).scalar_one_or_none()

    template = None
    template_id_raw = action_config.get("template_id")
    if template_id_raw:
        try:
            template_id = UUID(str(template_id_raw))
            template = db.execute(
                select(ContentTemplate).where(
                    ContentTemplate.id == template_id,
                    ContentTemplate.company_id == run.company_id,
                    ContentTemplate.project_id == run.project_id,
                )
            ).scalar_one_or_none()
        except ValueError:
            template = None

    if template and template.template_type != ContentTemplateType.POST_TEXT.value:
        raise ValueError("unsupported_template_type_for_generate_post")

    prompt_template = (
        template.prompt_template
        if template is not None
        else (
            action_config.get("prompt_template")
            or "Napisz angażujący post o {{topic}} dla {{brand.voice}} z CTA {{offer}}."
        )
    )
    output_schema = (
        template.output_schema_json
        if template is not None and template.output_schema_json
        else DEFAULT_POST_TEXT_OUTPUT_SCHEMA
    )
    variables = {
        **(template.default_values_json if template is not None else {}),
        **(action_config.get("variables") or {}),
    }
    brand_profile = (campaign.brand_profile_json if campaign is not None else {}) or {}
    language = (
        action_config.get("language")
        or (campaign.language if campaign is not None else None)
        or "pl"
    )

    ai_provider = get_ai_provider()
    try:
        generated = asyncio.run(
            ai_provider.generate_post_text(
                AIContentRequest(
                    template=str(prompt_template),
                    output_schema=output_schema,
                    variables=variables,
                    brand_profile=brand_profile,
                    language=str(language),
                )
            )
        )
    except AIProviderError as exc:
        failed_item = ContentItem(
            company_id=run.company_id,
            project_id=run.project_id,
            campaign_id=rule.campaign_id,
            template_id=(template.id if template is not None else None),
            status=ContentItemStatus.FAILED.value,
            title="AI generation failed",
            body="",
            metadata_json={
                "generated_by_rule_id": str(rule.id),
                "error": str(exc),
                "variables": variables,
            },
            source=ContentItemSource.AI.value,
        )
        db.add(failed_item)
        db.flush()
        emit_automation_event(
            db,
            company_id=run.company_id,
            project_id=run.project_id,
            run_id=run.id,
            event_type="ContentGenerationFailed",
            status="error",
            metadata_json={"content_item_id": str(failed_item.id), "error": str(exc)},
        )
        raise ValueError("ai_generation_failed") from exc

    generated_title = str(generated.get("title") or "").strip()
    generated_body = str(generated.get("body") or "").strip()
    risk_flags = generated.get("risk_flags") or []
    requires_approval = bool((rule.guardrails_json or {}).get("approval_required", False))
    if isinstance(risk_flags, list) and any(str(flag).lower() != "none" for flag in risk_flags):
        requires_approval = True

    status = ContentItemStatus.NEEDS_REVIEW.value if requires_approval else ContentItemStatus.DRAFT.value
    violations = _check_guardrails(db, rule=rule, now=datetime.now(UTC), title=generated_title)
    if violations:
        status = ContentItemStatus.NEEDS_REVIEW.value

    item = ContentItem(
        company_id=run.company_id,
        project_id=run.project_id,
        campaign_id=rule.campaign_id,
        template_id=(template.id if template is not None else None),
        status=status,
        title=generated_title,
        body=generated_body,
        metadata_json={
            "generated_by_rule_id": str(rule.id),
            "guardrail_violations": violations,
            "channels": generated.get("channels", []),
            "hashtags": generated.get("hashtags", []),
            "cta": generated.get("cta"),
            "risk_flags": risk_flags,
            "ai_output": generated,
        },
        source=ContentItemSource.AI.value,
    )
    if is_feature_enabled(db, key="beta_ai_quality", tenant_id=run.company_id):
        policy = get_or_create_policy(db, company_id=run.company_id, project_id=run.project_id)
        quality = evaluate_text(
            text=item.body,
            title=item.title,
            policy_json=policy.policy_json,
        )
        item.metadata_json = apply_quality_to_content_metadata(metadata_json=item.metadata_json, evaluation=quality)
        item.status = choose_content_status(current_status=item.status, evaluation=quality)
    db.add(item)
    db.flush()

    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="ContentGenerated",
        status="ok",
        metadata_json={"content_item_id": str(item.id), "status": item.status},
    )
    if item.status == ContentItemStatus.NEEDS_REVIEW.value:
        emit_automation_event(
            db,
            company_id=run.company_id,
            project_id=run.project_id,
            run_id=run.id,
            event_type="ApprovalRequired",
            status="ok",
            metadata_json={"content_item_id": str(item.id)},
        )
    return {"generated_content_items": 1, "generated_content_item_ids": [str(item.id)]}


def _action_schedule_post(db: Session, run: AutomationRun, rule: AutomationRule) -> dict[str, Any]:
    action_config = rule.action_config_json or {}
    publish_at_raw = action_config.get("publish_at")
    publish_at = datetime.now(UTC) + timedelta(minutes=5)
    if isinstance(publish_at_raw, str) and publish_at_raw.strip():
        try:
            parsed = datetime.fromisoformat(publish_at_raw)
            publish_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass

    candidate_items = db.execute(
        select(ContentItem).where(
            ContentItem.company_id == run.company_id,
            ContentItem.project_id == run.project_id,
            ContentItem.status.in_([ContentItemStatus.APPROVED.value, ContentItemStatus.DRAFT.value]),
        )
    ).scalars().all()
    if not candidate_items:
        return {"scheduled_posts": 0}

    scheduled_posts = 0
    for item in candidate_items:
        post = Post(
            company_id=run.company_id,
            project_id=run.project_id,
            title=item.title or "Automated post",
            content=item.body,
            status=PostStatus.SCHEDULED.value,
            publish_at=publish_at,
        )
        db.add(post)
        db.flush()
        item.status = ContentItemStatus.SCHEDULED.value
        emit_publish_event(
            db,
            company_id=post.company_id,
            project_id=post.project_id,
            post_id=post.id,
            event_type="PostScheduled",
            status="ok",
            metadata_json={"source": "automation", "run_id": str(run.id)},
        )
        scheduled_posts += 1

    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="PostsScheduled",
        status="ok",
        metadata_json={"scheduled_posts": scheduled_posts},
    )
    return {"scheduled_posts": scheduled_posts}


def _action_publish_now(db: Session, run: AutomationRun, rule: AutomationRule) -> dict[str, Any]:
    action_config = rule.action_config_json or {}
    limit = int(action_config.get("limit") or 5)
    posts = db.execute(
        select(Post).where(
            Post.company_id == run.company_id,
            Post.project_id == run.project_id,
            Post.status.in_([PostStatus.DRAFT.value, PostStatus.SCHEDULED.value]),
        )
    ).scalars().all()

    published_now = 0
    now = datetime.now(UTC)
    for post in posts[: max(1, limit)]:
        post.status = PostStatus.SCHEDULED.value
        post.publish_at = now
        emit_publish_event(
            db,
            company_id=post.company_id,
            project_id=post.project_id,
            post_id=post.id,
            event_type="PostScheduled",
            status="ok",
            metadata_json={"source": "automation_publish_now", "run_id": str(run.id)},
        )
        publish_post_async(post.company_id, post.id)
        published_now += 1

    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="PublishEnqueued",
        status="ok",
        metadata_json={"enqueued_posts": published_now},
    )
    return {"enqueued_posts": published_now}


def execute_automation_run_runtime(db: Session, *, run_id: UUID) -> dict[str, Any]:
    run = db.execute(select(AutomationRun).where(AutomationRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise ValueError("run_not_found")
    if run.status not in [AutomationRunStatus.QUEUED.value, AutomationRunStatus.RUNNING.value]:
        return {"status": "ignored", "reason": "terminal_state"}

    rule = db.execute(
        select(AutomationRule).where(
            AutomationRule.id == run.rule_id,
            AutomationRule.company_id == run.company_id,
            AutomationRule.project_id == run.project_id,
        )
    ).scalar_one_or_none()
    if rule is None:
        raise ValueError("rule_not_found")

    now = datetime.now(UTC)
    run.status = AutomationRunStatus.RUNNING.value
    run.started_at = run.started_at or now
    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="AutomationRunStarted",
        status="ok",
        metadata_json={"rule_id": str(rule.id), "action_type": rule.action_type},
    )

    if rule.action_type == AutomationActionType.GENERATE_POST.value:
        stats = _action_generate_post(db, run, rule)
    elif rule.action_type == AutomationActionType.SCHEDULE_POST.value:
        stats = _action_schedule_post(db, run, rule)
    elif rule.action_type == AutomationActionType.PUBLISH_NOW.value:
        stats = _action_publish_now(db, run, rule)
    elif rule.action_type == AutomationActionType.SYNC_METRICS.value:
        stats = {"sync_metrics": "queued"}
        emit_automation_event(
            db,
            company_id=run.company_id,
            project_id=run.project_id,
            run_id=run.id,
            event_type="MetricsSyncQueued",
            status="ok",
            metadata_json={},
        )
    else:
        raise ValueError(f"unsupported_action_type:{rule.action_type}")

    run.finished_at = datetime.now(UTC)
    run.status = AutomationRunStatus.SUCCESS.value
    run.stats_json = {**(run.stats_json or {}), **stats}
    emit_automation_event(
        db,
        company_id=run.company_id,
        project_id=run.project_id,
        run_id=run.id,
        event_type="AutomationRunCompleted",
        status="ok",
        metadata_json=run.stats_json,
    )
    return {"status": run.status, "stats": run.stats_json}
