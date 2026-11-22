"""Runtime settings read on instance creation so UI-managed changes take effect."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("UAS_ENVIRONMENT", "development"))
    app_name: str = "Universal AI Studio"
    api_prefix: str = "/api/v1"
    elasticsearch_url: str = field(default_factory=lambda: os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"))
    elasticsearch_index_prefix: str = field(default_factory=lambda: os.getenv("ELASTICSEARCH_INDEX_PREFIX", "uas"))
    elasticsearch_api_key: str | None = field(default_factory=lambda: os.getenv("ELASTICSEARCH_API_KEY"))
    elasticsearch_username: str | None = field(default_factory=lambda: os.getenv("ELASTICSEARCH_USERNAME"))
    elasticsearch_password: str | None = field(default_factory=lambda: os.getenv("ELASTICSEARCH_PASSWORD"))
    elasticsearch_verify_certs: bool = field(default_factory=lambda: _env_bool("ELASTICSEARCH_VERIFY_CERTS"))
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    request_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")))
    max_query_rows: int = field(default_factory=lambda: int(os.getenv("MAX_QUERY_ROWS", "1000")))

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache

def get_settings() -> Settings:
    return Settings()
