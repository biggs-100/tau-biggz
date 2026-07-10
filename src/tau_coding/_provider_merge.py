"""Provider merge, catalog sync, and upsert functions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tau_coding.catalog_loader import (
    CatalogError,
    effective_catalog,
    save_user_catalog_entries,
)
from tau_coding.credentials import FileCredentialStore, credentials_path
from tau_coding.paths import TauPaths
from tau_coding.provider_catalog import (
    BUILTIN_PROVIDER_CATALOG,
    ModelCatalogMetadata,
    ProviderCatalogEntry,
)
from tau_coding.provider_config import (
    DEFAULT_PROVIDER_NAME,
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
    provider_config_from_entry,
    provider_has_usable_credentials,
    provider_kind,
)





def upsert_openai_compatible_provider(
    settings: ProviderSettings,
    provider: OpenAICompatibleProviderConfig,
    *,
    set_default: bool = False,
) -> ProviderSettings:
    """Return settings with an OpenAI-compatible provider added or replaced."""
    return upsert_provider(settings, provider, set_default=set_default)


def upsert_provider(
    settings: ProviderSettings,
    provider: ProviderConfig,
    *,
    set_default: bool = False,
) -> ProviderSettings:
    """Return settings with a provider added or replaced."""
    providers_by_name = {item.name: item for item in settings.providers}
    builtin_names = {entry.name for entry in BUILTIN_PROVIDER_CATALOG}
    if provider.name in providers_by_name and provider.name in builtin_names:
        provider = _merge_provider_config(providers_by_name[provider.name], provider)
    providers_by_name[provider.name] = provider
    default_provider = provider.name if set_default else settings.default_provider
    providers = tuple(providers_by_name[name] for name in sorted(providers_by_name))
    updated = ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=settings.scoped_models,
    )
    updated.get_provider(default_provider)
    return updated


def _with_builtin_catalog_models(
    settings: ProviderSettings,
    *,
    paths: TauPaths | None = None,
) -> ProviderSettings:
    """Return settings with the current provider catalog merged in."""
    catalog_configs = {config.name: config for config in _effective_provider_configs(paths)}
    providers = tuple(
        _merge_provider_config(provider, catalog_configs[provider.name])
        if provider.name in catalog_configs
        else provider
        for provider in settings.providers
    )
    providers = _append_catalog_providers(providers, catalog_configs, paths=paths)
    default_provider = settings.default_provider
    if default_provider not in {provider.name for provider in providers}:
        default_provider = providers[0].name if providers else DEFAULT_PROVIDER_NAME
    return ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=settings.scoped_models,
    )


def _effective_provider_configs(paths: TauPaths | None = None) -> tuple[ProviderConfig, ...]:
    """Return provider configs for the effective catalog (builtin + user overlay)."""
    try:
        return tuple(provider_config_from_entry(entry) for entry in effective_catalog(paths))
    except CatalogError:
        import sys
        from tau_coding.catalog_loader import user_catalog_path

        path = user_catalog_path(paths)
        if path.exists():
            import traceback

            sys.stderr.write(f"Warning: ignoring invalid user catalog at {path}\n")
            traceback.print_exc(file=sys.stderr)
        return tuple(
            provider_config_from_entry(entry) for entry in BUILTIN_PROVIDER_CATALOG
        )


def _append_catalog_providers(
    providers: tuple[ProviderConfig, ...],
    catalog_configs: dict[str, ProviderConfig],
    *,
    paths: TauPaths | None,
) -> tuple[ProviderConfig, ...]:
    """Append catalog providers: user-catalog ones always, builtins when credentialed."""
    credential_store = FileCredentialStore(credentials_path(paths) if paths else None)
    builtin_names = {entry.name for entry in BUILTIN_PROVIDER_CATALOG}
    provider_names = {provider.name for provider in providers}
    appended = list(providers)
    for provider in catalog_configs.values():
        if provider.name in provider_names:
            continue
        if provider.name not in builtin_names or provider_has_usable_credentials(
            provider, credential_reader=credential_store
        ):
            appended.append(provider)
            provider_names.add(provider.name)
    return tuple(appended)


def _merge_provider_config(existing: ProviderConfig, incoming: ProviderConfig) -> ProviderConfig:
    """Merge a replacement provider config without losing local customizations."""
    if type(existing) is not type(incoming):
        return incoming

    if isinstance(existing, OpenAICodexProviderConfig) and isinstance(
        incoming, OpenAICodexProviderConfig
    ):
        return replace(
            incoming,
            default_model=(
                existing.default_model
                if existing.default_model in incoming.models
                else incoming.default_model
            ),
            headers={**incoming.headers, **existing.headers},
            timeout_seconds=existing.timeout_seconds,
            max_retries=existing.max_retries,
            max_retry_delay_seconds=existing.max_retry_delay_seconds,
            context_windows={**incoming.context_windows, **existing.context_windows},
            thinking_levels=(
                existing.thinking_levels
                if existing.thinking_levels is not None
                else incoming.thinking_levels
            ),
            thinking_models=(
                existing.thinking_models
                if existing.thinking_levels is not None
                else incoming.thinking_models
            ),
            thinking_default=(
                existing.thinking_default
                if existing.thinking_levels is not None
                else incoming.thinking_default
            ),
            thinking_parameter=(
                existing.thinking_parameter
                if existing.thinking_levels is not None
                else incoming.thinking_parameter
            ),
            thinking_defaults=existing.thinking_defaults,
        )

    if isinstance(existing, OpenAICompatibleProviderConfig) and isinstance(
        incoming, OpenAICompatibleProviderConfig
    ):
        return _merge_openai_compatible_provider(existing, incoming)

    if isinstance(existing, AnthropicProviderConfig) and isinstance(
        incoming, AnthropicProviderConfig
    ):
        return _merge_anthropic_provider(existing, incoming)

    return incoming


def _merge_openai_compatible_provider(
    existing: OpenAICompatibleProviderConfig,
    incoming: OpenAICompatibleProviderConfig,
) -> OpenAICompatibleProviderConfig:
    models = _unique_strings((*incoming.models, *existing.models))
    return replace(
        incoming,
        models=models,
        default_model=(
            existing.default_model if existing.default_model in models else incoming.default_model
        ),
        headers={**incoming.headers, **existing.headers},
        compat={**incoming.compat, **existing.compat},
        model_metadata=_merge_provider_model_metadata(
            incoming.model_metadata,
            existing.model_metadata,
        ),
        timeout_seconds=existing.timeout_seconds,
        max_retries=existing.max_retries,
        max_retry_delay_seconds=existing.max_retry_delay_seconds,
        context_windows={**incoming.context_windows, **existing.context_windows},
        thinking_levels=(
            existing.thinking_levels
            if existing.thinking_levels is not None
            else incoming.thinking_levels
        ),
        thinking_models=(
            existing.thinking_models
            if existing.thinking_levels is not None
            else incoming.thinking_models
        ),
        thinking_default=(
            existing.thinking_default
            if existing.thinking_levels is not None
            else incoming.thinking_default
        ),
        thinking_parameter=(
            existing.thinking_parameter
            if existing.thinking_levels is not None
            else incoming.thinking_parameter
        ),
        thinking_defaults=existing.thinking_defaults,
    )


def _merge_anthropic_provider(
    existing: AnthropicProviderConfig,
    incoming: AnthropicProviderConfig,
) -> AnthropicProviderConfig:
    models = _unique_strings((*incoming.models, *existing.models))
    return replace(
        incoming,
        models=models,
        default_model=(
            existing.default_model if existing.default_model in models else incoming.default_model
        ),
        headers={**incoming.headers, **existing.headers},
        compat={**incoming.compat, **existing.compat},
        model_metadata=_merge_provider_model_metadata(
            incoming.model_metadata,
            existing.model_metadata,
        ),
        timeout_seconds=existing.timeout_seconds,
        max_retries=existing.max_retries,
        max_retry_delay_seconds=existing.max_retry_delay_seconds,
        context_windows={**incoming.context_windows, **existing.context_windows},
        thinking_levels=(
            existing.thinking_levels
            if existing.thinking_levels is not None
            else incoming.thinking_levels
        ),
        thinking_models=(
            existing.thinking_models
            if existing.thinking_levels is not None
            else incoming.thinking_models
        ),
        thinking_default=(
            existing.thinking_default
            if existing.thinking_levels is not None
            else incoming.thinking_default
        ),
        thinking_parameter=(
            existing.thinking_parameter
            if existing.thinking_levels is not None
            else incoming.thinking_parameter
        ),
        thinking_defaults=existing.thinking_defaults,
    )


def _merge_provider_model_metadata(
    incoming: dict[str, ProviderModelMetadata],
    existing: dict[str, ProviderModelMetadata],
) -> dict[str, ProviderModelMetadata]:
    merged = dict(incoming)
    for model, metadata in existing.items():
        if model not in merged:
            merged[model] = metadata
            continue
        base = merged[model]
        merged[model] = replace(
            base,
            name=metadata.name or base.name,
            api=metadata.api or base.api,
            base_url=metadata.base_url or base.base_url,
            reasoning=metadata.reasoning if metadata.reasoning is not None else base.reasoning,
            input=metadata.input or base.input,
            cost={**base.cost, **metadata.cost},
            context_window=metadata.context_window or base.context_window,
            max_tokens=metadata.max_tokens or base.max_tokens,
            headers={**base.headers, **metadata.headers},
            compat={**base.compat, **metadata.compat},
            thinking_level_map={**base.thinking_level_map, **metadata.thinking_level_map},
        )
    return merged


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return values with duplicates removed while preserving order."""
    return tuple(dict.fromkeys(values))


