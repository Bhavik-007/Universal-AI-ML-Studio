"""Persistent platform configuration with encrypted integration secrets.

Non-secret settings are stored in config/platform.json. Secrets are stored in a
separate Fernet-encrypted file and require UAS_CONFIG_ENCRYPTION_KEY from the
process environment (normally loaded from a protected .env or secret manager).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
PLATFORM_CONFIG_PATH = CONFIG_DIR / "platform.json"
SECRET_STORE_PATH = CONFIG_DIR / "secrets.enc"

DEFAULT_FEATURES: dict[str, bool] = {
    "forecast": True,
    "file_qa": True,
    "api_analyzer": True,
    "sentiment": True,
    "finance": True,
    "sql_voice": True,
    "voice_test": True,
    "purchase": True,
    "mcp": True,
    "fraud": True,
    "loan_tree": True,
    "marketing": True,
    "graphql": True,
    "agent_assist": True,
    "market_intelligence": True,
    "svm_fraud": True,
    "nlp_sql": True,
    "rag_sql": True,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "features": DEFAULT_FEATURES,
    "ai_provider": {"default_provider": "gemini", "temperature": 0.2, "max_tokens": 2048, "fallback_provider": "none"},
    "integrations": {
        "sql_server": {"enabled": False, "server": "", "database": "", "driver": "ODBC Driver 18 for SQL Server", "auth_mode": "SQL", "encrypt": "yes", "trust_server_certificate": "no"},
        "rest_api": {"enabled": False, "base_url": "", "auth_type": "none", "timeout": 20},
        "graphql": {"enabled": False, "endpoint": "", "auth_type": "none", "timeout": 20},
        "elasticsearch": {"enabled": True, "url": "http://localhost:9200", "index_prefix": "uas", "schema_index": "uas_schema_metadata", "document_index": "uas_document_chunks", "marketing_index": "marketing-documents-v1", "verify_certs": True, "timeout": 20},
        "kibana": {"enabled": True, "url": "http://localhost:5601", "timeout": 10},
        "ollama": {"enabled": True, "base_url": "http://localhost:11434", "model": "llama3.1", "timeout": 60},
        "openai": {"enabled": False, "model": "gpt-4o-mini", "timeout": 60},
        "gemini": {"enabled": False, "model": "gemini-3.8-flash", "timeout": 60},
    },
}


class ConfigurationError(RuntimeError):
    """Raised when platform configuration cannot be safely read or written."""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _default_config() -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    integrations = config["integrations"]
    integrations["sql_server"]["enabled"] = bool(os.getenv("SQL_SERVER") or os.getenv("SQLSERVER_CONNECTION_STRING"))
    integrations["rest_api"]["enabled"] = bool(os.getenv("REST_API_BASE_URL"))
    integrations["graphql"]["enabled"] = bool(os.getenv("GRAPHQL_ENDPOINT"))
    integrations["elasticsearch"]["enabled"] = bool(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"))
    integrations["kibana"]["url"] = os.getenv("KIBANA_URL", integrations["kibana"]["url"])
    integrations["kibana"]["enabled"] = bool(integrations["kibana"]["url"])
    integrations["elasticsearch"]["marketing_index"] = os.getenv("ELASTICSEARCH_MARKETING_INDEX", os.getenv("ELASTICSEARCH_INDEX", integrations["elasticsearch"]["marketing_index"]))
    integrations["ollama"]["enabled"] = bool(os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    integrations["ollama"]["base_url"] = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL", integrations["ollama"]["base_url"])
    integrations["openai"]["enabled"] = bool(os.getenv("OPENAI_API_KEY"))
    integrations["gemini"]["enabled"] = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    return config


def load_platform_config() -> dict[str, Any]:
    if not PLATFORM_CONFIG_PATH.exists():
        return _default_config()
    try:
        loaded = json.loads(PLATFORM_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError("Platform configuration is unreadable. Check config/platform.json.") from exc
    if not isinstance(loaded, dict):
        raise ConfigurationError("Platform configuration must be a JSON object.")
    merged = _default_config()
    merged.update({key: value for key, value in loaded.items() if key != "features" and key != "integrations"})
    merged["features"].update(loaded.get("features", {}))
    if isinstance(loaded.get("ai_provider"), dict):
        merged["ai_provider"].update(loaded["ai_provider"])
    for name, value in loaded.get("integrations", {}).items():
        if name in merged["integrations"] and isinstance(value, dict):
            merged["integrations"][name].update(value)
    # Gemini retired gemini-2.0-flash. Migrate only this known retired default;
    # preserve any other administrator-selected model value.
    if merged["integrations"].get("gemini", {}).get("model") == "gemini-2.0-flash":
        merged["integrations"]["gemini"]["model"] = "gemini-3.8-flash"
    return merged


def save_platform_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ConfigurationError("Platform configuration must be a dictionary.")
    # Prevent accidental persistence of credential-like values in the plaintext file.
    forbidden = {"password", "api_key", "token", "secret", "client_secret", "authorization", "connection_string", "private_key"}
    for integration in config.get("integrations", {}).values():
        if isinstance(integration, dict) and forbidden.intersection(k.lower() for k in integration):
            raise ConfigurationError("Secrets must be stored through save_secrets(), not platform.json.")
    payload = json.dumps(config, indent=2, sort_keys=True).encode("utf-8")
    _atomic_write(PLATFORM_CONFIG_PATH, payload)


def _fernet():
    key = os.getenv("UAS_CONFIG_ENCRYPTION_KEY", "").strip()
    if not key:
        raise ConfigurationError(
            "Secure secret storage is not initialized. Set UAS_CONFIG_ENCRYPTION_KEY in .env. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode("ascii"))
    except (ImportError, ValueError, UnicodeEncodeError) as exc:
        raise ConfigurationError("UAS_CONFIG_ENCRYPTION_KEY is invalid or cryptography is not installed.") from exc


def load_secrets() -> dict[str, dict[str, str]]:
    if not SECRET_STORE_PATH.exists():
        return {}
    try:
        plaintext = _fernet().decrypt(SECRET_STORE_PATH.read_bytes())
        value = json.loads(plaintext.decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        raise ConfigurationError("Encrypted secret store cannot be decrypted. Verify the encryption key and backup.") from exc


def save_secrets(secrets_data: dict[str, dict[str, str]]) -> None:
    if not isinstance(secrets_data, dict):
        raise ConfigurationError("Secrets must be provided as a dictionary.")
    encrypted = _fernet().encrypt(json.dumps(secrets_data, sort_keys=True).encode("utf-8"))
    _atomic_write(SECRET_STORE_PATH, encrypted)


def save_integration_secret(integration: str, name: str, value: str) -> None:
    secrets_data = load_secrets()
    if value:
        secrets_data.setdefault(integration, {})[name] = value
    else:
        secrets_data.setdefault(integration, {}).pop(name, None)
    save_secrets(secrets_data)


def get_integration_secret(integration: str, name: str, default: str = "") -> str:
    """Read encrypted UI credentials first, then supported .env variables."""
    stored = load_secrets().get(integration, {}).get(name)
    if stored:
        return stored
    env_names = {
        ("openai", "api_key"): ("OPENAI_API_KEY",),
        ("gemini", "api_key"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        ("ollama", "base_url"): ("OLLAMA_BASE_URL", "OLLAMA_URL"),
    }
    for env_name in env_names.get((integration, name), ()):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return default


def apply_runtime_configuration() -> None:
    """Expose configured integration values to legacy modules through process env.

    If no platform configuration has been saved, existing .env configuration is
    left untouched. Once the administrator saves platform settings, disabled
    integrations are removed from the process environment so legacy modules do
    not continue using a connection that has been disabled in the UI.
    """
    if not PLATFORM_CONFIG_PATH.exists():
        return
    config = load_platform_config()
    secrets_data = load_secrets() if SECRET_STORE_PATH.exists() else {}
    mapping = {
        "sql_server": {"server": "SQL_SERVER", "database": "SQL_DATABASE", "driver": "SQL_DRIVER", "auth_mode": "SQL_AUTH_MODE", "encrypt": "SQL_ENCRYPT", "trust_server_certificate": "SQL_TRUST_SERVER_CERTIFICATE", "connection_string": "SQLSERVER_CONNECTION_STRING"},
        "rest_api": {"base_url": "REST_API_BASE_URL"},
        "graphql": {"endpoint": "GRAPHQL_ENDPOINT"},
        "elasticsearch": {"url": "ELASTICSEARCH_URL", "index_prefix": "ELASTICSEARCH_INDEX_PREFIX", "schema_index": "ELASTICSEARCH_SCHEMA_INDEX", "document_index": "ELASTICSEARCH_DOCUMENT_INDEX", "marketing_index": "ELASTICSEARCH_MARKETING_INDEX", "verify_certs": "ELASTICSEARCH_VERIFY_CERTS", "timeout": "ELASTICSEARCH_TIMEOUT_SECONDS"},
        "ollama": {"base_url": "OLLAMA_URL", "model": "OLLAMA_MODEL", "timeout": "OLLAMA_TIMEOUT_SECONDS"},
        "openai": {"model": "OPENAI_MODEL"},
        "gemini": {"model": "GEMINI_MODEL"},
    }
    secret_env = {
        ("sql_server", "username"): "SQL_USERNAME", ("sql_server", "password"): "SQL_PASSWORD",
        ("rest_api", "api_key"): "REST_API_KEY", ("rest_api", "bearer_token"): "REST_API_BEARER_TOKEN",
        ("graphql", "api_key"): "GRAPHQL_API_KEY", ("graphql", "bearer_token"): "GRAPHQL_BEARER_TOKEN",
        ("elasticsearch", "api_key"): "ELASTICSEARCH_API_KEY", ("elasticsearch", "username"): "ELASTICSEARCH_USERNAME", ("elasticsearch", "password"): "ELASTICSEARCH_PASSWORD",
        ("openai", "api_key"): "OPENAI_API_KEY", ("gemini", "api_key"): "GEMINI_API_KEY",
    }
    for integration, fields in mapping.items():
        section = config.get("integrations", {}).get(integration, {})
        if not section.get("enabled", False):
            for env_name in fields.values():
                os.environ.pop(env_name, None)
            if integration == "sql_server":
                os.environ.pop("SQL_TRUSTED_CONNECTION", None)
            if integration == "ollama":
                os.environ.pop("OLLAMA_BASE_URL", None)
                os.environ["USE_OLLAMA"] = "false"
            continue
        for field, env_name in fields.items():
            value = section.get(field)
            if value is not None and str(value) != "":
                os.environ[env_name] = str(value).lower() if isinstance(value, bool) else str(value)
        if integration == "sql_server":
            os.environ["SQL_TRUSTED_CONNECTION"] = "yes" if section.get("auth_mode", "SQL").upper() == "WINDOWS" else "no"
        if integration == "ollama":
            if section.get("base_url"):
                os.environ["OLLAMA_BASE_URL"] = str(section["base_url"])
            os.environ["USE_OLLAMA"] = "true"
    for (integration, field), env_name in secret_env.items():
        section = config.get("integrations", {}).get(integration, {})
        value = secrets_data.get(integration, {}).get(field)
        if not section.get("enabled", False):
            os.environ.pop(env_name, None)
        elif value:
            os.environ[env_name] = value
            if integration == "gemini" and field == "api_key":
                os.environ["GOOGLE_API_KEY"] = value
        if integration == "gemini" and not section.get("enabled", False):
            os.environ.pop("GOOGLE_API_KEY", None)
    # Settings are cached by the shared settings accessor; clear it so UI changes
    # become visible on the next Streamlit rerun without restarting the process.
    try:
        from universal_ai_studio.config.settings import get_settings
        get_settings.cache_clear()
    except ImportError:
        pass
