from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedProviderError:
    provider: str
    error_code: str
    category: str
    retryable: bool
    suggested_action: str


def map_provider_error(*, provider: str, error_code: str | None, message: str) -> NormalizedProviderError:
    normalized_provider = provider.strip().lower()
    code = (error_code or "unknown_error").strip().lower()
    text = (message or "").lower()

    if any(token in code for token in ("auth", "token", "invalid_grant")) or "unauthorized" in text:
        return NormalizedProviderError(
            provider=normalized_provider,
            error_code=code,
            category="auth",
            retryable=False,
            suggested_action="Reconnect connector and refresh credentials",
        )
    if any(token in code for token in ("rate", "throttle", "too_many_requests")) or "rate limit" in text:
        return NormalizedProviderError(
            provider=normalized_provider,
            error_code=code,
            category="rate_limit",
            retryable=True,
            suggested_action="Wait for cooldown and retry with backoff",
        )
    if any(token in code for token in ("content", "policy", "rejected")):
        return NormalizedProviderError(
            provider=normalized_provider,
            error_code=code,
            category="content_rejected",
            retryable=False,
            suggested_action="Adjust content to platform policy and retry",
        )
    if any(token in code for token in ("server", "timeout", "unavailable", "network")):
        return NormalizedProviderError(
            provider=normalized_provider,
            error_code=code,
            category="server_error",
            retryable=True,
            suggested_action="Retry later; provider instability detected",
        )

    return NormalizedProviderError(
        provider=normalized_provider,
        error_code=code,
        category="server_error",
        retryable=True,
        suggested_action="Retry later and inspect provider diagnostics",
    )