def _provider_preference_to_json(provider: ProviderConfig) -> dict[str, Any]:
    """Serialize only runtime preferences for one provider."""
    return {
        "default_model": provider.default_model,
        "headers": dict(provider.headers),
        "timeout_seconds": provider.timeout_seconds,
        "max_retries": provider.max_retries,
        "max_retry_delay_seconds": provider.max_retry_delay_seconds,
        "thinking_defaults": dict(provider.thinking_defaults),
    }


def _save_provider_definitions_to_catalog(
    settings: ProviderSettings,
    *,
    paths: TauPaths | None,
) -> None:
    """Persist provider definitions that are not already represented by the catalog."""
    catalog_by_name = {entry.name: entry for entry in effective_catalog(paths)}
    entries_to_save = []
    for provider in settings.providers:
        entry = catalog_by_name.get(provider.name)
        if entry is None or _provider_definition_differs_from_catalog(provider, entry):
            entries_to_save.append(_catalog_entry_from_provider(provider, existing=entry))
    if entries_to_save:
        save_user_catalog_entries(entries_to_save, paths=paths)


def _provider_definition_differs_from_catalog(
    provider: ProviderConfig,
    entry: ProviderCatalogEntry,
) -> bool:
    """Return whether provider metadata changed enough to belong in catalog.toml."""
    if provider_kind(provider) != entry.kind:
        return True
    if provider.base_url != entry.base_url:
        return True
    if provider.api_key_env != entry.api_key_env:
        return True
    if provider.credential_name != entry.credential_name:
        return True
    if provider.models != entry.models:
        return True
    if getattr(provider, "api", None) != entry.api and entry.api is not None:
        return True
    if provider.context_windows != dict(entry.context_windows or {}):
        return True
    if provider.headers != dict(entry.headers):
        return True
    if getattr(provider, "compat", {}) != dict(entry.compat):
        return True
    if _catalog_model_metadata_from_provider(provider) != entry.model_metadata:
        return True
    if provider.thinking_levels != entry.thinking_levels:
        return True
    if provider.thinking_models != entry.thinking_models:
        return True
    if provider.thinking_default != entry.thinking_default:
        return True
    return provider.thinking_parameter != entry.thinking_parameter


