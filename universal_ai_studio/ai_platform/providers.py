"""Provider-agnostic chat interface for Google Gemini, OpenAI and Ollama.

Application modules should call this service rather than importing provider SDKs.
Provider credentials are read from encrypted platform storage or the root .env.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from universal_ai_studio.core.configuration import (
    ConfigurationError, get_integration_secret, load_platform_config,
)


class ProviderError(RuntimeError):
    """Raised for provider configuration, connectivity or generation failures."""


class ChatProvider(Protocol):
    def complete(self, prompt: str, *, model: str, temperature: float = 0.2,
                 max_tokens: int = 2048, timeout: int = 60) -> str: ...


@dataclass
class GoogleGeminiProvider:
    api_key: str

    def complete(self, prompt: str, *, model: str, temperature: float = 0.2,
                 max_tokens: int = 2048, timeout: int = 60) -> str:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key, http_options={"timeout": timeout * 1000})
            response = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens),
            )
            return str(response.text or "")
        except Exception as exc:
            raise ProviderError(f"Google Gemini request failed: {type(exc).__name__}: {exc}") from exc


@dataclass
class OpenAIProvider:
    api_key: str
    base_url: str | None = None

    def complete(self, prompt: str, *, model: str, temperature: float = 0.2,
                 max_tokens: int = 2048, timeout: int = 60) -> str:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                temperature=temperature, max_tokens=max_tokens,
            )
            return str(response.choices[0].message.content or "")
        except Exception as exc:
            raise ProviderError(f"OpenAI-compatible request failed: {type(exc).__name__}: {exc}") from exc


@dataclass
class OllamaProvider:
    base_url: str

    def complete(self, prompt: str, *, model: str, temperature: float = 0.2,
                 max_tokens: int = 2048, timeout: int = 60) -> str:
        try:
            from ollama import Client
            client = Client(host=self.base_url, timeout=timeout)
            response = client.chat(
                model=model, messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            return str(response.message.content or "")
        except Exception as exc:
            raise ProviderError(f"Ollama request failed: {type(exc).__name__}: {exc}") from exc


class ProviderManager:
    """Resolve the approved default provider and expose a common completion API."""

    ALLOWED = frozenset({"gemini", "openai", "ollama"})

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or load_platform_config()
        self.settings = self.config.get("ai_provider", {})
        self.integrations = self.config.get("integrations", {})

    def available_providers(self) -> list[str]:
        available = []
        for name in self.ALLOWED:
            section = self.integrations.get(name, {})
            if not section.get("enabled", False):
                continue
            if name == "gemini" and get_integration_secret("gemini", "api_key"):
                available.append(name)
            elif name == "openai" and get_integration_secret("openai", "api_key"):
                available.append(name)
            elif name == "ollama" and section.get("base_url"):
                available.append(name)
        return sorted(available)

    def _provider(self, name: str) -> tuple[ChatProvider, dict[str, Any]]:
        if name not in self.ALLOWED:
            raise ProviderError(f"Unsupported AI provider: {name}")
        section = self.integrations.get(name, {})
        if not section.get("enabled", False):
            raise ProviderError(f"AI provider '{name}' is disabled by the administrator.")
        if name == "gemini":
            key = get_integration_secret("gemini", "api_key")
            if not key:
                raise ProviderError("Google API key is missing. Configure GOOGLE_API_KEY in .env or AI Provider Management.")
            return GoogleGeminiProvider(key), section
        if name == "openai":
            key = get_integration_secret("openai", "api_key")
            if not key:
                raise ProviderError("OpenAI API key is missing. Configure OPENAI_API_KEY in .env or AI Provider Management.")
            return OpenAIProvider(key, section.get("base_url") or None), section
        base_url = get_integration_secret("ollama", "base_url", section.get("base_url", "http://localhost:11434"))
        return OllamaProvider(base_url), section

    def complete(self, prompt: str, *, provider: str | None = None, model: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None) -> str:
        selected = provider or self.settings.get("default_provider", "gemini")
        client, section = self._provider(selected)
        return client.complete(
            prompt, model=model or section.get("model", ""),
            temperature=float(self.settings.get("temperature", 0.2) if temperature is None else temperature),
            max_tokens=int(self.settings.get("max_tokens", 2048) if max_tokens is None else max_tokens),
            timeout=int(section.get("timeout", 60)),
        )

    def test(self, provider: str) -> tuple[bool, str]:
        try:
            output = self.complete("Reply with exactly: connection successful", provider=provider, max_tokens=32)
            return bool(output.strip()), "Provider responded successfully." if output.strip() else "Provider returned an empty response."
        except (ProviderError, ConfigurationError) as exc:
            return False, str(exc)


def get_langchain_llm():
    """Return a LangChain-compatible LLM backed by the configured provider."""
    try:
        from langchain_core.language_models.llms import LLM
    except ImportError as exc:
        raise ProviderError("langchain-core is required for this application module.") from exc

    class ProviderManagerLangChainLLM(LLM):
        provider_manager: Any

        @property
        def _llm_type(self) -> str:
            return "universal-ai-studio-provider-manager"

        @property
        def _identifying_params(self) -> dict[str, Any]:
            settings = self.provider_manager.settings
            return {"provider": settings.get("default_provider", "gemini")}

        def _call(self, prompt: str, stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> str:
            result = self.provider_manager.complete(prompt)
            if stop:
                for stop_text in stop:
                    if stop_text and stop_text in result:
                        result = result.split(stop_text, 1)[0]
            return result

    return ProviderManagerLangChainLLM(provider_manager=ProviderManager())
