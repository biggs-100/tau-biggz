"""Persistent coding-session wrapper built on AgentHarness."""



from __future__ import annotations

__all__ = [
    "CodingSession",
    "CodingSessionConfig",
    "ModelChoice",
    "SessionTreeBranchResult",
    "SessionTreeChoice",
    "TerminalCommandResult",
    "create_model_provider",
    "default_session_path",
    "jsonl_session_storage",
    "load_provider_settings",
    "parse_terminal_command",
]

from collections.abc import AsyncIterator

from dataclasses import dataclass, replace

from pathlib import Path

from typing import Literal



from tau_agent import (

    AgentEvent,

    AgentHarness,

    AgentHarnessConfig,

    ErrorEvent,

    MessageEndEvent,

    QueuedMessages,

    QueueUpdateEvent,

    ToolExecutionEndEvent,

)

from tau_agent.messages import AgentMessage, AssistantMessage, ToolResultMessage, UserMessage

from tau_agent.session import (

    BranchSummaryEntry,

    CompactionEntry,

    JsonlSessionStorage,

    LeafEntry,

    MessageEntry,

    ModelChangeEntry,

    SessionInfoEntry,

    SessionState,

    SessionStorage,

    ThinkingLevelChangeEntry,

)

from tau_agent.session.entries import SessionEntry

from tau_agent.session.jsonl import entry_to_json_line

from tau_agent.session.tree import SessionTreeError, path_to_entry

from tau_agent.tools import AgentTool

from tau_ai import ModelProvider

from tau_ai.events import ProviderErrorEvent, ProviderResponseEndEvent, ProviderTextDeltaEvent

from tau_coding.branch_summary import summarize_branch_messages_with_model

from tau_coding.commands import CommandRegistry, CommandResult, create_default_command_registry

from tau_coding.context import discover_project_context_with_diagnostics

from tau_coding.context_window import (

    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,

    DEFAULT_CONTEXT_WINDOW_TOKENS,

    SUMMARIZATION_SYSTEM_PROMPT,

    ContextUsageEstimate,

    auto_compaction_threshold_for_context_window,

    build_compaction_summary_prompt,

    estimate_context_usage,

    estimate_message_tokens,

    summarize_messages_for_compaction,

)

from tau_coding.credentials import FileCredentialStore, credentials_path

from tau_coding.diagnostics import (

    AgentCallDiagnosticContext,

    AgentCallDiagnosticLogger,

    new_agent_call_run_id,

)

from tau_coding.paths import TauPaths

from tau_coding.prompt_templates import (

    PromptTemplate,

    expand_prompt_template_command,

    load_prompt_templates_with_diagnostics,

)

from tau_coding.provider_config import (

    ProviderConfig,

    ProviderConfigError,

    ProviderSettings,

    load_provider_settings,

    provider_default_thinking_level,

    provider_has_usable_credentials,

    provider_thinking_levels,

    provider_thinking_unavailable_reason,

    resolve_provider_selection,

    save_default_provider_model,

    save_provider_thinking_level,

    toggle_saved_scoped_model,

    validate_provider_model,

)

from tau_coding.provider_runtime import ClosableModelProvider, create_model_provider

from tau_coding.reload import CodingReloadSummary, ReloadCategorySummary

from tau_coding.resources import (

    ResourceDiagnostic,

    ResourceError,

    TauResourcePaths,

    resource_paths_with_cwd,

)

from tau_coding.session_export import (

    default_session_export_artifact_path,

    export_session_artifact,

    normalize_export_format,

)

from tau_coding.session_manager import SessionManager

from tau_coding.skills import Skill, expand_skill_command, load_skills_with_diagnostics

from tau_coding.system_prompt import (

    BuildSystemPromptOptions,

    ProjectContextFile,

    build_system_prompt,

)

from tau_coding.thinking import (

    DEFAULT_THINKING_LEVEL,

    THINKING_LEVELS,

    ThinkingLevel,

    next_thinking_level,

    normalize_thinking_level,

)

from tau_coding.extensions import get_default_registry

from tau_coding.harness import HarnessDefinition, SandboxConfig, coding_harness

from tau_coding.tools import create_bash_tool, create_coding_tools

