"""Agent-level events (Pi-compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tau_agent.messages import AgentMessage
from tau_agent.provider_events import AssistantMessageEvent
from tau_agent.tools import AgentToolResult, ToolCall
from tau_agent.types import JSONValue


@dataclass
class AgentStartEvent:
    pass


@dataclass
class AgentEndEvent:
    messages: list[AgentMessage] = field(default_factory=list)


@dataclass
class TurnStartEvent:
    pass


@dataclass
class TurnEndEvent:
    message: AgentMessage | None = None
    tool_results: list = field(default_factory=list)


@dataclass
class MessageStartEvent:
    message: AgentMessage | None = None


@dataclass
class MessageUpdateEvent:
    message: AgentMessage | None = None
    assistant_message_event: AssistantMessageEvent | None = None


@dataclass
class MessageEndEvent:
    message: AgentMessage | None = None


@dataclass
class ToolExecutionStartEvent:
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, JSONValue] = field(default_factory=dict)


@dataclass
class ToolExecutionUpdateEvent:
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, JSONValue] = field(default_factory=dict)
    partial_result: AgentToolResult | None = None


@dataclass
class ToolExecutionEndEvent:
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
class ErrorEvent:
    type: Literal["error"] = "error"
    message: str = ""
    recoverable: bool = False
    data: JSONValue = None


@dataclass
class QueueUpdateEvent:
    type: Literal["queue_update"] = "queue_update"
    steering: tuple[str, ...] = ()
    follow_up: tuple[str, ...] = ()


@dataclass
class RetryEvent:
    type: Literal["retry"] = "retry"
    attempt: int = 0
    max_attempts: int = 0
    delay_seconds: float = 0.0
    message: str = ""
    data: JSONValue = None


@dataclass
class ThinkingDeltaEvent:
    type: Literal["thinking_delta"] = "thinking_delta"
    delta: str = ""


@dataclass
class MessageDeltaEvent:
    type: Literal["message_delta"] = "message_delta"
    delta: str = ""
