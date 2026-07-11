"""Reload, resume, and new-session mixin for CodingSession."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from tau_agent.session import LeafEntry

from tau_coding.extensions import get_default_registry
import tau_coding.session as _session_mod

from tau_coding.provider_config import (
    ProviderConfigError,
    resolve_provider_selection,
    validate_provider_model,
)
from tau_coding.session_models import CodingSessionConfig
from tau_coding.session_provider import _coerced_thinking_level
from tau_coding.session_storage import jsonl_session_storage
from tau_coding.reload import CodingReloadSummary
from tau_coding.resources import resource_paths_with_cwd
from tau_coding.session_resources import (
    _category_summary,
    _context_file_signatures,
    _diagnostic_signatures,
    _load_session_resources,
    _prompt_template_signatures,
    _skill_signatures,
    _system_prompt_resource_signatures,
)
from tau_coding.system_prompt import (
    BuildSystemPromptOptions,
    build_system_prompt,
)

if TYPE_CHECKING:
    from tau_coding.session import CodingSession
    from tau_agent import AgentHarness
    from tau_agent.session import SessionState
    from tau_coding.commands import CommandRegistry
    from tau_coding.credentials import FileCredentialStore
    from tau_coding.provider_config import ProviderConfig, ProviderSettings
    from tau_coding.provider_runtime import ClosableModelProvider
    from tau_coding.prompt_templates import PromptTemplate
    from tau_coding.resources import ResourceDiagnostic, TauResourcePaths
    from tau_coding.skills import Skill
    from tau_coding.system_prompt import ProjectContextFile
    from tau_coding.thinking import ThinkingLevel


class _ReloadResumeMixin:
    """Reload, resume, new-session, and close operations for CodingSession.

    Mixin — accesses ``self`` for CodingSession internals (``self._config``,
    ``self._harness``, etc.) set in ``__init__``.
    Calls provider and persistence methods through MRO.
    """

    # Attributes accessed from CodingSession — declared for mypy strict
    _config: CodingSessionConfig
    _harness: AgentHarness
    _provider_settings: ProviderSettings | None
    _provider_name: str
    _runtime_provider_config: ProviderConfig | None
    _skills: tuple[Skill, ...]
    _prompt_templates: tuple[PromptTemplate, ...]
    _context_files: tuple[ProjectContextFile, ...]
    _resource_diagnostics: tuple[ResourceDiagnostic, ...]
    _resource_paths: TauResourcePaths
    _state: SessionState
    _thinking_level: ThinkingLevel
    model: str
    _last_parent_id: str | None
    _owned_providers: list[ClosableModelProvider]
    _credential_store: FileCredentialStore
    _command_registry: CommandRegistry
    _auto_compact_token_threshold: int | None
    _auto_compact_enabled: bool
    cwd: Path

    def reload(self) -> CodingReloadSummary:
        """Reload local coding resources and project context for future turns."""
        before_skills = _skill_signatures(self._skills)
        before_prompt_templates = _prompt_template_signatures(self._prompt_templates)
        before_context_files = _context_file_signatures(self._context_files)
        before_diagnostics = _diagnostic_signatures(self._resource_diagnostics)
        before_system_prompt_inputs = _system_prompt_resource_signatures(
            skills=self._skills,
            context_files=self._context_files,
        )

        resources = _load_session_resources(self._resource_paths, self._config.context_files)

        after_skills = _skill_signatures(resources.skills)
        after_prompt_templates = _prompt_template_signatures(resources.prompt_templates)
        after_context_files = _context_file_signatures(resources.context_files)
        after_diagnostics = _diagnostic_signatures(resources.diagnostics)
        after_system_prompt_inputs = _system_prompt_resource_signatures(
            skills=resources.skills,
            context_files=resources.context_files,
        )

        rebuilt_system_prompt: str | None = None
        system_prompt_rebuilt = False
        if (
            self._config.system is None
            and before_system_prompt_inputs != after_system_prompt_inputs
        ):
            rebuilt_system_prompt = build_system_prompt(
                BuildSystemPromptOptions(
                    cwd=self._config.cwd,
                    tools=self._harness.config.tools,
                    skills=resources.skills,
                    custom_prompt=self._config.custom_system_prompt,
                    append_system_prompt=self._config.append_system_prompt,
                    context_files=resources.context_files,
                )
            )
            system_prompt_rebuilt = True

        self._skills = resources.skills
        self._prompt_templates = resources.prompt_templates
        self._context_files = resources.context_files
        self._resource_diagnostics = resources.diagnostics
        if rebuilt_system_prompt is not None:
            self._harness.config.system = rebuilt_system_prompt
            self._invalidate_context_usage_cache()  # type: ignore[attr-defined]

        return CodingReloadSummary(
            skills=_category_summary(before_skills, after_skills),
            prompt_templates=_category_summary(
                before_prompt_templates,
                after_prompt_templates,
            ),
            context_files=_category_summary(before_context_files, after_context_files),
            diagnostics=_category_summary(before_diagnostics, after_diagnostics),
            system_prompt_rebuilt=system_prompt_rebuilt,
        )

    def reload_provider_settings(self) -> None:
        """Reload provider settings for login and model-selection flows."""
        if self._provider_settings is None:
            return
        previous_settings = self._provider_settings
        previous_thinking_level = self._thinking_level
        self._provider_settings = _session_mod.load_provider_settings(self._resource_paths.paths)
        try:
            self._sync_thinking_level_to_active_model()  # type: ignore[attr-defined]
            self._refresh_runtime_provider()  # type: ignore[attr-defined]
        except ProviderConfigError:
            self._provider_settings = previous_settings
            self._thinking_level = previous_thinking_level
            raise

    async def resume(self, session_id: str) -> str:
        """Replace this session's active state with another indexed session."""
        manager = self._config.session_manager
        if manager is None:
            raise ValueError("Session manager is not available")
        record = manager.get_session(session_id)
        if record is None:
            raise ValueError(f"Unknown session: {session_id}")

        provider_name = self._provider_name
        runtime_provider_config = self._runtime_provider_config
        model = self.model
        restore_record_model = False
        if record.provider_name:
            if self._provider_settings is None:
                raise ProviderConfigError(
                    "Cannot resume session provider without provider settings: "
                    f"{record.provider_name}"
                )
            try:
                runtime_provider_config = self._provider_settings.get_provider(record.provider_name)
            except ProviderConfigError as exc:
                raise ProviderConfigError(
                    f"Session provider is not configured: {record.provider_name}"
                ) from exc
            provider_name = runtime_provider_config.name
            model = record.model
            restore_record_model = True
            validate_provider_model(runtime_provider_config, model)

        replacement = await type(self).load(  # type: ignore[attr-defined]
            CodingSessionConfig(
                provider=self._harness.config.provider,
                model=model,
                cwd=record.cwd,
                storage=jsonl_session_storage(record.path),
                system=self._config.system,
                custom_system_prompt=self._config.custom_system_prompt,
                append_system_prompt=self._config.append_system_prompt,
                context_files=self._config.context_files,
                resource_paths=self._config.resource_paths,
                session_id=record.id,
                session_manager=manager,
                command_registry=self._command_registry,
                provider_name=provider_name,
                provider_settings=self._provider_settings,
                runtime_provider_config=runtime_provider_config,
                auto_compact_token_threshold=self._auto_compact_token_threshold,
                auto_compact_enabled=self._auto_compact_enabled,
                thinking_level=self._thinking_level,
                shell_command_prefix=self._config.shell_command_prefix,
            )
        )

        if restore_record_model:
            if runtime_provider_config is None:
                raise ProviderConfigError(f"Session provider is not configured: {provider_name}")
            validate_provider_model(runtime_provider_config, replacement.model)
        else:
            replacement._harness.config.model = self.model
            replacement._sync_thinking_level_to_active_model()
            replacement._refresh_runtime_provider()

        self._config = replacement._config
        self._state = replacement._state
        self._harness = replacement._harness
        self._invalidate_context_usage_cache()  # type: ignore[attr-defined]
        self._last_parent_id = replacement._last_parent_id
        self._skills = replacement._skills
        self._prompt_templates = replacement._prompt_templates
        self._context_files = replacement._context_files
        self._resource_diagnostics = replacement._resource_diagnostics
        self._command_registry = replacement._command_registry
        self._provider_name = replacement._provider_name
        self._provider_settings = replacement._provider_settings
        self._runtime_provider_config = replacement._runtime_provider_config
        self._resource_paths = replacement._resource_paths
        self._auto_compact_token_threshold = replacement._auto_compact_token_threshold
        self._auto_compact_enabled = replacement._auto_compact_enabled
        self._thinking_level = replacement._thinking_level
        return f"Resumed session: {record.id}"

    async def new_session(self) -> str:
        """Replace this session's active state with a pending unindexed session."""
        manager = self._config.session_manager
        if manager is None:
            raise ValueError("Session manager is not available")

        provider_name = self._provider_name
        model = self.model
        runtime_provider_config = self._runtime_provider_config
        thinking_level = self._thinking_level
        if self._provider_settings is not None:
            selection = resolve_provider_selection(self._provider_settings)
            provider_name = selection.provider.name
            model = selection.model
            runtime_provider_config = selection.provider
            thinking_level = _coerced_thinking_level(
                selection.provider,
                model=model,
                current=self._thinking_level,
            )

        record = manager.prepare_session(
            cwd=self.cwd,
            model=model,
            provider_name=provider_name,
        )
        replacement = await type(self).load(  # type: ignore[attr-defined]
            replace(
                self._config,
                provider=self._harness.config.provider,
                model=record.model or model,
                cwd=record.cwd,
                storage=jsonl_session_storage(record.path),
                session_id=record.id,
                provider_name=provider_name,
                provider_settings=self._provider_settings,
                runtime_provider_config=runtime_provider_config,
                thinking_level=thinking_level,
                index_on_first_persist=True,
            )
        )
        self._config = replacement._config
        self._state = replacement._state
        self._harness = replacement._harness
        self._invalidate_context_usage_cache()  # type: ignore[attr-defined]
        self._last_parent_id = replacement._last_parent_id
        self._skills = replacement._skills
        self._prompt_templates = replacement._prompt_templates
        self._context_files = replacement._context_files
        self._resource_diagnostics = replacement._resource_diagnostics
        self._command_registry = replacement._command_registry
        self._provider_name = replacement._provider_name
        self._provider_settings = replacement._provider_settings
        self._runtime_provider_config = replacement._runtime_provider_config
        self._resource_paths = replacement._resource_paths
        self._auto_compact_token_threshold = replacement._auto_compact_token_threshold
        self._auto_compact_enabled = replacement._auto_compact_enabled
        self._thinking_level = replacement._thinking_level
        return f"Started new session: {record.id}"

    async def aclose(self) -> None:
        """Close runtime providers and MCP connections."""
        get_default_registry().dispatch_event("session_end", {"session": self})
        for provider in self._owned_providers:
            await provider.aclose()
        self._owned_providers.clear()
        mcp_reg = __import__("tau_coding.mcp_integration", fromlist=["get_mcp_registry"]).get_mcp_registry()
        if mcp_reg.connected:
            await mcp_reg.disconnect_all()
