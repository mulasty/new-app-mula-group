from uuid import uuid4

from app.application.services.post_quality_service import evaluate_post_quality
from app.domain.models.brand_profile import BrandProfile
from app.domain.models.post import Post


def _brand_profile() -> BrandProfile:
    return BrandProfile(
        company_id=uuid4(),
        project_id=None,
        brand_name="Control Center",
        language="pl",
        tone="professional",
        target_audience="SMB",
        do_list=["clear"],
        dont_list=["cheap"],
        forbidden_claims=["guaranteed roi"],
        preferred_hashtags=["#controlcenter"],
        compliance_notes=None,
    )


def _post(title: str, content: str) -> Post:
    return Post(
        company_id=uuid4(),
        project_id=uuid4(),
        title=title,
        content=content,
        status="draft",
    )


def test_quality_flags_forbidden_and_pii() -> None:
    profile = _brand_profile()
    result = evaluate_post_quality(
        title="GUARANTEED ROI!!!",
        body="Contact us at john@example.com for guaranteed ROI right now!!!!",
        brand_profile=profile,
        recent_posts=[],
    )
    codes = {item["code"] for item in result.issues}
    assert "forbidden_claim" in codes
    assert "pii_email" in codes
    assert result.risk_level == "high"
    assert result.score < 60


def test_duplicate_similarity_detected() -> None:
    profile = _brand_profile()
    recent = [_post("Launch update", "Our new launch improves results for every team with better performance insights")]
    result = evaluate_post_quality(
        title="Launch update",
        body="Our new launch improves results for every team with better performance insights",
        brand_profile=profile,
        recent_posts=recent,
    )
    codes = {item["code"] for item in result.issues}
    assert "duplicate_similarity" in codes


def test_safe_text_returns_low_risk() -> None:
    profile = _brand_profile()
    result = evaluate_post_quality(
        title="Performance update",
        body="We share practical strategy insights to help teams improve campaign performance and efficiency.",
        brand_profile=profile,
        recent_posts=[],
    )
    assert result.risk_level in {"low", "medium"}
    assert result.score >= 70
