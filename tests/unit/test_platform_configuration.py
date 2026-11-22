import json

import pytest
from cryptography.fernet import Fernet

from universal_ai_studio.core import configuration
from universal_ai_studio.core.feature_manager import is_feature_enabled, set_feature_enabled


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(configuration, "PLATFORM_CONFIG_PATH", tmp_path / "config" / "platform.json")
    monkeypatch.setattr(configuration, "SECRET_STORE_PATH", tmp_path / "config" / "secrets.enc")


def test_default_platform_config_contains_all_feature_flags():
    config = configuration.load_platform_config()
    assert len(config["features"]) == 18
    assert config["integrations"]["elasticsearch"]["enabled"] is True


def test_feature_flags_persist_without_touching_source_defaults(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    assert is_feature_enabled("marketing") is True
    set_feature_enabled("marketing", False)
    assert is_feature_enabled("marketing") is False
    assert json.loads(configuration.PLATFORM_CONFIG_PATH.read_text())["features"]["marketing"] is False


def test_plaintext_configuration_rejects_secret_fields(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    config = configuration.load_platform_config()
    config["integrations"]["sql_server"]["password"] = "must-not-be-saved"
    with pytest.raises(configuration.ConfigurationError, match="Secrets must be stored"):
        configuration.save_platform_config(config)


def test_integration_secrets_are_encrypted_at_rest(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("UAS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    configuration.save_integration_secret("sql_server", "password", "test-password-123")
    ciphertext = configuration.SECRET_STORE_PATH.read_bytes()
    assert b"test-password-123" not in ciphertext
    assert configuration.get_integration_secret("sql_server", "password") == "test-password-123"


def test_secret_persistence_requires_encryption_key(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.delenv("UAS_CONFIG_ENCRYPTION_KEY", raising=False)
    with pytest.raises(configuration.ConfigurationError, match="UAS_CONFIG_ENCRYPTION_KEY"):
        configuration.save_integration_secret("openai", "api_key", "secret")


def test_disabled_integration_is_removed_from_legacy_environment(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("SQL_SERVER", "legacy-host")
    config = configuration.load_platform_config()
    config["integrations"]["sql_server"].update(enabled=False)
    configuration.save_platform_config(config)
    configuration.apply_runtime_configuration()
    assert "SQL_SERVER" not in __import__("os").environ


def test_runtime_configuration_keeps_existing_env_when_no_platform_file(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("SQL_SERVER", "legacy-host")
    configuration.apply_runtime_configuration()
    assert __import__("os").environ["SQL_SERVER"] == "legacy-host"


def test_load_platform_config_migrates_retired_gemini_model(tmp_path, monkeypatch):
    import json
    from universal_ai_studio.core import configuration

    config_path = tmp_path / "platform.json"
    config_path.write_text(json.dumps({
        "integrations": {"gemini": {"enabled": True, "model": "gemini-2.0-flash"}}
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "PLATFORM_CONFIG_PATH", config_path)

    loaded = configuration.load_platform_config()
    assert loaded["integrations"]["gemini"]["model"] == "gemini-3.8-flash"


def test_load_platform_config_preserves_custom_gemini_model(tmp_path, monkeypatch):
    import json
    from universal_ai_studio.core import configuration

    config_path = tmp_path / "platform.json"
    config_path.write_text(json.dumps({
        "integrations": {"gemini": {"enabled": True, "model": "gemini-custom-model"}}
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "PLATFORM_CONFIG_PATH", config_path)

    loaded = configuration.load_platform_config()
    assert loaded["integrations"]["gemini"]["model"] == "gemini-custom-model"
