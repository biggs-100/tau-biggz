"""Message models with block-based content (Pi-compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tau_agent.tools import ToolCall
from tau_agent.types import JSONValue


# ── Content blocks ──────────────────────────────────────────────

@dataclass
class TextContent:
    text: str
    text_signature: str | None = None


@dataclass
class ThinkingContent:
    thinking: str
    thinking_signature: str | None = None
    redacted: bool = False


@dataclass
class ImageContent:
    image_url: str | None = None
    image_data: str | None = None
    mime_type: str = "image/png"


AssistantContent = TextContent | ThinkingContent | ToolCall
ToolResultContent = TextContent | ImageContent
UserContent = str | list[TextContent | ImageContent]


# ── Core Message Types ─────────────────────────────────────────

@dataclass
class UserMessage:
    role: Literal["user"] = "user"
    content: UserContent = ""


@dataclass
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    content: list[AssistantContent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.content, str):
            self.content = [TextContent(text=self.content)]

    @property
    def text(self) -> str:
        return "".join(
            block.text for block in self.content
            if isinstance(block, TextContent)
        )

    @property
    def thinking_text(self) -> str:
        return "".join(
            block.thinking for block in self.content
            if isinstance(block, ThinkingContent)
        )

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [block for block in self.content if isinstance(block, ToolCall)]


@dataclass
class ToolResultMessage:
    role: Literal["toolResult"] = "toolResult"
    tool_name: str = ""
    content: list[ToolResultContent] = field(default_factory=list)
    is_error: bool = False
    tool_call_id: str = ""
    details: JSONValue = None

    def __post_init__(self) -> None:
        if isinstance(self.content, str):
            self.content = [TextContent(text=self.content)]


@dataclass
class CustomMessage:
    role: str = "custom"
    content: str = ""


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | CustomMessage
