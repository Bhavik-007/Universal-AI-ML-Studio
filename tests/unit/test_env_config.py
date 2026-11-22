from __future__ import annotations

import os

from universal_ai_studio.core import env_config


def test_openai_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    assert env_config.get_api_key("openai") == "test-openai-key"


def test_google_key_accepts_google_and_gemini_names(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-google-key")
    assert env_config.get_api_key("google") == "test-google-key"


def test_environment_values_take_precedence_over_streamlit_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    monkeypatch.setattr(env_config, "_streamlit_secret", lambda *args, **kwargs: "streamlit-key")
    assert env_config.get_api_key("openai") == "environment-key"


def test_missing_streamlit_secrets_does_not_raise(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(env_config, "_streamlit_secret", lambda *args, **kwargs: "")
    assert env_config.get_api_key("openai") == ""


def test_azure_openai_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat-prod")
    assert env_config.get_config_value("openai", "api_base") == "https://example.openai.azure.com/"
    assert env_config.get_config_value("openai", "api_version") == "2024-10-21"
    assert env_config.get_config_value("openai", "deployment_name") == "chat-prod"
