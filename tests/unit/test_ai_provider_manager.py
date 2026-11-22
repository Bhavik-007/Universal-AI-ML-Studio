from universal_ai_studio.ai_platform.providers import ProviderError, ProviderManager


def _config(provider="gemini", enabled=True):
    return {
        "ai_provider": {"default_provider": provider, "temperature": 0.2, "max_tokens": 256},
        "integrations": {
            "gemini": {"enabled": enabled, "model": "gemini-test", "timeout": 10},
            "openai": {"enabled": False, "model": "gpt-test", "timeout": 10},
            "ollama": {"enabled": False, "model": "llama-test", "base_url": "http://localhost:11434", "timeout": 10},
        },
    }


def test_provider_manager_rejects_unknown_provider():
    manager = ProviderManager(_config())
    try:
        manager.complete("hello", provider="unknown")
    except ProviderError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Unknown provider should be rejected")


def test_provider_manager_rejects_disabled_provider():
    manager = ProviderManager(_config(enabled=False))
    try:
        manager.complete("hello", provider="gemini")
    except ProviderError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Disabled provider should be rejected")


def test_provider_manager_supports_only_approved_provider_names():
    assert ProviderManager.ALLOWED == frozenset({"gemini", "openai", "ollama"})
