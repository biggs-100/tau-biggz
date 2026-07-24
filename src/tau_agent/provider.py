"""Provider protocol returning Pi-compatible events."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from tau_agent.messages import AgentMessage
from tau_agent.provider_events import AssistantMessageEvent
from tau_agent.tools import AgentTool


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool:
        return False


class ModelProvider(Protocol):
    async def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        ...
