"""Stream pattern helpers for integration tests.

These are shared helper functions (not fixtures) used by multiple test files.
"""

from __future__ import annotations

from tau_agent.messages import AssistantMessage
from tau_agent.provider_events import (
    AssistantDoneEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from tau_agent.tools import ToolCall


def text_stream(content: str) -> list[AssistantMessageEvent]:
    """Build a text-only provider stream (Pattern A)."""
    chunks = _chunk_text(content)
    events: list[AssistantMessageEvent] = [
        AssistantStartEvent(partial=AssistantMessage(content="")),
    ]
    for chunk in chunks:
        events.append(TextDeltaEvent(content_index=0, delta=chunk))
    events.append(
        AssistantDoneEvent(
            message=AssistantMessage(content=content),
            reason="stop",
        ),
    )
    return events


def tool_call_stream(
    tool_name: str,
    tool_args: dict[str, object],
    text: str,
) -> list[list[AssistantMessageEvent]]:
    """Build a tool-call -> text provider stream (Pattern B, two turns).

    The first stream produces a tool-call response.
    The second stream produces a plain-text response.
    """
    tool_call = ToolCall(
        id="call-1",
        name=tool_name,
        arguments=tool_args,
    )
    stream1: list[AssistantMessageEvent] = [
        AssistantStartEvent(partial=AssistantMessage(content="")),
        ToolCallDeltaEvent(content_index=0, partial=tool_call),
        AssistantDoneEvent(
            message=AssistantMessage(content="", tool_calls=[tool_call]),
            reason="tool_calls",
        ),
    ]
    stream2 = text_stream(text)
    return [stream1, stream2]


def _chunk_text(text: str) -> list[str]:
    """Split text into small delta chunks for realistic streaming."""
    if len(text) <= 3:
        return [text]
    mid = len(text) // 2
    return [text[:mid], text[mid:]]
