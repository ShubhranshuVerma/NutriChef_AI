"""Shared pytest fixtures.

Tests must never depend on your personal `.env` or call paid APIs,
so every test runs with a clean, test-only configuration.
"""

import pytest

from app.core.config import Settings, get_settings

_APP_ENV_VARS = [
    "ENVIRONMENT",
    "LOG_LEVEL",
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "JWT_SECRET_KEY",
    "DATABASE_URL",
    "EMBEDDING_MODEL",
]


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Ignore the developer's .env and real environment for every test."""
    for var in _APP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