def _catalog_entry_from_provider(
    provider: ProviderConfig,
    *,
    existing: ProviderCatalogEntry | None = None,
) -> ProviderCatalogEntry:
    """Create catalog metadata from a runtime provider config."""
    return ProviderCatalogEntry(
        name=provider.name,
        display_name=existing.display_name if existing is not None else provider.name,
        kind=provider_kind(provider),
        base_url=provider.base_url,
        api_key_env=provider.api_key_env,
        api=getattr(provider, "api", None),
        credential_name=provider.credential_name,
        models=provider.models,
        default_model=(
            existing.default_model
            if existing is not None and existing.default_model in provider.models
            else provider.default_model
        ),
        docs_url=existing.docs_url if existing is not None else provider.base_url,
        context_windows=dict(provider.context_windows) or None,
        headers=dict(provider.headers),
        compat=dict(getattr(provider, "compat", {})),
        model_metadata=_catalog_model_metadata_from_provider(provider),
        thinking_levels=provider.thinking_levels,
        thinking_models=provider.thinking_models,
        thinking_default=provider.thinking_default,
        thinking_parameter=provider.thinking_parameter,
    )


def _catalog_model_metadata_from_provider(
    provider: ProviderConfig,
) -> dict[str, ModelCatalogMetadata]:
    metadata_by_model = getattr(provider, "model_metadata", {})
    return {
        model: ModelCatalogMetadata(
            name=metadata.name,
            api=metadata.api,
            base_url=metadata.base_url,
            reasoning=metadata.reasoning,
            input=tuple(item for item in metadata.input if item in {"text", "image"}),
            cost=dict(metadata.cost) or None,
            context_window=metadata.context_window,
            max_tokens=metadata.max_tokens,
            headers=dict(metadata.headers),
            compat=dict(metadata.compat),
            thinking_level_map=dict(metadata.thinking_level_map),
        )
        for model, metadata in metadata_by_model.items()
    }
