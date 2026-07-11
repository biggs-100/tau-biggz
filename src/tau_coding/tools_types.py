"""Shared types, constants, and dataclasses for Tau coding tools.

Extracted from tools.py to reduce module size.

This module provides tool-related data types used across the coding-tool
subsystem: constants for output limits, a custom exception for invalid tool
arguments, the structured ``TruncationResult`` and ``ToolDefinition``
dataclasses, and the module-level file-lock dict.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from tau_agent.tools import AgentTool, ToolExecutor
from tau_agent.types import JSONValue

DEFAULT_MAX_OUTPUT_BYTES = 50 * 1024
DEFAULT_MAX_OUTPUT_LINES = 2_000
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
UTF8_BOM = "\ufeff"


class ToolInputError(ValueError):
    """Raised when a tool receives invalid structured arguments."""


@dataclass(frozen=True, slots=True)
class TruncationResult:
    """Metadata describing how a tool output was shortened.

    ``content`` contains the returned slice. The remaining fields record whether
    truncation happened, whether the line or byte limit was responsible, the
    total size of the original output, the size of the returned output, and
    edge cases such as partial-line output or a first line that is too large to
    display safely.
    """

    content: str
    truncated: bool
    truncated_by: str | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int
    last_line_partial: bool
    first_line_exceeds_limit: bool
    max_lines: int
    max_bytes: int

    def to_json(self) -> dict[str, JSONValue]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Complete definition for a coding tool before provider conversion.

    A definition contains the tool name, user-facing description, prompt
    metadata, JSON input schema, and async executor. ``to_agent_tool()`` converts
    it into the smaller ``AgentTool`` type consumed by the provider-neutral agent
    loop while preserving prompt metadata for clients that render tool guidance.
    """

    name: str
    description: str
    prompt_snippet: str
    prompt_guidelines: tuple[str, ...]
    input_schema: Mapping[str, JSONValue]
    executor: ToolExecutor

    def to_agent_tool(self) -> AgentTool:
        return AgentTool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            executor=self.executor,
            prompt_snippet=self.prompt_snippet,
            prompt_guidelines=self.prompt_guidelines,
        )


_file_locks: dict[Path, asyncio.Lock] = {}
