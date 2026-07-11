"""Data types used throughout the coding session subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tau_agent.messages import AgentMessage
from tau_agent.session import SessionStorage
from tau_agent.tools import AgentTool
from tau_ai import ModelProvider
from tau_coding.commands import CommandRegistry
from tau_coding.harness import SandboxConfig
from tau_coding.prompt_templates import PromptTemplate
from tau_coding.provider_config import ProviderConfig, ProviderSettings
from tau_coding.resources import ResourceDiagnostic, TauResourcePaths
from tau_coding.session_manager import SessionManager
from tau_coding.skills import Skill
from tau_coding.system_prompt import ProjectContextFile
from tau_coding.thinking import DEFAULT_THINKING_LEVEL, ThinkingLevel

StreamingBehavior = Literal["steer", "follow_up"]


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """A selectable model and the provider that serves it."""

    provider_name: str
    model: str


@dataclass(frozen=True, slots=True)
class TerminalCommandResult:
    """Result of an input-bar terminal command."""

    command: str
    output: str
    exit_code: int | None
    ok: bool
    added_to_context: bool


@dataclass(frozen=True, slots=True)
class SessionTreeChoice:
    """One branchable entry in the active session tree."""

    entry_id: str
    label: str
    active: bool = False
    is_tool_call: bool = False


@dataclass(frozen=True, slots=True)
class SessionTreeBranchResult:
    """Result of moving the active session tree leaf."""

    message: str
    input_prefill: str | None = None


@dataclass(frozen=True, slots=True)
class TerminalCommandRequest:
    """Parsed input-bar terminal command request."""

    command: str
    add_to_context: bool


@dataclass(frozen=True, slots=True)
class SessionResources:
    """Tau-owned resources loaded around a coding session."""

    skills: tuple[Skill, ...]
    prompt_templates: tuple[PromptTemplate, ...]
    context_files: tuple[ProjectContextFile, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """Prepared active-context entries for a compaction run."""

    replace_entry_ids: tuple[str, ...]
    messages_to_summarize: tuple[AgentMessage, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionConfig:
    """Configuration for a persistent coding session."""

    provider: ModelProvider
    model: str
    storage: SessionStorage
    cwd: Path
    system: str | None = None
    custom_system_prompt: str | None = None
    append_system_prompt: str | None = None
    context_files: tuple[ProjectContextFile, ...] = ()
    tools: list[AgentTool] | None = None
    resource_paths: TauResourcePaths | None = None
    session_id: str | None = None
    session_manager: SessionManager | None = None
    command_registry: CommandRegistry | None = None
    provider_name: str = "openai"
    provider_settings: ProviderSettings | None = None
    runtime_provider_config: ProviderConfig | None = None
    auto_compact_token_threshold: int | None = None
    auto_compact_enabled: bool = True
    thinking_level: ThinkingLevel = DEFAULT_THINKING_LEVEL
    index_on_first_persist: bool = False
    shell_command_prefix: str | None = None
    sandbox_config: SandboxConfig | None = None
