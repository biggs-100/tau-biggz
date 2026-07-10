"""Provider settings deserialization functions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tau_ai import (
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
)
from tau_coding.paths import TauPaths
from tau_coding.provider_config import (
    _default_api_for_kind,
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    ScopedModelConfig,
    provider_thinking_levels,
    validate_provider_model,
)
from tau_coding._provider_parsers import (
    _context_window_dict,
    _json_dict,
    _model_metadata_dict,
    _non_negative_float,
    _non_negative_int,
    _optional_provider_api,
    _optional_string,
    _optional_string_tuple,
    _optional_thinking_level,
    _optional_thinking_levels,
    _optional_thinking_parameter,
    _positive_float,
    _reject_catalog_only_legacy_metadata,
    _string,
    _string_dict,
    _string_tuple,
)
from tau_coding._provider_merge import _effective_provider_configs
from tau_coding.thinking import ThinkingLevel


def provider_settings_from_json(
    data: dict[str, Any],
    *,
    paths: TauPaths | None = None,
) -> ProviderSettings:
    """Parse provider preferences from JSON-compatible data.

    The current providers.json shape stores runtime preferences under
    provider_preferences. The older providers[] shape is still accepted for
    migration and compatibility; saves rewrite it to provider_preferences and
    move custom provider definitions to catalog.toml.
    """
    default_provider = _string(data.get("default_provider"), "default_provider")
    scoped_models = _scoped_models_from_json(data.get("scoped_models"))
    if "provider_preferences" in data:
        providers = _providers_with_preferences(
            data.get("provider_preferences"),
            paths=paths,
        )
        return ProviderSettings(
            default_provider=default_provider,
            providers=providers,
            scoped_models=scoped_models,
        )

    providers_data = data.get("providers")
    if not isinstance(providers_data, list) or not providers_data:
        raise ProviderConfigError(
            "Provider settings must include provider_preferences or legacy providers"
        )
    providers = tuple(_provider_from_json(item) for item in providers_data)
    names = [provider.name for provider in providers]
    if len(set(names)) != len(names):
        raise ProviderConfigError("Provider names must be unique")
    return ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=scoped_models,
    )


def _providers_with_preferences(
    value: object,
    *,
    paths: TauPaths | None,
) -> tuple[ProviderConfig, ...]:
    if not isinstance(value, dict):
        raise ProviderConfigError("Provider settings field must be an object: provider_preferences")
    catalog_configs = {provider.name: provider for provider in _effective_provider_configs(paths)}
    providers = []
    seen: set[str] = set()
    for name, preference_data in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ProviderConfigError("Provider preference names must be non-empty strings")
        provider_name = name.strip()
        if provider_name in seen:
            raise ProviderConfigError("Provider preference names must be unique")
        if provider_name not in catalog_configs:
            raise ProviderConfigError(f"Unknown provider preference: {provider_name}")
        providers.append(
            _apply_provider_preference(
                catalog_configs[provider_name],
                preference_data,
            )
        )
        seen.add(provider_name)
    return tuple(providers)


def _apply_provider_preference(
    provider: ProviderConfig,
    value: object,
) -> ProviderConfig:
    if not isinstance(value, dict):
        raise ProviderConfigError("Provider preference entries must be objects")
    allowed = {
        "default_model",
        "headers",
        "timeout_seconds",
        "max_retries",
        "max_retry_delay_seconds",
        "thinking_defaults",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProviderConfigError(
            f"Unknown provider preference fields for {provider.name}: {', '.join(unknown)}"
        )
    default_model = (
        _string(value.get("default_model"), f"provider_preferences.{provider.name}.default_model")
        if "default_model" in value
        else provider.default_model
    )
    models = (
        provider.models if default_model in provider.models else (*provider.models, default_model)
    )
    headers = (
        _string_dict(value.get("headers"), f"provider_preferences.{provider.name}.headers")
        if "headers" in value
        else provider.headers
    )
    timeout_seconds = (
        _positive_float(
            value.get("timeout_seconds"),
            f"provider_preferences.{provider.name}.timeout_seconds",
        )
        if "timeout_seconds" in value
        else provider.timeout_seconds
    )
    max_retries = (
        _non_negative_int(
            value.get("max_retries"),
            f"provider_preferences.{provider.name}.max_retries",
        )
        if "max_retries" in value
        else provider.max_retries
    )
    max_retry_delay_seconds = (
        _non_negative_float(
            value.get("max_retry_delay_seconds"),
            f"provider_preferences.{provider.name}.max_retry_delay_seconds",
        )
        if "max_retry_delay_seconds" in value
        else provider.max_retry_delay_seconds
    )
    thinking_defaults = (
        _thinking_defaults_dict(
            value.get("thinking_defaults"),
            provider,
            f"provider_preferences.{provider.name}.thinking_defaults",
        )
        if "thinking_defaults" in value
        else provider.thinking_defaults
    )
    return replace(
        provider,
        models=models,
        default_model=default_model,
        headers=headers,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
        thinking_defaults=thinking_defaults,
    )


def _thinking_defaults_dict(
    value: object,
    provider: ProviderConfig,
    field_name: str,
) -> dict[str, ThinkingLevel]:
    raw = _raw_thinking_defaults_dict(value, field_name)
    for model, thinking_level in raw.items():
        validate_provider_model(provider, model)
        available = provider_thinking_levels(provider, model=model)
        if thinking_level not in available:
            modes = ", ".join(available) or "none"
            raise ProviderConfigError(
                f"Provider thinking default {thinking_level} is not available for "
                f"{provider.name}:{model}. Available modes: {modes}"
            )
    return raw


def _raw_thinking_defaults_dict(value: object, field_name: str) -> dict[str, ThinkingLevel]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a thinking mode object: {field_name}")
    defaults: dict[str, ThinkingLevel] = {}
    for key, item in value.items():
        model = _string(key, field_name)
        thinking_level = _optional_thinking_level(item, f"{field_name}.{model}")
        if thinking_level is None:
            raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
        defaults[model] = thinking_level
    return defaults


def _scoped_models_from_json(value: object) -> tuple[ScopedModelConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderConfigError("Provider settings field must be a list: scoped_models")
    scoped: list[ScopedModelConfig] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ProviderConfigError("Provider scoped_models entries must be objects")
        provider = _string(item.get("provider"), "scoped_models.provider")
        model = _string(item.get("model"), "scoped_models.model")
        key = (provider, model)
        if key not in seen:
            scoped.append(ScopedModelConfig(provider=provider, model=model))
            seen.add(key)
    return tuple(scoped)


def _provider_from_json(data: object) -> ProviderConfig:
    if not isinstance(data, dict):
        raise ProviderConfigError("Provider entries must be JSON objects")
    provider_type = _string(data.get("type"), "providers[].type")
    if provider_type not in {
        "openai-compatible",
        "anthropic",
        "openai-codex",
        "google-generative-ai",
        "mistral-conversations",
    }:
        raise ProviderConfigError(f"Unsupported provider type: {provider_type}")
    name = _string(data.get("name"), "providers[].name")
    base_url = _string(data.get("base_url"), f"providers[{name}].base_url").rstrip("/")
    api = _optional_provider_api(data.get("api"), f"providers[{name}].api")
    api_key_env = _string(data.get("api_key_env"), f"providers[{name}].api_key_env")
    credential_name = _optional_string(
        data.get("credential_name"), f"providers[{name}].credential_name"
    )
    models = _string_tuple(data.get("models"), f"providers[{name}].models")
    default_model = _string(data.get("default_model"), f"providers[{name}].default_model")
    context_windows = _context_window_dict(
        data.get("context_windows", {}), f"providers[{name}].context_windows"
    )
    headers = _string_dict(data.get("headers", {}), f"providers[{name}].headers")
    compat = _json_dict(data.get("compat", {}), f"providers[{name}].compat")
    model_metadata = _model_metadata_dict(
        data.get("model_metadata", {}),
        models,
        f"providers[{name}].model_metadata",
    )
    timeout_seconds = _positive_float(
        data.get("timeout_seconds", DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS),
        f"providers[{name}].timeout_seconds",
    )
    max_retries = _non_negative_int(
        data.get("max_retries", DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES),
        f"providers[{name}].max_retries",
    )
    max_retry_delay_seconds = _non_negative_float(
        data.get(
            "max_retry_delay_seconds",
            DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
        ),
        f"providers[{name}].max_retry_delay_seconds",
    )
    thinking_levels = _optional_thinking_levels(
        data.get("thinking_levels"), f"providers[{name}].thinking_levels"
    )
    thinking_models = _optional_string_tuple(
        data.get("thinking_models"), f"providers[{name}].thinking_models"
    )
    thinking_default = _optional_thinking_level(
        data.get("thinking_default"), f"providers[{name}].thinking_default"
    )
    thinking_parameter = _optional_thinking_parameter(
        data.get("thinking_parameter"), f"providers[{name}].thinking_parameter"
    )
    thinking_defaults = _raw_thinking_defaults_dict(
        data.get("thinking_defaults", {}), f"providers[{name}].thinking_defaults"
    )
    if default_model not in models:
        models = (*models, default_model)
    if provider_type == "anthropic":
        return AnthropicProviderConfig(
            name=name,
            base_url=base_url,
            api=api or "anthropic-messages",
            api_key_env=api_key_env,
            credential_name=credential_name,
            models=models,
            default_model=default_model,
            context_windows=context_windows,
            headers=headers,
            compat=compat,
            model_metadata=model_metadata,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
            thinking_levels=thinking_levels,
            thinking_models=thinking_models,
            thinking_default=thinking_default,
            thinking_parameter=thinking_parameter,
            thinking_defaults=thinking_defaults,
        )
    if provider_type == "openai-codex":
        _reject_catalog_only_legacy_metadata(compat, model_metadata)
        return OpenAICodexProviderConfig(
            name=name,
            base_url=base_url,
            api_key_env=api_key_env,
            credential_name=credential_name,
            models=models,
            default_model=default_model,
            context_windows=context_windows,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
            thinking_levels=thinking_levels,
            thinking_models=thinking_models,
            thinking_default=thinking_default,
            thinking_parameter=thinking_parameter,
            thinking_defaults=thinking_defaults,
        )
    return OpenAICompatibleProviderConfig(
        name=name,
        base_url=base_url,
        api=api or _default_api_for_kind(provider_type),
        api_key_env=api_key_env,
        credential_name=credential_name,
        models=models,
        default_model=default_model,
        context_windows=context_windows,
        headers=headers,
        compat=compat,
        model_metadata=model_metadata,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
        thinking_levels=thinking_levels,
        thinking_models=thinking_models,
        thinking_default=thinking_default,
        thinking_parameter=thinking_parameter,
        thinking_defaults=thinking_defaults,
    )
