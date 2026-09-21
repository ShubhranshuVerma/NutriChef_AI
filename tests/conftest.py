"""Runs before every test: tests must never read your .env or call a paid API."""

import pytest

from app.core.config import Settings, get_settings

YOUR_SETTINGS = ["ENVIRONMENT", "LOG_LEVEL", "GOOGLE_API_KEY", "GEMINI_MODEL", "JWT_SECRET_KEY",
                 "DATABASE_URL", "EMBEDDING_MODEL", "LANGSMITH_API_KEY", "LLM_CACHE",
                 "LLM_THINKING"]


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    """Ignore the .env file and anything set in your shell, for every test."""
    for name in YOUR_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")   # never send test runs to LangSmith
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
