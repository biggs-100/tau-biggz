"""Provider-neutral tool definitions and tool execution results."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from tau_agent.types import JSONValue


@dataclass
class ToolCall:
    """A request from the assistant to execute a named tool."""

    id: str
    name: str
    arguments: dict[str, JSONValue] = field(default_factory=dict)
    thought_signature: str | None = None

    def model_dump(self) -> dict:
        return dataclasses.asdict(self)


class ToolCancellationToken(Protocol):
    """Minimal cancellation interface accepted by tools."""

    def is_cancelled(self) -> bool:
        """Return whether tool execution should stop."""
        ...


class ToolExecutor(Protocol):
    """Async callable used to execute a tool."""

    def __call__(
        self,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> Awaitable[AgentToolResult]:
        """Execute the tool with optional cancellation support."""
        ...


@dataclass
class AgentToolResult:
    """Structured result returned by a tool execution."""

    content: list = field(default_factory=list)
    details: JSONValue = None
    added_tool_names: tuple[str, ...] = ()
    terminate: bool = False
    tool_call_id: str = ""
    name: str = ""
    ok: bool = True
    error: str | None = None

    def model_dump(self) -> dict:
        return dataclasses.asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), default=str)


@dataclass(frozen=True, slots=True)
class AgentTool:
    """A tool that can be exposed to an agent loop."""

    name: str
    description: str
    input_schema: Mapping[str, JSONValue]
    executor: ToolExecutor
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] = ()

    async def execute(
        self,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        """Execute the tool with provider-neutral JSON-like arguments."""
        return await self.executor(arguments, signal=signal)
