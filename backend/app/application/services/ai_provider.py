import json
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate

from app.application.services.template_renderer import render_prompt_template
from app.core.config import settings

DEFAULT_POST_TEXT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["title", "body", "hashtags", "cta", "channels", "risk_flags"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 5, "maxLength": 120},
        "body": {"type": "string", "minLength": 50, "maxLength": 3000},
        "hashtags": {
            "type": "array",
            "items": {"type": "string", "minLength": 2, "maxLength": 50},
            "maxItems": 12,
        },
        "cta": {"type": "string", "minLength": 2, "maxLength": 140},
        "channels": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
    },
}


class AIProviderError(Exception):
    pass


class AIProviderValidationError(AIProviderError):
    pass


@dataclass(frozen=True)
class AIContentRequest:
    template: str
    output_schema: dict[str, Any]
    variables: dict[str, Any]
    brand_profile: dict[str, Any]
    language: str
    max_retries: int = 2


class BaseAIProvider:
    async def generate_post_text(self, request: AIContentRequest) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.base_url = settings.openai_base_url.rstrip("/")
        self.timeout_seconds = settings.openai_timeout_seconds
        self.temperature = settings.openai_temperature

    async def generate_post_text(self, request: AIContentRequest) -> dict[str, Any]:
        if not self.api_key:
            raise AIProviderError("OPENAI_API_KEY is not configured")

        rendered_prompt = render_prompt_template(request.template, request.variables)
        output_schema = request.output_schema or DEFAULT_POST_TEXT_OUTPUT_SCHEMA
        brand_json = json.dumps(request.brand_profile or {}, ensure_ascii=False)
        schema_json = json.dumps(output_schema, ensure_ascii=False)

        system_prompt = (
            "You are a deterministic social media content generator for SaaS automation. "
            "Return ONLY strict JSON and never include markdown. "
            f"Output language must be: {request.language}. "
            "Follow brand profile exactly and avoid forbidden topics."
        )

        user_prompt = (
            f"Brand profile JSON:\n{brand_json}\n\n"
            f"Output JSON schema:\n{schema_json}\n\n"
            f"Task prompt:\n{rendered_prompt}\n\n"
            "Return only JSON object matching schema."
        )

        last_error: Exception | None = None
        correction_prompt = ""
        for attempt in range(request.max_retries + 1):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n{correction_prompt}"},
            ]
            try:
                payload = await self._call_openai(messages)
                self._validate_response_payload(
                    payload=payload,
                    output_schema=output_schema,
                    language=request.language,
                    brand_profile=request.brand_profile or {},
                )
                return payload
            except (AIProviderError, AIProviderValidationError) as exc:
                last_error = exc
                correction_prompt = (
                    f"\nPrevious output was invalid: {str(exc)}. "
                    "Regenerate valid JSON strictly matching schema and constraints."
                )
                continue

        raise AIProviderError(f"AI generation failed after retries: {last_error}")

    async def _call_openai(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        request_body = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=request_body,
            )
        if response.status_code >= 400:
            raise AIProviderError(
                f"OpenAI API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIProviderError("OpenAI API returned no choices")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("OpenAI response content is empty")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderValidationError(f"Invalid JSON returned: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AIProviderValidationError("Output must be JSON object")
        return parsed

    def _validate_response_payload(
        self,
        *,
        payload: dict[str, Any],
        output_schema: dict[str, Any],
        language: str,
        brand_profile: dict[str, Any],
    ) -> None:
        try:
            validate(instance=payload, schema=output_schema)
        except JsonSchemaValidationError as exc:
            raise AIProviderValidationError(f"Schema validation failed: {exc.message}") from exc

        title = str(payload.get("title", ""))
        body = str(payload.get("body", ""))
        if len(title) < 5 or len(title) > 120:
            raise AIProviderValidationError("Title length is out of bounds")
        if len(body) < 50 or len(body) > 3000:
            raise AIProviderValidationError("Body length is out of bounds")

        forbidden_topics = {
            str(item).strip().lower()
            for item in (brand_profile.get("forbidden_topics") or [])
            if str(item).strip()
        }
        forbidden_words = {
            str(item).strip().lower()
            for item in (brand_profile.get("forbidden_words") or [])
            if str(item).strip()
        }
        normalized_text = f"{title}\n{body}".lower()
        for token in forbidden_topics.union(forbidden_words):
            if token and token in normalized_text:
                raise AIProviderValidationError(f"Forbidden token detected: {token}")

        if language.lower() in {"pl", "polish"}:
            # Basic compliance heuristic for Polish output.
            polish_markers = [" i ", " oraz ", " że ", " się ", " na "]
            if not any(marker in f" {normalized_text} " for marker in polish_markers):
                raise AIProviderValidationError("Language compliance check failed for Polish output")


def get_ai_provider() -> BaseAIProvider:
    provider = settings.ai_provider.strip().lower()
    if provider == "openai":
        return OpenAIProvider()
    raise AIProviderError(f"Unsupported AI provider: {settings.ai_provider}")
