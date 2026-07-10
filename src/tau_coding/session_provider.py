"""Provider and thinking helper functions extracted from session.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tau_agent.session import SessionState

from tau_coding.provider_config import (
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    provider_default_thinking_level,
    provider_thinking_levels,
    validate_provider_model,
)
from tau_coding.session_models import CodingSessionConfig
from tau_coding.thinking import ThinkingLevel, normalize_thinking_level

if TYPE_CHECKING:
    from tau_coding.session import CodingSession


def _initial_model_for_config(config: CodingSessionConfig) -> str:

    if config.provider_settings is None or config.runtime_provider_config is None:
        return config.model

    provider = _provider_config_for_name(config, config.provider_name)

    if provider is None:
        return config.model

    try:
        validate_provider_model(provider, config.model)
    except ProviderConfigError:
        return provider.default_model

    return config.model


def _runtime_model_for_state(config: CodingSessionConfig, state: SessionState) -> str:

    state_model = state.model or config.model

    if config.provider_settings is None or config.runtime_provider_config is None:
        return state_model

    provider = _provider_config_for_name(config, config.provider_name)

    if provider is None:
        return state_model

    try:
        validate_provider_model(provider, state_model)
    except ProviderConfigError:
        return config.model if config.model in provider.models else provider.default_model

    return state_model


def _initial_thinking_level_for_config(
    config: CodingSessionConfig,
    *,
    model: str,
) -> ThinkingLevel:

    provider = _provider_config_for_name(config, config.provider_name)

    if provider is None:
        return config.thinking_level

    return _preferred_thinking_level_for_model(
        provider,
        model=model,
        fallback=config.thinking_level,
    )


def _provider_config_for_name(
    config: CodingSessionConfig,
    provider_name: str,
) -> ProviderConfig | None:

    if config.provider_settings is not None:
        try:
            return config.provider_settings.get_provider(provider_name)
        except ProviderConfigError:
            pass

    if config.runtime_provider_config is not None:
        return config.runtime_provider_config

    return None


def _state_thinking_level(
    state: SessionState,
    default: ThinkingLevel,
) -> ThinkingLevel:

    thinking_level = getattr(state, "thinking_level", None)

    if thinking_level is None:
        return default

    return normalize_thinking_level(thinking_level)


def _default_thinking_level_for_active_model(session: CodingSession) -> ThinkingLevel:

    provider = session._active_provider_config()

    if provider is None:
        return session._config.thinking_level

    return _preferred_thinking_level_for_model(
        provider,
        model=session.model,
        fallback=session._config.thinking_level,
    )


def _preferred_thinking_level_for_model(
    provider: ProviderConfig,
    *,
    model: str,
    fallback: ThinkingLevel,
) -> ThinkingLevel:

    levels = provider_thinking_levels(provider, model=model)
    preferred = provider.thinking_defaults.get(model)

    if preferred in levels:
        return preferred

    if fallback in levels or not levels:
        return fallback

    default = provider_default_thinking_level(provider, model=model)

    return default or levels[0]


def _coerced_thinking_level(
    provider: ProviderConfig,
    *,
    model: str,
    current: ThinkingLevel,
    preferred: ThinkingLevel | None = None,
) -> ThinkingLevel:

    levels = provider_thinking_levels(provider, model=model)

    if not levels or current in levels:
        return current

    if preferred in levels:
        return preferred

    default = provider_default_thinking_level(provider, model=model)

    return default or levels[0]


def _unavailable_thinking_message(session: CodingSession) -> str:

    message = f"Thinking controls are unavailable for {session.provider_name}:{session.model}"

    reason = session.thinking_unavailable_reason

    if reason:
        return f"{message}: {reason}"

    return message
