"""Canonicalize provider streams to Pi-compatible assistant events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from tau_agent.messages import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCall,
)
from tau_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent as PiTextDeltaEvent,
    TextEndEvent as PiTextEndEvent,
    TextStartEvent as PiTextStartEvent,
    ThinkingDeltaEvent as PiThinkingDeltaEvent,
    ThinkingEndEvent as PiThinkingEndEvent,
    ThinkingStartEvent as PiThinkingStartEvent,
    ToolCallDeltaEvent as PiToolCallDeltaEvent,
    ToolCallEndEvent as PiToolCallEndEvent,
    ToolCallStartEvent as PiToolCallStartEvent,
)
from tau_ai._provider_events import (
    ProviderErrorEvent,
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderRetryEvent,
    ProviderTextDeltaEvent,
    ProviderThinkingDeltaEvent,
    ProviderToolCallEvent,
)


async def canonicalize_provider_stream(
    raw: AsyncIterator[ProviderEvent],
) -> AsyncIterator[AssistantMessageEvent]:
    """Wrap a v1 ProviderEvent stream and yield Pi-compatible AssistantMessageEvent."""

    content_index = 0
    thinking_texts: list[str] = []
    text_texts: list[str] = []
    tool_calls: list[ToolCall] = []
    current_thinking = False
    content_emitted = False

    async for event in raw:
        if isinstance(event, ProviderResponseStartEvent):
            content_index = 0
            thinking_texts = []
            text_texts = []
            tool_calls = []
            current_thinking = False
            content_emitted = False
            yield AssistantStartEvent(
                partial=AssistantMessage(content=[])
            )

        elif isinstance(event, ProviderThinkingDeltaEvent):
            if not current_thinking and content_emitted:
                pass
            if not current_thinking:
                yield PiThinkingStartEvent(content_index=content_index)
                current_thinking = True
            thinking_texts.append(event.delta)
            yield PiThinkingDeltaEvent(content_index=content_index, delta=event.delta)

        elif isinstance(event, ProviderTextDeltaEvent):
            if current_thinking:
                yield PiThinkingEndEvent(content_index=content_index)
                current_thinking = False
                content_index += 1
                yield PiTextStartEvent(content_index=content_index)
            elif not content_emitted:
                yield PiTextStartEvent(content_index=content_index)
            text_texts.append(event.delta)
            content_emitted = True
            yield PiTextDeltaEvent(content_index=content_index, delta=event.delta)

        elif isinstance(event, ProviderToolCallEvent):
            if current_thinking:
                yield PiThinkingEndEvent(content_index=content_index)
                current_thinking = False
                content_index += 1
            yield PiToolCallStartEvent(content_index=content_index)
            tool_calls.append(event.tool_call)
            content_emitted = True
            yield PiToolCallDeltaEvent(
                content_index=content_index,
                partial=event.tool_call,
            )
            yield PiToolCallEndEvent(content_index=content_index)
            content_index += 1

        elif isinstance(event, ProviderResponseEndEvent):
            if current_thinking:
                yield PiThinkingEndEvent(content_index=content_index)
            elif content_emitted:
                yield PiTextEndEvent(content_index=content_index)

            blocks: list = []
            if text_texts:
                blocks.append(TextContent(text="".join(text_texts)))
            if thinking_texts:
                blocks.append(ThinkingContent(thinking="".join(thinking_texts)))
            for tc in tool_calls:
                blocks.append(tc)

            msg = AssistantMessage(content=blocks)
            yield AssistantDoneEvent(reason=event.finish_reason or "end_turn", message=msg)

        elif isinstance(event, ProviderErrorEvent):
            if current_thinking:
                yield PiThinkingEndEvent(content_index=content_index)
            yield AssistantErrorEvent(
                reason="error",
                error=AssistantMessage(content=[TextContent(text=event.message)]),
            )

        elif isinstance(event, ProviderRetryEvent):
            continue

    if current_thinking:
        yield PiThinkingEndEvent(content_index=content_index)
