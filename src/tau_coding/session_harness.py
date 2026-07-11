"""Harness helper functions extracted from session.py."""

from __future__ import annotations

from typing import Any

from tau_agent.tools import AgentTool
from tau_coding.session_models import CodingSessionConfig


def _harness_filtered_tools(config: CodingSessionConfig) -> list[AgentTool]:
    """Return tools filtered by the active harness."""

    from tau_coding.extensions import get_default_registry
    from tau_coding.harness import get_active_harness
    from tau_coding.tools import create_coding_tools

    harness = get_active_harness()

    all_tools = create_coding_tools(
        cwd=config.cwd,
        shell_command_prefix=config.shell_command_prefix,
        extension_tools=get_default_registry().get_tools(),
        approval=harness.approval,
    )

    if harness.name == "coding":
        return all_tools

    allowed = set(harness.tools.builtin)

    if not allowed:
        return all_tools

    return [t for t in all_tools if t.name in allowed]


def _harness_system_prompt(
    config: CodingSessionConfig,
    tools: list[AgentTool],
    resources: Any,
) -> str:
    """Build system prompt using harness personality."""

    from tau_coding.harness import get_active_harness
    from tau_coding.system_prompt import BuildSystemPromptOptions, build_system_prompt

    harness = get_active_harness()

    custom_prompt = config.custom_system_prompt

    if harness.name != "coding" and harness.personality.system_prompt:
        custom_prompt = harness.personality.system_prompt

    return build_system_prompt(
        BuildSystemPromptOptions(
            cwd=config.cwd,
            tools=tools,
            skills=resources.skills,
            custom_prompt=custom_prompt,
            append_system_prompt=config.append_system_prompt,
            context_files=resources.context_files,
        )
    )
