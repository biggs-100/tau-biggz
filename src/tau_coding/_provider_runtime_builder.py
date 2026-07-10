"""Runtime provider config builders — convert durable settings to tau_ai config objects."""

from __future__ import annotations

from os import environ
from typing import Any

from tau_ai import (
    AnthropicConfig,
    OpenAICompatibleConfig,
)
from tau_coding.provider_catalog import ProviderKind
from tau_coding.provider_config import (
    DEFAULT_PROVIDER_NAME,
    AnthropicProviderConfig,
    CredentialReader,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderModelMetadata,
    _metadata_for_model,
    _model_base_url,
    _model_compat,
    _model_headers,
    _model_max_tokens,
    _provider_api,
    provider_thinking_levels,
)
from tau_coding.thinking import (
    ThinkingLevel,
    anthropic_thinking_budget_for_level,
    normalize_thinking_level,
    reasoning_effort_for_level,
)


def openai_compatible_config_from_provider(
    provider: OpenAICompatibleProviderConfig,
    *,
    credential_reader: CredentialReader | None = None,
    model: str | None = None,
    thinking_level: ThinkingLevel | None = None,
) -> OpenAICompatibleConfig:
    """Build OpenAI-compatible runtime config from durable settings."""
    api_key = _api_key_from_provider(provider, credential_reader=credential_reader)
    selected_model = model or provider.default_model
    base_url = _model_base_url(provider, selected_model)
    if provider.name == DEFAULT_PROVIDER_NAME and provider.api_key_env == "OPENAI_API_KEY":
        base_url = environ.get("OPENAI_BASE_URL", base_url)
    reasoning_effort = _reasoning_effort_from_provider(
        provider,
        model=selected_model,
        thinking_level=thinking_level,
    )
    compat = _model_compat(provider, selected_model)
    return OpenAICompatibleConfig(
        api_key=api_key,
        provider_name=provider.name,
        api=str(_provider_api(provider, selected_model)),
        base_url=base_url.rstrip("/"),
        headers=_model_headers(provider, selected_model),
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        max_retry_delay_seconds=provider.max_retry_delay_seconds,
        reasoning_effort=reasoning_effort,
        reasoning_effort_parameter=provider.thinking_parameter or "reasoning_effort",
        thinking_format=_thinking_format(provider, selected_model),
        compat=compat,
        include_reasoning_effort_none=_include_reasoning_effort_none(
            provider,
            model=selected_model,
            thinking_level=thinking_level,
        ),
    )


def anthropic_config_from_provider(
    provider: AnthropicProviderConfig,
    *,
    credential_reader: CredentialReader | None = None,
    model: str | None = None,
    thinking_level: ThinkingLevel | None = None,
) -> AnthropicConfig:
    """Build Anthropic runtime config from durable settings."""
    api_key = _api_key_from_provider(provider, credential_reader=credential_reader)
    selected_model = model or provider.default_model
    thinking_budget_tokens = _anthropic_thinking_budget_from_provider(
        provider,
        model=selected_model,
        thinking_level=thinking_level,
    )
    return AnthropicConfig(
        api_key=api_key,
        provider_name=provider.name,
        base_url=_normalize_anthropic_base_url(_model_base_url(provider, selected_model)),
        headers=_model_headers(provider, selected_model),
        bearer_auth=provider.compat.get("bearer_auth", False),
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        max_retry_delay_seconds=provider.max_retry_delay_seconds,
        thinking_budget_tokens=thinking_budget_tokens,
        thinking_effort=_reasoning_effort_from_anthropic_provider(
            provider,
            model=selected_model,
            thinking_level=thinking_level,
        ),
        thinking_mode=_anthropic_thinking_mode(provider, selected_model),
    )


def _api_key_from_provider(
    provider: ProviderConfig,
    *,
    credential_reader: CredentialReader | None,
) -> str:
    if provider.credential_name and credential_reader is not None:
        credential = credential_reader.get(provider.credential_name)
        if credential:
            return credential

    api_key = environ.get(provider.api_key_env)
    if api_key:
        return api_key
    credential_hint = f" or run /login {provider.name}" if provider.credential_name else ""
    raise RuntimeError(f"Missing provider API key. Set {provider.api_key_env}{credential_hint}.")


