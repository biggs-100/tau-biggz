"""Stream pattern helpers for integration tests.

These are shared helper functions (not fixtures) used by multiple test files.
"""

from __future__ import annotations

from tau_agent.messages import AssistantMessage
from tau_agent.tools import ToolCall
from tau_ai.events import (
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderTextDeltaEvent,
)


def text_stream(content: str) -> list[ProviderEvent]:
    """Build a text-only provider stream (Pattern A)."""
    return [
        ProviderResponseStartEvent(model="fake"),
        *[ProviderTextDeltaEvent(delta=chunk) for chunk in _chunk_text(content)],
        ProviderResponseEndEvent(
            message=AssistantMessage(content=content),
            finish_reason="stop",
        ),
    ]


def tool_call_stream(
    tool_name: str,
    tool_args: dict[str, object],
    text: str,
) -> list[list[ProviderEvent]]:
    """Build a tool-call → text provider stream (Pattern B, two turns).

    The first stream produces a tool-call response.
    The second stream produces a plain-text response.
    """
    tool_call = ToolCall(
        id="call-1",
        name=tool_name,
        arguments=tool_args,
    )
    stream1: list[ProviderEvent] = [
        ProviderResponseStartEvent(model="fake"),
        ProviderResponseEndEvent(
            message=AssistantMessage(
                content="",
                tool_calls=[tool_call],
            ),
            finish_reason="tool_calls",
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
