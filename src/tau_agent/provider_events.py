"""Provider-level assistant stream events (Pi-compatible)."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Literal

from tau_agent.messages import AssistantMessage, ToolCall
from tau_agent.types import JSONValue


class _ProviderEventMixin:
    def model_dump(self) -> dict:
        return dataclasses.asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), default=str)


@dataclass
class AssistantStartEvent(_ProviderEventMixin):
    """Stream begins."""
    partial: AssistantMessage
    type: Literal["assistant_start"] = "assistant_start"

@dataclass
class TextStartEvent(_ProviderEventMixin):
    """Text block begins."""
    content_index: int
    type: Literal["text_start"] = "text_start"

@dataclass
class TextDeltaEvent(_ProviderEventMixin):
    """Text block delta."""
    content_index: int
    delta: str
    type: Literal["text_delta"] = "text_delta"

@dataclass
class TextEndEvent(_ProviderEventMixin):
    """Text block ends."""
    content_index: int
    type: Literal["text_end"] = "text_end"

@dataclass
class ThinkingStartEvent(_ProviderEventMixin):
    """Thinking block begins."""
    content_index: int
    type: Literal["thinking_start"] = "thinking_start"

@dataclass
class ThinkingDeltaEvent(_ProviderEventMixin):
    """Thinking block delta."""
    content_index: int
    delta: str
    type: Literal["thinking_delta"] = "thinking_delta"

@dataclass
class ThinkingEndEvent(_ProviderEventMixin):
    """Thinking block ends."""
    content_index: int
    type: Literal["thinking_end"] = "thinking_end"

@dataclass
class ToolCallStartEvent(_ProviderEventMixin):
    """Tool call block begins."""
    content_index: int
    type: Literal["tool_call_start"] = "tool_call_start"

@dataclass
class ToolCallDeltaEvent(_ProviderEventMixin):
    """Tool call block delta (partial snapshot)."""
    content_index: int
    partial: ToolCall
    type: Literal["tool_call_delta"] = "tool_call_delta"

@dataclass
class ToolCallEndEvent(_ProviderEventMixin):
    """Tool call block ends."""
    content_index: int
    type: Literal["tool_call_end"] = "tool_call_end"

@dataclass
class AssistantDoneEvent(_ProviderEventMixin):
    """Stream completed successfully."""
    type: Literal["assistant_done"] = "assistant_done"
    reason: str = "end_turn"
    message: AssistantMessage | None = None

@dataclass
class AssistantErrorEvent(_ProviderEventMixin):
    """Stream terminated with error."""
    type: Literal["assistant_error"] = "assistant_error"
    reason: str = "error"
    error: AssistantMessage | None = None


AssistantMessageEvent = (
    AssistantStartEvent
    | TextStartEvent | TextDeltaEvent | TextEndEvent
    | ThinkingStartEvent | ThinkingDeltaEvent | ThinkingEndEvent
    | ToolCallStartEvent | ToolCallDeltaEvent | ToolCallEndEvent
    | AssistantDoneEvent | AssistantErrorEvent
)
