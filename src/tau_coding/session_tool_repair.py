"""Tool-repair helper for interrupted tool calls."""

from __future__ import annotations

from tau_agent.messages import AgentMessage, AssistantMessage, TextContent, ToolResultMessage


def _interrupted_tool_repair_plan(
    messages: tuple[AgentMessage, ...],
    *,
    context_entry_ids: tuple[str, ...],
) -> tuple[str, tuple[AgentMessage, ...]] | None:
    repaired: list[AgentMessage] = []
    returned_ids = {
        message.tool_call_id for message in messages if isinstance(message, ToolResultMessage)
    }
    for message in messages:
        repaired.append(message)
        if not isinstance(message, AssistantMessage):
            continue
        for tool_call in message.tool_calls:
            if tool_call.id in returned_ids:
                continue
            returned_ids.add(tool_call.id)
            content = "Tool call interrupted by user"
            repaired.append(
                ToolResultMessage(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    content=[TextContent(text=content)],
                    is_error=True,
                )
            )

    if tuple(repaired) == messages:
        return None

    common_prefix_length = 0
    for old_message, repaired_message in zip(messages, repaired, strict=False):
        if old_message != repaired_message:
            break
        common_prefix_length += 1

    if common_prefix_length == 0:
        return None

    return context_entry_ids[common_prefix_length - 1], tuple(repaired[common_prefix_length:])
