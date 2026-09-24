"""Actionable provider errors without dumping request bodies or credentials."""

import json
import os
import re


def safe_text(value: str) -> str:
    for name, secret in os.environ.items():
        if name.endswith("_API_KEY") and secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return " ".join(value.split())[:1200]


def message_from(value: object) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        return message_from(parsed) if isinstance(parsed, dict) else ""
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, str):
            return message
        return message_from(value.get("error"))
    return ""


def describe_error(exc: Exception) -> str:
    if not type(exc).__module__.startswith("openrouter."):
        return safe_text(str(exc))
    try:
        body = json.loads(getattr(exc, "body", ""))
    except (ValueError, TypeError):
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    metadata = error.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    code = getattr(exc, "status_code", None)
    title = safe_text(message_from(error) or str(exc))
    lines = [f"OpenRouter HTTP {code}: {title}" if code else f"OpenRouter: {title}"]
    provider = metadata.get("provider_name")
    if isinstance(provider, str) and provider:
        lines.append(f"Provider: {safe_text(provider)}")
    detail = safe_text(message_from(metadata.get("raw")))
    if detail and detail != title:
        lines.append(f"Details: {detail}")
    if code == 429:
        if metadata.get("limit_source") == "upstream_provider_shared_pool":
            lines.append("The provider's shared free capacity is rate-limited.")
        lines.append("Retry later. You can also select another available :free model in .env.")
    elif code == 404 or "unavailable for free" in title.lower():
        lines.append(
            "Choose an available model with tool support in .env; keep :free for free use."
        )
    if code in (429, 404) or "unavailable for free" in title.lower():
        lines.append(
            "After changing QUIZPILOT_MODEL in .env, start --live or --resume your saved quiz."
        )
    return "\n".join(lines)
