import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings, get_settings


def test_defaults_load_without_env_file():
    settings = get_settings()
    assert settings.environment == "test"
    assert settings.app_name == "NutriChef AI"
    assert settings.embedding_model.startswith("sentence-transformers/")
    assert settings.has_llm_key is False


def test_env_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    settings = Settings()
    assert settings.gemini_model == "gemini-test-model"
    assert settings.llm_temperature == 0.7


def test_api_key_is_secret_and_never_printed(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaFAKEKEY1234567890abcdefgh")
    settings = Settings()
    assert settings.has_llm_key
    assert "AIzaFAKE" not in repr(settings)
    assert "AIzaFAKE" not in str(settings.google_api_key)
    assert settings.google_api_key.get_secret_value().startswith("AIza")


def test_blank_api_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "   ")
    assert Settings().has_llm_key is False


def test_log_level_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"


def test_invalid_temperature_rejected(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "5")
    with pytest.raises(ValidationError):
        Settings()


def test_relative_paths_resolve_to_project_root():
    settings = Settings()
    assert settings.chroma_dir.is_absolute()
    assert settings.chroma_dir.is_relative_to(PROJECT_ROOT)


def test_production_requires_real_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaFAKEKEY1234567890abcdefgh")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me")
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings()


def test_production_requires_llm_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-long-random-secret-value-for-tests")
    with pytest.raises(ValidationError, match="GOOGLE_API_KEY"):
        Settings()


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