from tau_coding.session_models import (
    CodingSessionConfig,
    CompactionPlan,
    ModelChoice,
    SessionResources,
    SessionTreeBranchResult,
    SessionTreeChoice,
    StreamingBehavior,
    TerminalCommandRequest,
    TerminalCommandResult,
)
from tau_coding.session_compaction import (
    _first_recent_context_index,
    _is_context_overflow_error,
    _next_user_message_index,
)
from tau_coding.session_tree import (
    _detach_missing_parents,
    _is_branchable_tree_entry,
    _is_tool_call_tree_entry,
    _last_parent_id_from_state,
    _latest_leaf_entry,
    _messages_after_entry_on_active_path,
    _message_text_preview,
    _ordered_tree_entries,
    _short_preview,
    _tree_branch_indents,
    _tree_choice_label,
    _tree_entry_title,
)
from tau_coding.session_utils import (
    _auto_session_name_from_text,
    _terminal_command_context_message,
    parse_terminal_command,
)
from tau_coding.session_resources import (
    _category_summary,
    _context_file_signatures,
    _diagnostic_signatures,
    _load_session_resources,
    _merge_context_files,
    _prompt_template_signatures,
    _skill_signatures,
    _system_prompt_resource_signatures,
)
from tau_coding.session_tool_repair import _interrupted_tool_repair_plan
from tau_coding.session_storage import (
    _append_session_entry_sync,
    default_session_path,
    jsonl_session_storage,
)
from tau_coding._session_provider import _ProviderMixin
from tau_coding._session_reload import _ReloadResumeMixin
from tau_coding._session_compaction import _CompactionMixin



