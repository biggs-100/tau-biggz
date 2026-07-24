"""Provider-level assistant stream events (Pi-compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tau_agent.messages import AssistantMessage, ToolCall
from tau_agent.types import JSONValue


@dataclass
class AssistantStartEvent:
    """Stream begins."""
    partial: AssistantMessage

@dataclass
class TextStartEvent:
    """Text block begins."""
    content_index: int

@dataclass
class TextDeltaEvent:
    """Text block delta."""
    content_index: int
    delta: str

@dataclass
class TextEndEvent:
    """Text block ends."""
    content_index: int

@dataclass
class ThinkingStartEvent:
    """Thinking block begins."""
    content_index: int

@dataclass
class ThinkingDeltaEvent:
    """Thinking block delta."""
    content_index: int
    delta: str

@dataclass
class ThinkingEndEvent:
    """Thinking block ends."""
    content_index: int

@dataclass
class ToolCallStartEvent:
    """Tool call block begins."""
    content_index: int

@dataclass
class ToolCallDeltaEvent:
    """Tool call block delta (partial snapshot)."""
    content_index: int
    partial: ToolCall

@dataclass
class ToolCallEndEvent:
    """Tool call block ends."""
    content_index: int

@dataclass
class AssistantDoneEvent:
    """Stream completed successfully."""
    reason: str = "end_turn"
    message: AssistantMessage | None = None

@dataclass
class AssistantErrorEvent:
    """Stream terminated with error."""
    reason: str = "error"
    error: AssistantMessage | None = None


AssistantMessageEvent = (
    AssistantStartEvent
    | TextStartEvent | TextDeltaEvent | TextEndEvent
    | ThinkingStartEvent | ThinkingDeltaEvent | ThinkingEndEvent
    | ToolCallStartEvent | ToolCallDeltaEvent | ToolCallEndEvent
    | AssistantDoneEvent | AssistantErrorEvent
)
