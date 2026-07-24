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
    """Provider that replays scripted Pi events for testing.

    Accepts either a flat sequence of events (single batch) or a sequence
    of sequences (one batch per ``stream_response`` call) to support
    multi-turn loops.
    """

    def __init__(self, scripted_events: Sequence[AssistantMessageEvent] | Sequence[Sequence[AssistantMessageEvent]]) -> None:
        events = list(scripted_events)
        if events and isinstance(events[0], (list, tuple)):
            self._batches = [list(b) for b in events]  # type: ignore[union-attr]
        else:
            self._batches = [events]
        self._batch_index = 0
        self._calls: list[tuple] = []

    @property
    def calls(self) -> list[tuple]:
        return list(self._calls)

    async def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list,
        tools: list,
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        self._calls.append((model, system, list(messages), list(tools), signal))
        batch: list[AssistantMessageEvent] = []
        if self._batch_index < len(self._batches):
            batch = self._batches[self._batch_index]
            self._batch_index += 1
        for event in batch:
            yield event
