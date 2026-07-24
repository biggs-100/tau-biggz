"""Message models with block-based content (Pi-compatible)."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Literal

from tau_agent.tools import ToolCall
from tau_agent.types import JSONValue


# ── Helpers ─────────────────────────────────────────────────────


def _ensure_content_list(
    content: list[AssistantContent] | str,
    tool_calls: list[ToolCall] | None = None,
    thinking_text: str | None = None,
) -> list[AssistantContent]:
    if isinstance(content, str):
        content = [TextContent(text=content)]
    content = list(content)
    if tool_calls:
        content.extend(tool_calls)
    if thinking_text:
        content.append(ThinkingContent(thinking=thinking_text))
    return content


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

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("UserMessage cannot be subclassed")

    def __init__(self, **kwargs: object) -> None:
        allowed = {"role", "content"}
        extra = set(kwargs) - allowed
        if extra:
            raise TypeError(f"UserMessage.__init__() got unexpected keyword arguments: {', '.join(sorted(extra))}")
        self.role = kwargs.get("role", "user")
        self.content = kwargs.get("content", "")

    def model_dump(self) -> dict:
        return {"role": self.role, "content": self.content}

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)

    @property
    def text(self) -> str:
        if isinstance(self.content, list):
            return "".join(
                block.text if isinstance(block, TextContent) else ""
                for block in self.content
            )
        return self.content


@dataclass
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    content: list[AssistantContent] = field(default_factory=list)

    def __init__(
        self,
        content: list[AssistantContent] | str = "",
        tool_calls: list[ToolCall] | None = None,
        thinking_text: str | None = None,
    ) -> None:
        self.content = _ensure_content_list(content, tool_calls=tool_calls, thinking_text=thinking_text)
        self.role = "assistant"

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

    def model_dump(self) -> dict:
        dumped: dict = {"role": self.role, "content": []}
        for block in self.content:
            if isinstance(block, ToolCall):
                if "tool_calls" not in dumped:
                    dumped["tool_calls"] = []
                dumped["tool_calls"].append(block.model_dump())
            elif isinstance(block, ThinkingContent) and block.thinking:
                dumped.setdefault("content", []).append(dataclasses.asdict(block))
            else:
                dumped.setdefault("content", []).append(dataclasses.asdict(block))
        if self.thinking_text:
            dumped["thinking_text"] = self.thinking_text
        return dumped

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)


@dataclass
class ToolResultMessage:
    role: Literal["tool", "toolResult"] = "tool"
    tool_name: str = ""
    content: list[ToolResultContent] = field(default_factory=list)
    is_error: bool = False
    tool_call_id: str = ""
    details: JSONValue = None
    name: str = ""
    ok: bool = True
    data: JSONValue = None
    error: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.content, str):
            self.content = [TextContent(text=self.content)]

    def model_dump(self) -> dict:
        return {
            "role": self.role,
            "tool_name": self.tool_name,
            "content": [dataclasses.asdict(b) for b in self.content],
            "is_error": self.is_error,
            "tool_call_id": self.tool_call_id,
            "details": self.details,
            "name": self.name,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
        }

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)


@dataclass
class CustomMessage:
    role: str = "custom"
    content: str = ""

    def model_dump(self) -> dict:
        return {"role": self.role, "content": self.content}

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | CustomMessage
