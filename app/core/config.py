"""Central application settings.

All configuration comes from environment variables (or a local `.env` file).
Import the cached instance anywhere with:

    from app.core.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_INSECURE_JWT_SECRETS = {"", "change-me", "changeme", "secret", "supersecretkey"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- App ----------
    app_name: str = "NutriChef AI"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ---------- LLM ----------
    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_cache: bool = True  # cache answers on disk; the free tier allows very few
    # How hard Gemini 3 models think before answering. Thinking happens before the
    # first word of the reply, so it is pure waiting; gemini-3.5-flash defaults to
    # "medium". Empty = send nothing, for models without thinking levels.
    llm_thinking: Literal["minimal", "low", "medium", "high"] | None = "low"

    # ---------- LangSmith (tracing) ----------
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "nutrichef-ai"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ---------- Embeddings / RAG (HuggingFace, runs locally) ----------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_dir: Path = Path("data/processed/chroma_db")
    recipenlg_csv_path: Path = Path("data/raw/RecipeNLG/full_dataset.csv")
    recipenlg_subset_size: int = Field(default=15000, gt=0)

    # ---------- Database ----------
    database_url: str = "sqlite:///data/processed/nutrichef.db"

    # ---------- MLflow ----------
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_experiment_name: str = "nutrichef-ranker"

    # ---------- Security ----------
    jwt_secret_key: SecretStr = SecretStr("change-me")
    jwt_expire_minutes: int = Field(default=60, gt=0, le=60 * 24 * 7)

    # ---------- Services ----------
    api_base_url: str = "http://localhost:8000"

    # Normalise things like "info" -> "INFO" before validation.
    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper() if isinstance(value, str) else value

    # Treat an empty GOOGLE_API_KEY= / LANGSMITH_API_KEY= / LLM_THINKING= line as "not set".
    @field_validator("google_api_key", "langsmith_api_key", "llm_thinking", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # Relative paths are resolved against the project root, so scripts work
    # no matter which folder you run them from.
    @field_validator("chroma_dir", "recipenlg_csv_path", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret_key.get_secret_value()
            if secret in _INSECURE_JWT_SECRETS or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be a strong value of at least 32 characters "
                    "in production (try: python -c \"import secrets; print(secrets.token_hex(32))\")"
                )
            if self.google_api_key is None:
                raise ValueError("GOOGLE_API_KEY is required in production")
        return self

    # ---------- Helpers ----------
    @property
    def has_llm_key(self) -> bool:
        return self.google_api_key is not None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def tracing_on(self) -> bool:
        """Tracing follows the key. No key, no traces, no noise."""
        return self.langsmith_api_key is not None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