def _reasoning_effort_from_provider(
    provider: OpenAICompatibleProviderConfig,
    *,
    model: str | None,
    thinking_level: ThinkingLevel | None,
) -> str | None:
    if thinking_level is None or provider.thinking_parameter not in {
        "reasoning_effort",
        "reasoning.effort",
    }:
        return None

    levels = provider_thinking_levels(provider, model=model)
    if not levels:
        return None

    selected_model = model or provider.default_model
    normalized = normalize_thinking_level(thinking_level)
    if normalized not in levels:
        available = ", ".join(levels)
        raise ProviderConfigError(
            f"Thinking mode {normalized} is not available for "
            f"{provider.name}:{selected_model}. Available modes: {available}"
        )
    mapped = _metadata_thinking_value(provider, selected_model, normalized)
    if mapped is not None:
        return mapped
    if provider.name == "huggingface" and normalized == "minimal":
        # Hugging Face's router currently accepts low/medium/high/xhigh/max/none
        # for reasoning_effort, but rejects Pi/Tau's "minimal" label.
        return "low"
    return reasoning_effort_for_level(normalized)


def _anthropic_thinking_budget_from_provider(
    provider: AnthropicProviderConfig,
    *,
    model: str | None,
    thinking_level: ThinkingLevel | None,
) -> int | None:
    if thinking_level is None or provider.thinking_parameter != "anthropic.thinking":
        return None

    selected_model = model or provider.default_model
    if _anthropic_thinking_mode(provider, selected_model) == "adaptive":
        return None

    levels = provider_thinking_levels(provider, model=selected_model)
    if not levels:
        return None

    normalized = normalize_thinking_level(thinking_level)
    if normalized not in levels:
        available = ", ".join(levels)
        raise ProviderConfigError(
            f"Thinking mode {normalized} is not available for "
            f"{provider.name}:{selected_model}. Available modes: {available}"
        )
    return anthropic_thinking_budget_for_level(normalized)


def _metadata_thinking_value(
    provider: ProviderConfig,
    model: str,
    level: ThinkingLevel,
) -> str | None:
    metadata = _metadata_for_model(provider, model)
    if metadata is None:
        return None
    value = metadata.thinking_level_map.get(level)
    return value if isinstance(value, str) else None


def _thinking_format(provider: ProviderConfig, model: str) -> str:
    compat = _model_compat(provider, model)
    value = compat.get("thinkingFormat")
    if isinstance(value, str) and value:
        return value
    base_url = _model_base_url(provider, model)
    if provider.name == "deepseek" or "deepseek.com" in base_url:
        return "deepseek"
    if provider.name == "zai" or "api.z.ai" in base_url:
        return "zai"
    if provider.name == "together" or "api.together.ai" in base_url:
        return "together"
    if provider.name == "openrouter" or "openrouter.ai" in base_url:
        return "openrouter"
    return "openai"


def _include_reasoning_effort_none(
    provider: ProviderConfig,
    *,
    model: str,
    thinking_level: ThinkingLevel | None,
) -> bool:
    if thinking_level is None:
        return False
    try:
        normalized = normalize_thinking_level(thinking_level)
    except ValueError:
        return False
    if normalized != "off":
        return False
    return _metadata_thinking_value(provider, model, "off") == "none"


def _reasoning_effort_from_anthropic_provider(
    provider: AnthropicProviderConfig,
    *,
    model: str,
    thinking_level: ThinkingLevel | None,
) -> str | None:
    if thinking_level is None:
        return None
    selected_model = model
    normalized = normalize_thinking_level(thinking_level)
    if normalized == "off":
        return None
    mapped = _metadata_thinking_value(provider, selected_model, normalized)
    return mapped or normalized


def _anthropic_thinking_mode(provider: AnthropicProviderConfig, model: str) -> str:
    compat = _model_compat(provider, model)
    if compat.get("forceAdaptiveThinking") is True:
        return "adaptive"
    return "budget"


def _normalize_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"
