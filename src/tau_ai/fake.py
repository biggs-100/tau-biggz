"""Fake provider for testing — emits Pi-compatible AssistantMessageEvent."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from tau_agent.messages import AssistantMessage, TextContent, ToolCall
from tau_agent.provider import CancellationToken, ModelProvider
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


class FakeProvider(ModelProvider):
    """Provider that replays scripted Pi events for testing."""

    def __init__(self, scripted_events: Sequence[AssistantMessageEvent]) -> None:
        self._scripted = list(scripted_events)

    async def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list,
        tools: list,
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        for event in self._scripted:
            yield event
