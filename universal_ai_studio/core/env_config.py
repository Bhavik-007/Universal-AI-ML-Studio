"""Unified environment/.env/Streamlit-secrets configuration access.

Environment variables (normally loaded from the project-root .env) take
precedence. Streamlit secrets are an optional backwards-compatible fallback.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
# Both names are accepted because Google GenAI SDKs and older app modules
# have used different conventional environment-variable names.
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
elif os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

_ENV_ALIASES = {
    ("openai", "api_key"): ("OPENAI_API_KEY",),
    ("openai", "api_version"): ("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    ("openai", "api_base"): ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_BASE"),
    ("openai", "deployment_name"): ("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME"),
    ("app_settings", "show_status_messages"): ("SHOW_STATUS_MESSAGES",),
    ("app_settings", "show_sql"): ("SHOW_SQL",),
    ("log_settings", "log_shipping"): ("LOG_SHIPPING",),
}


def _streamlit_secret(section: str, key: str | None = None, default: Any = None) -> Any:
    try:
        import streamlit as st
        value = st.secrets.get(section, {})
        if key is None:
            return value if value else default
        if hasattr(value, "get"):
            return value.get(key, default)
    except Exception:
        # Missing secrets.toml must never prevent .env-based startup.
        pass
    return default


def get_config_value(section: str, key: str, default: Any = None) -> Any:
    """Resolve a setting from .env/process env, then Streamlit secrets."""
    for env_name in _ENV_ALIASES.get((section, key), ()):
        value = os.getenv(env_name)
        if value is not None and value != "":
            if key in {"show_status_messages", "show_sql", "log_shipping"}:
                return value.strip().lower() not in {"0", "false", "no", "off"}
            return value
    return _streamlit_secret(section, key, default)


def get_api_key(provider: str) -> str:
    """Get a provider API key from .env, with legacy Streamlit fallback."""
    provider = provider.strip().lower()
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", "").strip() or str(_streamlit_secret("openai", "api_key", "") or "").strip()
    if provider in {"google", "gemini"}:
        return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip() or str(
            _streamlit_secret("gemini", "api_key", _streamlit_secret("google", "api_key", "")) or ""
        ).strip()
    raise ValueError(f"Unsupported API-key provider: {provider}")


def get_sqlserver_legacy_config() -> tuple[str, dict[str, Any]]:
    """Return legacy SQL Server environment/config, supporting .env defaults."""
    section = _streamlit_secret("sqlserver", default={}) or {}
    if isinstance(section, dict) and section:
        env_name = str(section.get("env", ""))
        if env_name and isinstance(section.get(env_name), dict):
            return env_name, dict(section[env_name])
    config = {
        "server": os.getenv("SQL_SERVER", ""),
        "database": os.getenv("SQL_DATABASE", ""),
        "username": os.getenv("SQL_USERNAME", ""),
        "password": os.getenv("SQL_PASSWORD", ""),
        "driver": os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server"),
        "encrypt": os.getenv("SQL_ENCRYPT", "yes").lower() in {"yes", "true", "1"},
    }
    if os.getenv("SQLSERVER_CONNECTION_STRING"):
        config["connection_string"] = os.environ["SQLSERVER_CONNECTION_STRING"]
    if not config["server"] and not config.get("connection_string"):
        raise RuntimeError("SQL Server is not configured. Set SQL_SERVER/SQL_DATABASE credentials in .env or configure it in Integration Management.")
    return "dotenv", config
