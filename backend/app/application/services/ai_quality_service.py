from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.ai_quality_policy import AIQualityPolicy
from app.domain.models.content_item import ContentItemStatus

DEFAULT_POLICY = {
    "brand_voice_keywords": [],
    "forbidden_topics": [],
    "max_caps_ratio": 0.35,
    "max_exclamation_count": 4,
    "require_approval_risk_score": 0.65,
}


@dataclass(frozen=True)
class QualityEvaluation:
    risk_score: float
    tone_score: float
    risk_flags: list[str]
    needs_approval: bool
    metadata: dict


def get_or_create_policy(db: Session, *, company_id: UUID, project_id: UUID, created_by_user_id: UUID | None = None) -> AIQualityPolicy:
    policy = db.execute(
        select(AIQualityPolicy).where(
            AIQualityPolicy.company_id == company_id,
            AIQualityPolicy.project_id == project_id,
        )
    ).scalar_one_or_none()
    if policy:
        return policy
    policy = AIQualityPolicy(
        company_id=company_id,
        project_id=project_id,
        policy_json=DEFAULT_POLICY.copy(),
        created_by_user_id=created_by_user_id,
    )
    db.add(policy)
    db.flush()
    return policy


def evaluate_text(*, text: str, title: str | None, policy_json: dict | None) -> QualityEvaluation:
    policy = {**DEFAULT_POLICY, **(policy_json or {})}
    normalized_text = f"{title or ''}\n{text}".strip().lower()
    forbidden_topics = [str(item).strip().lower() for item in (policy.get("forbidden_topics") or []) if str(item).strip()]
    voice_keywords = [str(item).strip().lower() for item in (policy.get("brand_voice_keywords") or []) if str(item).strip()]

    flags: list[str] = []
    forbidden_matches = [topic for topic in forbidden_topics if topic and topic in normalized_text]
    if forbidden_matches:
        flags.append("forbidden_topic")

    alpha_chars = [ch for ch in text if ch.isalpha()]
    upper_chars = [ch for ch in alpha_chars if ch.isupper()]
    caps_ratio = (len(upper_chars) / len(alpha_chars)) if alpha_chars else 0.0
    if caps_ratio > float(policy.get("max_caps_ratio", DEFAULT_POLICY["max_caps_ratio"])):
        flags.append("shouting_style")

    exclamation_count = text.count("!")
    if exclamation_count > int(policy.get("max_exclamation_count", DEFAULT_POLICY["max_exclamation_count"])):
        flags.append("aggressive_punctuation")

    tone_hits = sum(1 for keyword in voice_keywords if keyword in normalized_text)
    tone_score = (tone_hits / len(voice_keywords)) if voice_keywords else 1.0
    if tone_score < 0.4:
        flags.append("tone_mismatch")

    hashtag_count = len(re.findall(r"#\w+", text))
    if hashtag_count > 12:
        flags.append("hashtag_overload")

    risk_score = min(1.0, (len(flags) * 0.22) + (0.25 if forbidden_matches else 0.0) + ((1 - tone_score) * 0.25))
    threshold = float(policy.get("require_approval_risk_score", DEFAULT_POLICY["require_approval_risk_score"]))
    needs_approval = risk_score >= threshold

    return QualityEvaluation(
        risk_score=round(risk_score, 4),
        tone_score=round(tone_score, 4),
        risk_flags=(flags if flags else ["none"]),
        needs_approval=needs_approval,
        metadata={
            "forbidden_matches": forbidden_matches,
            "caps_ratio": round(caps_ratio, 4),
            "exclamation_count": exclamation_count,
            "hashtag_count": hashtag_count,
            "threshold": threshold,
        },
    )


def apply_quality_to_content_metadata(*, metadata_json: dict | None, evaluation: QualityEvaluation) -> dict:
    return {
        **(metadata_json or {}),
        "quality": {
            "risk_score": evaluation.risk_score,
            "tone_score": evaluation.tone_score,
            "risk_flags": evaluation.risk_flags,
            "needs_approval": evaluation.needs_approval,
            **evaluation.metadata,
        },
    }


def choose_content_status(*, current_status: str, evaluation: QualityEvaluation) -> str:
    if evaluation.needs_approval:
        return ContentItemStatus.NEEDS_REVIEW.value
    return current_status

