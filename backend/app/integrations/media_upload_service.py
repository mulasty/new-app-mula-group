import hashlib
from urllib.parse import urlparse


async def upload_media(platform: str, file_reference: str) -> dict:
    """
    Platform-neutral media upload abstraction.
    Current implementation normalizes remote media reference and returns
    a deterministic media identifier for adapter-level publishing calls.
    """
    normalized_platform = platform.strip().lower()
    normalized_reference = file_reference.strip()
    if not normalized_reference:
        raise ValueError("Media reference is required")

    parsed = urlparse(normalized_reference)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP/HTTPS media references are supported")

    digest = hashlib.sha1(f"{normalized_platform}:{normalized_reference}".encode("utf-8")).hexdigest()[:16]
    media_id = f"{normalized_platform}_{digest}"
    return {
        "platform": normalized_platform,
        "media_id": media_id,
        "source_url": normalized_reference,
    }
