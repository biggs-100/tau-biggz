"""Provider and thinking mixin for CodingSession."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tau_agent.session import LeafEntry, ModelChangeEntry, ThinkingLevelChangeEntry

from tau_coding.provider_config import (
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    provider_has_usable_credentials,
    provider_thinking_levels,
    provider_thinking_unavailable_reason,
    save_default_provider_model,
    save_provider_thinking_level,
    toggle_saved_scoped_model,
    validate_provider_model,
)
import tau_coding.session as _session_mod
from tau_coding.session_models import ModelChoice
from tau_coding.session_provider import (
    _coerced_thinking_level,
    _unavailable_thinking_message,
)
from tau_coding.thinking import (
    THINKING_LEVELS,
    ThinkingLevel,
    next_thinking_level,
    normalize_thinking_level,
)

if TYPE_CHECKING:
    from tau_coding.session import CodingSession


class _ProviderMixin:
    """Provider and thinking operations for CodingSession.

    Mixin — accesses ``self`` for CodingSession internals (``self._config``,
    ``self._provider_settings``, ``self._harness``, etc.) set in ``__init__``.
    Calls persistence methods through MRO (``self._append_session_entry()``,
    ``self._refresh_persisted_state()``).
    """

    # -- thinking properties ---------------------------------------------------

    @property
    def available_thinking_levels(self) -> tuple[ThinkingLevel, ...]:
        """Return thinking modes supported by the active provider/model."""
        if self._provider_settings is None:
            return THINKING_LEVELS
        provider = self._active_provider_config()
        if provider is None:
            return ()
        return provider_thinking_levels(provider, model=self.model)

    @property
    def thinking_unavailable_reason(self) -> str | None:
        """Return why thinking controls are unavailable for the active model."""
        if self.available_thinking_levels:
            return None
        provider = self._active_provider_config()
        if provider is None:
            return "Active provider settings are not available"
        return provider_thinking_unavailable_reason(provider, model=self.model)

    # -- thinking control ------------------------------------------------------

    async def set_thinking_level(self, level: str) -> str:
        """Persist and activate a thinking mode for future turns."""
        normalized = normalize_thinking_level(level)
        available = self.available_thinking_levels
        if not available:
            raise ValueError(_unavailable_thinking_message(self))
        if normalized not in available:
            modes = ", ".join(available)
            raise ValueError(
                f"Thinking mode {normalized} is not available for "
                f"{self._provider_name}:{self.model}. Available modes: {modes}"
            )
        if normalized == self._thinking_level:
            return f"Thinking mode: {normalized}"

        previous = self._thinking_level
        self._thinking_level = normalized
        try:
            self._refresh_runtime_provider()
        except ProviderConfigError:
            self._thinking_level = previous
            raise

        entry = ThinkingLevelChangeEntry(
            parent_id=self._last_parent_id,
            thinking_level=normalized,
        )
        await self._append_session_entry(entry)
        leaf = LeafEntry(parent_id=entry.id, entry_id=entry.id)
        await self._append_session_entry(leaf)
        self._last_parent_id = entry.id

        self._persist_thinking_level_choice()
        await self._refresh_persisted_state(leaf_id=entry.id)
        return f"Thinking mode: {normalized}"

    async def cycle_thinking_level(self) -> str:
        """Cycle to the next supported thinking mode and persist it."""
        return await self.set_thinking_level(
            next_thinking_level(
                self._thinking_level,
                available=self.available_thinking_levels,
            )
        )

    # -- model switching -------------------------------------------------------

    def set_model(self, model: str) -> None:
        """Switch the active model for future turns and make it the default."""
        provider = self._active_provider_config()
        if provider is not None:
            validate_provider_model(provider, model)
        self._harness.config.model = model
        self._sync_thinking_level_to_active_model()
        self._refresh_runtime_provider()
        self._persist_default_model_choice()
        if self._config.session_id is not None and self._config.session_manager is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                model=model,
                provider_name=self.provider_name,
            )

    def set_model_choice(self, choice: ModelChoice) -> None:
        """Switch provider/model as one operation."""
        if choice.provider_name == self.provider_name:
            self.set_model(choice.model)
            return
        self._set_provider_model(choice.provider_name, choice.model)

    def is_scoped_model(self, choice: ModelChoice) -> bool:
        """Return whether a provider/model pair is in the scoped model list."""
        return choice in self.scoped_model_choices

    def toggle_scoped_model(self, choice: ModelChoice) -> tuple[ModelChoice, ...]:
        """Add or remove a model from the persisted scoped model list."""
        if self._provider_settings is None:
            raise ProviderConfigError("Provider settings are not available for this session")
        available = set(self.available_model_choices)
        if choice not in available:
            raise ProviderConfigError(
                f"Model is not available: {choice.provider_name}:{choice.model}"
            )

        self._provider_settings = toggle_saved_scoped_model(
            provider_name=choice.provider_name,
            model=choice.model,
            paths=self._resource_paths.paths,
            fallback_settings=self._provider_settings,
        )
        self._sync_thinking_level_to_active_model()
        return self.scoped_model_choices

    def cycle_scoped_model(self, *, reverse: bool = False) -> ModelChoice:
        """Switch to the next configured scoped model."""
        scoped = self.scoped_model_choices
        if not scoped:
            raise ProviderConfigError("No scoped models configured.")
        current = ModelChoice(provider_name=self.provider_name, model=self.model)
        try:
            current_index = scoped.index(current)
        except ValueError:
            current_index = -1 if not reverse else 0
        delta = -1 if reverse else 1
        choice = scoped[(current_index + delta) % len(scoped)]
        self.set_model_choice(choice)
        return choice

    # -- provider switching ----------------------------------------------------

    def set_provider(self, provider_name: str, *, persist_default: bool = True) -> None:
        """Switch the active provider and reset to that provider's default model."""
        if self._provider_settings is None:
            raise ProviderConfigError("Provider settings are not available for this session")
        provider_config = self._provider_settings.get_provider(provider_name)
        self._set_provider_model(
            provider_name,
            provider_config.default_model,
            persist_default=persist_default,
        )

    def _set_provider_model(
        self,
        provider_name: str,
        model: str,
        *,
        persist_default: bool = True,
    ) -> None:
        """Switch active provider/model without constructing an intermediate provider."""
        if self._provider_settings is None:
            raise ProviderConfigError("Provider settings are not available for this session")

        provider_config = self._provider_settings.get_provider(provider_name)
        if model not in provider_config.models:
            raise ProviderConfigError(f"Model is not configured: {provider_name}:{model}")
        thinking_level = _coerced_thinking_level(
            provider_config,
            model=model,
            current=self._thinking_level,
            preferred=provider_config.thinking_defaults.get(model),
        )
        try:
            provider = _session_mod.create_model_provider(
                provider_config,
                credential_store=self._credential_store,
                model=model,
                thinking_level=thinking_level,
            )
        except RuntimeError as exc:
            raise ProviderConfigError(str(exc)) from exc

        self._owned_providers.append(provider)
        self._harness.config.provider = provider
        self._provider_name = provider_config.name
        self._runtime_provider_config = provider_config
        self._harness.config.model = model
        self._thinking_level = thinking_level
        if persist_default:
            self._persist_default_model_choice()
        if self._config.session_id is not None and self._config.session_manager is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                model=model,
                provider_name=self.provider_name,
            )

    # -- internal helpers ------------------------------------------------------

    def _active_provider_config(self) -> ProviderConfig | None:
        if self._provider_settings is None:
            return None
        try:
            return self._provider_settings.get_provider(self._provider_name)
        except ProviderConfigError:
            return None

    def _sync_thinking_level_to_active_model(self) -> None:
        provider = self._active_provider_config()
        if provider is None:
            return
        self._thinking_level = _coerced_thinking_level(
            provider,
            model=self.model,
            current=self._thinking_level,
            preferred=provider.thinking_defaults.get(self.model),
        )

    def _persist_default_model_choice(self) -> None:
        if self._provider_settings is None:
            return
        self._provider_settings = save_default_provider_model(
            provider_name=self.provider_name,
            model=self.model,
            paths=self._resource_paths.paths,
            fallback_settings=self._provider_settings,
        )
        self._sync_thinking_level_to_active_model()

    def _persist_thinking_level_choice(self) -> None:
        if self._provider_settings is None:
            return
        provider = self._active_provider_config()
        if provider is None or self._thinking_level not in provider_thinking_levels(
            provider,
            model=self.model,
        ):
            return
        try:
            self._provider_settings = save_provider_thinking_level(
                provider_name=self.provider_name,
                model=self.model,
                thinking_level=self._thinking_level,
                paths=self._resource_paths.paths,
                fallback_settings=self._provider_settings,
            )
        except ProviderConfigError:
            return

    def _refresh_runtime_provider(self) -> None:
        if self._runtime_provider_config is None:
            return
        provider_config = self._active_provider_config() or self._runtime_provider_config
        validate_provider_model(provider_config, self.model)
        try:
            provider = _session_mod.create_model_provider(
                provider_config,
                credential_store=self._credential_store,
                model=self.model,
                thinking_level=self._thinking_level,
            )
        except RuntimeError as exc:
            raise ProviderConfigError(str(exc)) from exc
        self._owned_providers.append(provider)
        self._harness.config.provider = provider
        self._runtime_provider_config = provider_config

    def _provider_is_usable(self, provider: ProviderConfig) -> bool:
        return provider_has_usable_credentials(
            provider,
            credential_reader=self._credential_store,
        )

    def _usable_provider_configs(self) -> tuple[ProviderConfig, ...]:
        if self._provider_settings is None:
            return ()
        return tuple(
            provider
            for provider in self._provider_settings.providers
            if self._provider_is_usable(provider)
        )
