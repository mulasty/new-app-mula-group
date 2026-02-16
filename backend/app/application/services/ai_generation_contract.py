from __future__ import annotations

from typing import Any

from app.application.services.ai_provider import DEFAULT_POST_TEXT_OUTPUT_SCHEMA


def build_generation_contract(
    *,
    template: str,
    variables: dict[str, Any],
    brand_profile: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    return {
        "template": template,
        "variables": variables,
        "brand_profile": {
            "brand_name": brand_profile.get("brand_name"),
            "tone": brand_profile.get("tone") or brand_profile.get("voice"),
            "do_list": brand_profile.get("do_list") or brand_profile.get("do") or [],
            "dont_list": brand_profile.get("dont_list") or brand_profile.get("dont") or [],
            "forbidden_claims": brand_profile.get("forbidden_claims") or brand_profile.get("forbidden_topics") or [],
            "preferred_hashtags": brand_profile.get("preferred_hashtags") or [],
            "compliance_notes": brand_profile.get("compliance_notes") or "",
        },
        "language": language,
        "output_contract": {
            "required": ["title", "body", "hashtags", "cta"],
            "schema": DEFAULT_POST_TEXT_OUTPUT_SCHEMA,
        },
    }
