"""Configuration is explicit: demo by default, model calls only in live mode."""

import os
from importlib.resources import files
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DATABASE = Path(".quizpilot/sessions.sqlite3")
DEFAULT_TOPIC = "Python basics"


def load_environment() -> None:
    # The project's .env is authoritative, including over stale shell exports.
    load_dotenv(Path.cwd() / ".env", override=True)


def configured_model() -> str:
    model = os.environ.get("QUIZPILOT_MODEL", "").strip()
    if not model:
        raise ValueError("Set QUIZPILOT_MODEL to provider:model-name in .env for live mode.")
    return model


def validate_live_config(model: str) -> None:
    if ":" not in model or not model.split(":", 1)[1].strip():
        raise ValueError("Set QUIZPILOT_MODEL to provider:model-name in .env.")
    provider = model.split(":", 1)[0]
    if provider not in {"openrouter", "openai", "anthropic", "ollama"}:
        raise ValueError("Supported model providers are openrouter, openai, anthropic, and ollama.")
    key_name = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider)
    if key_name and not os.environ.get(key_name, "").strip():
        guidance = (
            "OpenRouter requires a key even for free models."
            if provider == "openrouter"
            else "Hosted API usage requires credits or billing."
        )
        raise ValueError(
            f"Set {key_name} in .env for live mode. {guidance} --demo makes no model calls."
        )


def load_notes(path: Path | None = None) -> str:
    if path is not None:
        if path.stat().st_size > 100_000:
            raise ValueError("Keep lesson notes under 100 KB for this small project.")
        notes = path.read_text(encoding="utf-8")
    else:
        notes = files("quizpilot").joinpath("data/python_basics.md").read_text(encoding="utf-8")
    if not notes.strip():
        raise ValueError("Lesson notes cannot be empty.")
    if len(notes) > 20_000:
        raise ValueError("Keep lesson notes under 20,000 characters for this small project.")
    return notes


def topic_from_notes(notes: str, path: Path) -> str:
    """Use the lesson's title or filename instead of labeling it Python basics."""
    for line in notes.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return path.stem.replace("_", " ").replace("-", " ").strip() or "Custom lesson"
