"""Agent-level events (Pi-compatible)."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Literal

from tau_agent.messages import AgentMessage
from tau_agent.provider_events import AssistantMessageEvent
from tau_agent.tools import AgentToolResult, ToolCall
from tau_agent.types import JSONValue


class _EventMixin:
    def model_dump(self) -> dict:
        return dataclasses.asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), default=str)


@dataclass
class AgentStartEvent(_EventMixin):
    type: Literal["agent_start"] = "agent_start"


@dataclass
class AgentEndEvent(_EventMixin):
    type: Literal["agent_end"] = "agent_end"
    messages: list[AgentMessage] = field(default_factory=list)


@dataclass
class TurnStartEvent(_EventMixin):
    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEndEvent(_EventMixin):
    type: Literal["turn_end"] = "turn_end"
    message: AgentMessage | None = None
    tool_results: list = field(default_factory=list)


@dataclass
class MessageStartEvent(_EventMixin):
    type: Literal["message_start"] = "message_start"
    message: AgentMessage | None = None


@dataclass
class MessageEndEvent(_EventMixin):
    type: Literal["message_end"] = "message_end"
    message: AgentMessage | None = None


@dataclass
class MessageUpdateEvent(_EventMixin):
    type: Literal["message_update"] = "message_update"
    message: AgentMessage | None = None
    assistant_message_event: AssistantMessageEvent | None = None


@dataclass
class ToolExecutionStartEvent(_EventMixin):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, JSONValue] = field(default_factory=dict)


@dataclass
class ToolExecutionUpdateEvent(_EventMixin):
    type: Literal["tool_execution_update"] = "tool_execution_update"
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, JSONValue] = field(default_factory=dict)
    partial_result: AgentToolResult | None = None


@dataclass
class ToolExecutionEndEvent(_EventMixin):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str = ""
    tool_name: str = ""
    result: AgentToolResult | None = None
    is_error: bool = False


AgentEvent = (
    AgentStartEvent | AgentEndEvent
    | TurnStartEvent | TurnEndEvent
    | MessageStartEvent | MessageUpdateEvent | MessageEndEvent
    | ToolExecutionStartEvent | ToolExecutionUpdateEvent | ToolExecutionEndEvent
)


# ── Backward-compat aliases (removed from AgentEvent union in Wave 1) ────

@dataclass
class ErrorEvent(_EventMixin):
    type: Literal["error"] = "error"
    message: str = ""
    recoverable: bool = False
    data: JSONValue = None


@dataclass
class QueueUpdateEvent(_EventMixin):
    type: Literal["queue_update"] = "queue_update"
    steering: tuple[str, ...] = ()
    follow_up: tuple[str, ...] = ()


@dataclass
class RetryEvent(_EventMixin):
    type: Literal["retry"] = "retry"
    attempt: int = 0
    max_attempts: int = 0
    delay_seconds: float = 0.0
    message: str = ""
    data: JSONValue = None


@dataclass
class ThinkingDeltaEvent(_EventMixin):
    type: Literal["thinking_delta"] = "thinking_delta"
    delta: str = ""


@dataclass
class MessageDeltaEvent(_EventMixin):
    type: Literal["message_delta"] = "message_delta"
    delta: str = ""
