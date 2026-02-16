from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.brand_profile import BrandProfile
from app.domain.models.post import Post
from app.domain.models.post_quality_report import PostQualityReport


TONE_KEYWORDS: dict[str, list[str]] = {
    "professional": ["strategy", "results", "performance", "efficiency", "insight"],
    "friendly": ["hello", "together", "community", "thanks", "share"],
    "premium": ["exclusive", "premium", "craft", "luxury", "elevated"],
    "playful": ["fun", "wow", "creative", "challenge", "spark"],
}

PII_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PII_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3}[\s.-]?\d{3,4}")
SPAM_PUNCT_RE = re.compile(r"[!?]{4,}")


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    severity: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class QualityCheckResult:
    score: int
    risk_level: str
    issues: list[dict[str, str]]
    recommendations: list[str]


def _normalize_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _tokenize(text: str) -> set[str]:
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return {token for token in clean.split() if token}


def _trigrams(text: str) -> set[str]:
    clean = re.sub(r"\s+", " ", text.lower().strip())
    if len(clean) < 3:
        return {clean} if clean else set()
    return {clean[i : i + 3] for i in range(len(clean) - 2)}


def _jaccard_similarity(a: str, b: str) -> float:
    a_tokens = _trigrams(a)
    b_tokens = _trigrams(b)
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = len(a_tokens.intersection(b_tokens))
    universe = len(a_tokens.union(b_tokens))
    return overlap / universe if universe else 0.0


def resolve_brand_profile(
    db: Session,
    *,
    tenant_id: UUID,
    project_id: UUID,
    brand_profile_id: UUID | None = None,
) -> BrandProfile | None:
    if brand_profile_id is not None:
        explicit = db.execute(
            select(BrandProfile).where(
                BrandProfile.id == brand_profile_id,
                BrandProfile.company_id == tenant_id,
            )
        ).scalar_one_or_none()
        if explicit is not None:
            return explicit

    project_profile = db.execute(
        select(BrandProfile).where(
            BrandProfile.company_id == tenant_id,
            BrandProfile.project_id == project_id,
        )
    ).scalar_one_or_none()
    if project_profile is not None:
        return project_profile

    return db.execute(
        select(BrandProfile).where(
            BrandProfile.company_id == tenant_id,
            BrandProfile.project_id.is_(None),
        )
    ).scalar_one_or_none()


def evaluate_post_quality(
    *,
    title: str,
    body: str,
    brand_profile: BrandProfile | None,
    recent_posts: list[Post],
) -> QualityCheckResult:
    text = f"{title}\n{body}".strip()
    normalized = text.lower()
    issues: list[Issue] = []

    forbidden_claims = _normalize_list(brand_profile.forbidden_claims if brand_profile else [])
    for claim in forbidden_claims:
        if claim.lower() in normalized:
            issues.append(
                Issue(
                    code="forbidden_claim",
                    message=f"Forbidden claim detected: '{claim}'.",
                    severity="block",
                    suggestion="Remove absolute or non-compliant claims from the post.",
                )
            )

    prohibited_words = _normalize_list(brand_profile.dont_list if brand_profile else [])
    for word in prohibited_words:
        if word.lower() in normalized:
            issues.append(
                Issue(
                    code="prohibited_word",
                    message=f"Prohibited word detected: '{word}'.",
                    severity="warn",
                    suggestion="Replace prohibited wording with neutral brand-safe phrasing.",
                )
            )

    if PII_EMAIL_RE.search(text):
        issues.append(
            Issue(
                code="pii_email",
                message="Potential email address detected.",
                severity="block",
                suggestion="Remove personal emails from public posts.",
            )
        )
    if PII_PHONE_RE.search(text):
        issues.append(
            Issue(
                code="pii_phone",
                message="Potential phone number detected.",
                severity="block",
                suggestion="Remove personal phone numbers from public content.",
            )
        )

    alpha_chars = [char for char in text if char.isalpha()]
    caps_ratio = (sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)) if alpha_chars else 0.0
    if caps_ratio > 0.45:
        issues.append(
            Issue(
                code="caps_ratio_high",
                message="Excessive capitalization detected.",
                severity="warn",
                suggestion="Use sentence case to improve readability and trust.",
            )
        )

    if SPAM_PUNCT_RE.search(text):
        issues.append(
            Issue(
                code="spam_punctuation",
                message="Spam-like punctuation detected.",
                severity="warn",
                suggestion="Reduce repeated punctuation marks.",
            )
        )

    max_similarity = 0.0
    for recent in recent_posts:
        candidate = f"{recent.title}\n{recent.content}".strip()
        max_similarity = max(max_similarity, _jaccard_similarity(text, candidate))
    if max_similarity >= 0.72:
        issues.append(
            Issue(
                code="duplicate_similarity",
                message=f"Content is too similar to recent posts ({max_similarity:.2f}).",
                severity="warn",
                suggestion="Change angle, hook, and CTA to avoid repetition.",
            )
        )

    tone = (brand_profile.tone if brand_profile else "professional").strip().lower()
    keywords = TONE_KEYWORDS.get(tone, TONE_KEYWORDS["professional"])
    token_set = _tokenize(text)
    tone_hits = sum(1 for token in keywords if token in token_set)
    tone_score = tone_hits / len(keywords) if keywords else 1.0
    if tone_score < 0.2:
        issues.append(
            Issue(
                code="tone_mismatch",
                message=f"Content tone may not match '{tone}'.",
                severity="warn",
                suggestion="Adjust wording to better match selected brand tone.",
            )
        )

    score = 100
    for issue in issues:
        if issue.severity == "block":
            score -= 35
        elif issue.severity == "warn":
            score -= 15
        else:
            score -= 5
    score = max(0, min(100, score))

    has_block = any(issue.severity == "block" for issue in issues)
    if has_block or score < 55:
        risk_level = "high"
    elif score < 80:
        risk_level = "medium"
    else:
        risk_level = "low"

    recommendations = []
    for issue in issues:
        if issue.suggestion not in recommendations:
            recommendations.append(issue.suggestion)

    return QualityCheckResult(
        score=score,
        risk_level=risk_level,
        issues=[issue.to_dict() for issue in issues],
        recommendations=recommendations,
    )


def create_post_quality_report(
    db: Session,
    *,
    post: Post,
    result: QualityCheckResult,
) -> PostQualityReport:
    report = PostQualityReport(
        post_id=post.id,
        company_id=post.company_id,
        project_id=post.project_id,
        score=result.score,
        risk_level=result.risk_level,
        issues=result.issues,
    )
    db.add(report)
    db.flush()
    return report


def get_latest_quality_report(db: Session, *, tenant_id: UUID, post_id: UUID) -> PostQualityReport | None:
    return db.execute(
        select(PostQualityReport)
        .where(PostQualityReport.company_id == tenant_id, PostQualityReport.post_id == post_id)
        .order_by(PostQualityReport.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def extract_recommendations(issues: list[dict[str, str]]) -> list[str]:
    suggestions: list[str] = []
    for issue in issues:
        suggestion = str(issue.get("suggestion") or "").strip()
        if not suggestion:
            continue
        for chunk in [part.strip() for part in suggestion.split("|")]:
            if chunk and chunk not in suggestions:
                suggestions.append(chunk)
    return suggestions