class CodingSession(_ProviderMixin, _ReloadResumeMixin, _CompactionMixin):

    """Tau's coding-agent environment wrapper.



    `AgentHarness` owns the in-memory agent brain. `CodingSession` owns the

    coding-session environment around it: durable session entries, default coding

    tools, and a small command seam for later phases.

    """

    # Attribute type declarations — mirroring mixin annotations for mypy strict
    _config: CodingSessionConfig
    _state: SessionState
    _harness: AgentHarness
    _pending_initial_entries: tuple[SessionEntry, ...]
    _skills: tuple[Skill, ...]
    _prompt_templates: tuple[PromptTemplate, ...]
    _context_files: tuple[ProjectContextFile, ...]
    _resource_diagnostics: tuple[ResourceDiagnostic, ...]
    _command_registry: CommandRegistry
    _provider_name: str
    _provider_settings: ProviderSettings | None
    _runtime_provider_config: ProviderConfig | None
    _resource_paths: TauResourcePaths
    _auto_compact_token_threshold: int | None
    _auto_compact_enabled: bool
    _thinking_level: ThinkingLevel
    _context_usage_cache: ContextUsageEstimate | None
    _owned_providers: list[ClosableModelProvider]
    _diagnostic_logger: AgentCallDiagnosticLogger
    _credential_store: FileCredentialStore

    def __init__(

        self,

        config: CodingSessionConfig,

        *,

        state: SessionState,

        harness: AgentHarness,

        last_parent_id: str | None,

        skills: tuple[Skill, ...] = (),

        prompt_templates: tuple[PromptTemplate, ...] = (),

        context_files: tuple[ProjectContextFile, ...] = (),

        resource_diagnostics: tuple[ResourceDiagnostic, ...] = (),

        command_registry: CommandRegistry | None = None,

        pending_initial_entries: tuple[SessionEntry, ...] = (),

    ) -> None:

        self._config = config

        self._state = state

        self._harness = harness

        self._last_parent_id = last_parent_id

        self._pending_initial_entries: tuple[SessionEntry, ...] = pending_initial_entries

        self._skills = skills

        self._prompt_templates = prompt_templates

        self._context_files = context_files

        self._resource_diagnostics = resource_diagnostics

        self._command_registry = command_registry or create_default_command_registry()

        self._provider_name: str = config.provider_name or "openai"

        self._provider_settings: ProviderSettings | None = config.provider_settings

        self._runtime_provider_config: ProviderConfig | None = config.runtime_provider_config

        self._resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)

        self._auto_compact_token_threshold = config.auto_compact_token_threshold

        self._auto_compact_enabled = config.auto_compact_enabled

        self._thinking_level = _state_thinking_level(

            state,

            default=_default_thinking_level_for_active_model(self),

        )

        self._context_usage_cache: ContextUsageEstimate | None = None

        self._owned_providers: list[ClosableModelProvider] = []

        self._diagnostic_logger = AgentCallDiagnosticLogger.from_paths(self._resource_paths.paths)

        self._credential_store = FileCredentialStore(

            credentials_path(self._resource_paths.paths) if self._resource_paths.paths else None

        )

        self._last_diagnostic_log_path: Path | None = None



    @classmethod

    async def load(cls, config: CodingSessionConfig) -> CodingSession:

        """Load a coding session from append-only storage."""

        entries = await config.storage.read_all()

        pending_initial_entries: tuple[SessionEntry, ...] = ()

        if not entries:

            info = SessionInfoEntry(cwd=str(config.cwd))

            initial_model = _initial_model_for_config(config)

            model = ModelChangeEntry(

                parent_id=info.id,

                model=initial_model,

            )

            thinking = ThinkingLevelChangeEntry(

                parent_id=model.id,

                thinking_level=_initial_thinking_level_for_config(config, model=initial_model),

            )

            entries = [info, model, thinking]

            pending_initial_entries = (info, model, thinking)

        else:

            entries = _detach_missing_parents(entries)



        linear_state = SessionState.from_entries(entries)

        latest_leaf = _latest_leaf_entry(entries)

        state = (

            SessionState.from_entries(entries, leaf_id=latest_leaf.entry_id)

            if latest_leaf is not None

            else linear_state

        )

        from tau_coding.harness import get_active_harness

        _active_harness = get_active_harness()

        tools = (

            config.tools

            if config.tools is not None

            else create_coding_tools(

                cwd=config.cwd,

                shell_command_prefix=config.shell_command_prefix,

                extension_tools=get_default_registry().get_tools(),

                approval=_active_harness.approval,
                    sandbox_config=config.sandbox_config or _active_harness.sandbox,
                )
            )
        resource_paths  = resource_paths_with_cwd(config.resource_paths, config.cwd)

        resources = _load_session_resources(resource_paths, config.context_files)

        system = (

            config.system

            if config.system is not None

            else build_system_prompt(

                BuildSystemPromptOptions(

                    cwd=config.cwd,

                    tools=tools,

                    skills=resources.skills,

                    custom_prompt=config.custom_system_prompt,

                    append_system_prompt=config.append_system_prompt,

                    context_files=resources.context_files,

                )

            )

        )

        harness = AgentHarness(

            AgentHarnessConfig(

                provider=config.provider,

                model=_runtime_model_for_state(config, state),

                system=system,

                tools=tools,

            ),

            messages=state.messages,

        )

        session = cls(

            config,

            state=state,

            harness=harness,

            last_parent_id=_last_parent_id_from_state(state),

            skills=resources.skills,

            prompt_templates=resources.prompt_templates,

            context_files=resources.context_files,

            resource_diagnostics=resources.diagnostics,

            command_registry=config.command_registry,

            pending_initial_entries=pending_initial_entries,

        )

        await session._persist_loaded_interrupted_tool_repairs()

        session._sync_thinking_level_to_active_model()

        session._refresh_runtime_provider()

        get_default_registry().dispatch_event("session_start", {"session": session})

        return session



    @property

    def cwd(self) -> Path:  # type: ignore[override]

        """Return the session working directory."""

        return self._config.cwd



    @property

    def provider(self) -> ModelProvider:

        """Return the active model provider for this session."""

        return self._config.provider



    @property

    def model(self) -> str:  # type: ignore[override]

        """Return the active model for this session."""

        return self._harness.config.model



    @property

    def provider_name(self) -> str:  # type: ignore[override]

        """Return the active provider name."""

        return self._provider_name



    @property

    def available_providers(self) -> tuple[str, ...]:

        """Return provider names Tau can call with available credentials."""

        if self._provider_settings is None:

            return (self._provider_name,)

        return tuple(provider.name for provider in self._usable_provider_configs())



    @property

    def available_models(self) -> tuple[str, ...]:

        """Return model names for the active provider when it is usable."""

        if self._provider_settings is None:

            return (self.model,)

        try:

            provider = self._provider_settings.get_provider(self._provider_name)

        except ProviderConfigError:

            return (self.model,)

        if not self._provider_is_usable(provider):

            return ()

        return provider.models



    @property

    def available_model_choices(self) -> tuple[ModelChoice, ...]:  # type: ignore[override]

        """Return provider/model choices Tau can call with available credentials."""

        if self._provider_settings is None:

            return (ModelChoice(provider_name=self._provider_name, model=self.model),)

        return tuple(

            ModelChoice(provider_name=provider.name, model=model)

            for provider in self._usable_provider_configs()

            for model in provider.models

        )



    @property

    def scoped_model_choices(self) -> tuple[ModelChoice, ...]:  # type: ignore[override]

        """Return configured quick-switch model choices that are currently usable."""

        if self._provider_settings is None:

            return ()

        available = set(self.available_model_choices)

        return tuple(

            choice

            for choice in (

                ModelChoice(provider_name=item.provider, model=item.model)

                for item in self._provider_settings.scoped_models

            )

            if choice in available

        )



    @property

    def tools(self) -> tuple[AgentTool, ...]:

        """Return the tools available to the agent."""

        return tuple(self._harness.config.tools)



    @property

    def messages(self) -> tuple[AgentMessage, ...]:

        """Return the restored/current transcript."""

        return self._harness.messages



    @property

    def state(self) -> SessionState:

        """Return the last replayed durable session state."""

        return self._state



    async def tree_choices(self) -> tuple[SessionTreeChoice, ...]:

        """Return branchable session entries for a tree picker."""

        entries = await self._read_session_entries()

        branch_indents = _tree_branch_indents(entries)

        return tuple(

            SessionTreeChoice(

                entry_id=entry.id,

                label=_tree_choice_label(entry, branch_indent=branch_indents.get(entry.id, 0)),

                active=entry.id == self._state.active_leaf_id,

                is_tool_call=_is_tool_call_tree_entry(entry),

            )

            for entry in _ordered_tree_entries(entries)

            if _is_branchable_tree_entry(entry)

        )



    async def branch_to_entry(

        self,

        entry_id: str,

        *,

        summarize: bool = False,

        custom_instructions: str | None = None,

        replace_instructions: bool = False,

    ) -> SessionTreeBranchResult:

        """Move the active leaf to a previous entry, preserving existing history."""

        entries = await self._read_session_entries()

        by_id = {entry.id: entry for entry in entries}

        if entry_id not in by_id:

            raise ValueError(f"Unknown session entry: {entry_id}")

        selected_entry = by_id[entry_id]

        if not _is_branchable_tree_entry(selected_entry):

            raise ValueError(f"Session entry cannot be branched from: {entry_id}")



        target_id: str | None = entry_id

        input_prefill: str | None = None

        summary_entry: BranchSummaryEntry | None = None

        if summarize:

            abandoned_messages = _messages_after_entry_on_active_path(

                entries,

                entry_id,

                self._last_parent_id,

            )

            if abandoned_messages:

                summary = await self._summarize_branch_messages(

                    abandoned_messages,

                    custom_instructions=custom_instructions,

                    replace_instructions=replace_instructions,

                )

                summary_entry = BranchSummaryEntry(

                    parent_id=entry_id,

                    branch_root_id=entry_id,

                    summary=summary,

                )

                await self._append_session_entry(summary_entry)

                target_id = summary_entry.id

        elif selected_entry.type == "message" and isinstance(selected_entry.message, UserMessage):

            target_id = selected_entry.parent_id

            input_prefill = selected_entry.message.content



        leaf = LeafEntry(parent_id=target_id, entry_id=target_id)

        await self._append_session_entry(leaf)

        self._last_parent_id = target_id



        await self._refresh_persisted_state(leaf_id=target_id)

        self._harness.replace_messages(self._state.messages)

        self._invalidate_context_usage_cache()

        self._thinking_level = _state_thinking_level(

            self._state,

            default=_default_thinking_level_for_active_model(self),

        )

        self._sync_thinking_level_to_active_model()

        self._refresh_runtime_provider()

        suffix = " with branch summary" if summary_entry is not None else ""

        if input_prefill is not None:

            return SessionTreeBranchResult(

                message=f"Branched session before {entry_id}.",

                input_prefill=input_prefill,

            )

        return SessionTreeBranchResult(message=f"Branched session at {target_id}{suffix}.")



    @property

    def thinking_level(self) -> ThinkingLevel:

        """Return the active thinking mode for future turns."""

        return self._thinking_level







    @property

    def storage(self) -> SessionStorage:

        """Return the backing session storage."""

        return self._config.storage



    async def export(

        self,

        destination: Path | None = None,

        *,

        format: str | None = None,

    ) -> Path:

        """Export the current session to a user-facing artifact."""

        entries = await self._read_session_entries()

        session_path = _storage_path(self._config.storage)

        export_format = normalize_export_format(

            format or (destination.suffix.removeprefix(".") if destination else "html")

        )

        output_path = _resolve_export_destination(

            destination,

            cwd=self.cwd,

            session_path=session_path,

            format=export_format,

        )

        return export_session_artifact(

            entries,

            output_path,

            title=_session_export_title(self),

            source=str(session_path) if session_path is not None else self.session_id,

            format=export_format,

        )



    @property

    def skills(self) -> tuple[Skill, ...]:

        """Return loaded skills."""

        return self._skills



    @property

    def prompt_templates(self) -> tuple[PromptTemplate, ...]:

        """Return loaded prompt templates."""

        return self._prompt_templates



    @property

    def context_files(self) -> tuple[ProjectContextFile, ...]:

        """Return active project context files."""

        return self._context_files



    @property

    def context_token_estimate(self) -> int:  # type: ignore[override]

        """Return a rough token estimate for the active provider context."""

        return self.context_usage.total_tokens



    @property

    def context_usage(self) -> ContextUsageEstimate:

        """Return structured context accounting for the active provider context."""

        if self._context_usage_cache is None:

            self._context_usage_cache = estimate_context_usage(

                system=self._harness.config.system,

                messages=self._harness.messages,

                tools=tuple(self._harness.config.tools),

            )

        return self._context_usage_cache



    @property

    def system_prompt(self) -> str:

        """Return the effective system prompt sent to the model."""

        return self._harness.config.system



    @property

    def auto_compact_token_threshold(self) -> int | None:  # type: ignore[override]

        """Return the effective automatic compaction threshold, if any."""

        if not self._auto_compact_enabled:

            return None

        if self._auto_compact_token_threshold is not None:

            return self._auto_compact_token_threshold

        return auto_compaction_threshold_for_context_window(self.context_window_tokens)



    @property

    def context_window_tokens(self) -> int:

        """Return the active model's configured context window, or Tau's fallback."""

        provider = self._active_provider_config()

        if provider is None:

            return DEFAULT_CONTEXT_WINDOW_TOKENS

        return provider.context_windows.get(self.model, DEFAULT_CONTEXT_WINDOW_TOKENS)



    @property

    def command_registry(self) -> CommandRegistry:

        """Return the slash-command registry used by this session."""

        return self._command_registry



    @property

    def resource_diagnostics(self) -> tuple[ResourceDiagnostic, ...]:

        """Return non-fatal resource discovery diagnostics."""

        return self._resource_diagnostics



    @property

    def session_id(self) -> str | None:

        """Return this session's manager id, if indexed."""

        return self._config.session_id



    @property

    def session_title(self) -> str | None:  # type: ignore[override]

        """Return this session's indexed human-friendly title, if named."""

        if self._config.session_id is None or self._config.session_manager is None:

            return None

        record = self._config.session_manager.get_session(self._config.session_id)

        if record is None:

            return None

        return record.title



    @property

    def session_manager(self) -> SessionManager | None:

        """Return the session manager, if available."""

        return self._config.session_manager



    @property

    def is_running(self) -> bool:

        """Return whether this session currently has an active agent run."""

        return self._harness.is_running



    @property

    def queued_messages(self) -> QueuedMessages:

        """Return queued steering and follow-up messages."""

        return self._harness.queued_messages



    @property

    def queued_steering_messages(self) -> tuple[str, ...]:

        """Return queued steering message text for UI display."""

        return tuple(message.content for message in self._harness.queued_messages.steering)



    @property

    def queued_follow_up_messages(self) -> tuple[str, ...]:

        """Return queued follow-up message text for UI display."""

        return tuple(message.content for message in self._harness.queued_messages.follow_up)



    @property

    def last_diagnostic_log_path(self) -> Path | None:

        """Return the last diagnostic log path written by this session."""

        return self._last_diagnostic_log_path



    def cancel(self) -> None:

        """Cancel the currently running agent turn, if any."""

        self._harness.cancel()



    def queue_update_event(self) -> QueueUpdateEvent:

        """Return the current queue state as an agent event."""

        return self._harness.queue_update_event()



    def clear_queued_messages(self) -> QueuedMessages:

        """Clear queued steering and follow-up messages."""

        return self._harness.clear_queues()



    def pop_latest_follow_up_message(self) -> str | None:

        """Remove and return the most recently queued follow-up message."""

        message = self._harness.pop_latest_follow_up()

        return None if message is None else message.content



















    def handle_command(self, text: str) -> CommandResult:

        """Handle coding-session slash commands.



        Prompt-template slash commands are expansion directives, so they remain

        unhandled here and flow through `prompt()` for on-the-fly replacement.

        """

        if expand_prompt_template_command(text, self._prompt_templates) is not None:

            return CommandResult(handled=False)

        return self._command_registry.execute(self, text)



    def ensure_session_indexed(self) -> None:

        """Persist pending session metadata and add this session to the resume index."""

        if self._config.session_id is None or self._config.session_manager is None:

            return

        if self._config.session_manager.get_session(self._config.session_id) is None:

            self._config.session_manager.create_session(

                cwd=self.cwd,

                model=self.model,

                provider_name=self.provider_name,

                session_id=self._config.session_id,

            )

        self._config = replace(self._config, index_on_first_persist=False)

        self._ensure_session_file_initialized()



    def expand_prompt_text(self, text: str) -> str:

        """Expand prompt text using loaded markdown resources."""

        expanded_prompt = expand_prompt_template_command(text, self._prompt_templates)

        if expanded_prompt is not None:

            return expanded_prompt

        expanded_skill = expand_skill_command(text, self._skills)

        return expanded_skill if expanded_skill is not None else text



    async def run_terminal_command(

        self,

        command: str,

        *,

        add_to_context: bool,

    ) -> TerminalCommandResult:

        """Run a shell command in the session cwd, optionally adding output to context."""

        normalized_command = command.strip()

        if not normalized_command:

            raise ValueError("Terminal command cannot be empty")



        bash_tool = create_bash_tool(

            cwd=self.cwd,

            shell_command_prefix=self._config.shell_command_prefix,

        )

        result = await bash_tool.execute({"command": normalized_command})

        exit_code = None

        if result.data is not None:

            raw_exit_code = result.data.get("exit_code")

            exit_code = raw_exit_code if isinstance(raw_exit_code, int) else None



        if add_to_context:

            before_count = len(self._harness.messages)

            self._harness.append_message(

                UserMessage(

                    content=_terminal_command_context_message(

                        normalized_command,

                        result.content,

                    )

                )

            )

            self._invalidate_context_usage_cache()

            await self._persist_messages_since(before_count)



        return TerminalCommandResult(

            command=normalized_command,

            output=result.content,

            exit_code=exit_code,

            ok=result.ok,

            added_to_context=add_to_context,

        )



    async def prompt(

        self,

        content: str,

        *,

        streaming_behavior: StreamingBehavior | None = None,

    ) -> AsyncIterator[AgentEvent]:

        """Append a user prompt, run the agent, and persist new messages."""

        get_default_registry().dispatch_event("before_prompt", {"session": self, "prompt": content})

        context = self._diagnostic_context()

        try:

            expanded_content = self.expand_prompt_text(content)

        except ResourceError:

            raise

        except Exception as exc:

            self._last_diagnostic_log_path = self._diagnostic_logger.log_exception(

                context=context,

                phase="expand_prompt",

                exc=exc,

            )

            raise



        if self._harness.is_running:

            if streaming_behavior == "steer":

                yield self._harness.steer(expanded_content)

                return

            if streaming_behavior == "follow_up":

                yield self._harness.follow_up(expanded_content)

                return

            raise RuntimeError(

                "CodingSession is already running; pass streaming_behavior to queue a message."

            )



        await self._try_auto_compact(context=context, phase="auto_compact_before_prompt")

        persisted_count = len(self._harness.messages)

        overflow_event: ErrorEvent | None = None

        try:

            events = self._harness.prompt(expanded_content)

            self._invalidate_context_usage_cache()

            async for event in events:

                if isinstance(event, MessageEndEvent):

                    persisted_count = await self._persist_messages_since(persisted_count)

                if isinstance(event, ToolExecutionEndEvent):

                    self._invalidate_context_usage_cache()

                if isinstance(event, ErrorEvent) and not event.recoverable:

                    self._last_diagnostic_log_path = self._diagnostic_logger.log_error_event(

                        context=context,

                        phase="agent_loop",

                        event=event,

                    )

                    if _is_context_overflow_error(event):

                        overflow_event = event

                yield event

            persisted_count = await self._persist_messages_since(persisted_count)

            if overflow_event is not None:

                compacted = await self._try_overflow_compact(context=context)

                if compacted:

                    retry_persisted_count = len(self._harness.messages)

                    retry_events = self._harness.continue_()

                    self._invalidate_context_usage_cache()

                    async for retry_event in retry_events:

                        if isinstance(retry_event, MessageEndEvent):

                            retry_persisted_count = await self._persist_messages_since(

                                retry_persisted_count

                            )

                        if isinstance(retry_event, ToolExecutionEndEvent):

                            self._invalidate_context_usage_cache()

                        if isinstance(retry_event, ErrorEvent) and not retry_event.recoverable:

                            self._last_diagnostic_log_path = (

                                self._diagnostic_logger.log_error_event(

                                    context=context,

                                    phase="agent_loop_retry",

                                    event=retry_event,

                                )

                            )

                        yield retry_event

                    await self._persist_messages_since(retry_persisted_count)

                return

            await self._try_auto_compact(context=context, phase="auto_compact_after_prompt")

            await self._auto_name_session(expanded_content)

            get_default_registry().dispatch_event("after_prompt", {"session": self, "prompt": expanded_content})

        except Exception as exc:

            self._last_diagnostic_log_path = self._diagnostic_logger.log_exception(

                context=context,

                phase="agent_loop",

                exc=exc,

            )

            raise



    async def continue_(self) -> AsyncIterator[AgentEvent]:

        """Continue the agent from restored state and persist new messages."""

        context = self._diagnostic_context()

        persisted_count = len(self._harness.messages)

        try:

            events = self._harness.continue_()

            self._invalidate_context_usage_cache()

            async for event in events:

                if isinstance(event, MessageEndEvent):

                    persisted_count = await self._persist_messages_since(persisted_count)

                if isinstance(event, ToolExecutionEndEvent):

                    self._invalidate_context_usage_cache()

                if isinstance(event, ErrorEvent) and not event.recoverable:

                    self._last_diagnostic_log_path = self._diagnostic_logger.log_error_event(

                        context=context,

                        phase="agent_loop",

                        event=event,

                    )

                yield event

            await self._persist_messages_since(persisted_count)

            await self._try_auto_compact(context=context, phase="auto_compact_after_continue")

        except Exception as exc:

            self._last_diagnostic_log_path = self._diagnostic_logger.log_exception(

                context=context,

                phase="agent_loop",

                exc=exc,

            )

            raise



    def _diagnostic_context(self) -> AgentCallDiagnosticContext:

        return AgentCallDiagnosticContext(

            provider_name=self._provider_name,

            model=self.model,

            cwd=self.cwd,

            session_id=self.session_id,

            run_id=new_agent_call_run_id(),

        )







    def _invalidate_context_usage_cache(self) -> None:

        """Mark context accounting dirty after transcript/system/tool changes."""

        self._context_usage_cache = None








# ---------------------------------------------------------------------------
# Re-exports from extracted modules
# ---------------------------------------------------------------------------
from tau_coding.session_export import _storage_path, _resolve_export_destination, _session_export_title
from tau_coding.session_provider import (
    _coerced_thinking_level,
    _default_thinking_level_for_active_model,
    _initial_model_for_config,
    _initial_thinking_level_for_config,
    _preferred_thinking_level_for_model,
    _provider_config_for_name,
    _runtime_model_for_state,
    _state_thinking_level,
    _unavailable_thinking_message,
)
from tau_coding.session_harness import _harness_filtered_tools, _harness_system_prompt
