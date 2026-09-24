import json

import httpx
import pytest

from quizpilot.errors import describe_error

OpenRouterError = pytest.importorskip("openrouter.errors").OpenRouterError


def provider_error(status, message, metadata=None):
    response = httpx.Response(
        status,
        json={"error": {"code": status, "message": message, "metadata": metadata or {}}},
    )
    return OpenRouterError(message, response)


def test_shared_free_pool_limit_is_explained_and_credentials_redacted(monkeypatch):
    key = "private-test-api-key"
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    exc = provider_error(
        429,
        "Provider returned error",
        {
            "provider_name": "Google AI Studio",
            "limit_source": "upstream_provider_shared_pool",
            "raw": f"Model is temporarily rate-limited upstream. Key: {key}",
        },
    )
    message = describe_error(exc)
    assert "HTTP 429" in message
    assert "Google AI Studio" in message
    assert "shared free capacity" in message
    assert "QUIZPILOT_MODEL in .env" in message
    assert "--resume your saved quiz" in message
    assert key not in message
    assert "[REDACTED]" in message


def test_nested_provider_error_shows_message_without_echoing_request():
    exc = provider_error(
        400,
        "Provider returned error",
        {
            "raw": json.dumps(
                {
                    "error": {"message": "Unsupported tool schema"},
                    "request": {"messages": ["Private quiz rubric"]},
                }
            )
        },
    )
    message = describe_error(exc)
    assert "Unsupported tool schema" in message
    assert "Private quiz rubric" not in message


def test_removed_free_model_explains_how_to_change_configuration():
    message = describe_error(provider_error(404, "This model is unavailable for free."))
    assert "keep :free for free use" in message
    assert "start --live or --resume your saved quiz" in message


def test_plain_errors_keep_their_message():
    assert describe_error(ValueError("Lesson notes cannot be empty.")) == (
        "Lesson notes cannot be empty."
    )
