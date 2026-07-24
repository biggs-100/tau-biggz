"""Integration tests for tool-call execution through CodingSession."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_agent import AssistantMessage, ToolResultMessage, UserMessage
from tau_agent.messages import TextContent
from tests.integration.helpers import tool_call_stream


def _msg_text(m: ToolResultMessage) -> str:
    return "".join(b.text for b in m.content if isinstance(b, TextContent))


@pytest.mark.anyio
async def test_write_tool_creates_file(
    coding_session_factory,
    tmp_path: Path,
) -> None:
    """Write tool call produces a file on disk and correct message types."""

    streams = tool_call_stream(
        tool_name="write",
        tool_args={"path": "test.txt", "content": "hello"},
        text="File written.",
    )
    session = await coding_session_factory(streams)

    async for _event in session.prompt("Write hello.txt"):
        pass

    # File exists with content
    assert (tmp_path / "test.txt").read_text() == "hello"

    # Message order includes key types
    msg_types = [type(m) for m in session.messages]
    assert UserMessage in msg_types
    assert AssistantMessage in msg_types
    assert ToolResultMessage in msg_types

    # Tool result has matching ID
    result = [m for m in session.messages if isinstance(m, ToolResultMessage)][0]
    assert result.tool_call_id == "call-1"
    assert "success" in _msg_text(result).lower() or _msg_text(result).strip()


@pytest.mark.anyio
async def test_read_tool_reads_existing_file(
    coding_session_factory,
    tmp_path: Path,
) -> None:
    """Read tool returns content of an existing file."""

    (tmp_path / "hello.txt").write_text("world")
    streams = tool_call_stream(
        tool_name="read",
        tool_args={"path": "hello.txt"},
        text="File content read.",
    )
    session = await coding_session_factory(streams)

    async for _event in session.prompt("Read hello.txt"):
        pass

    result = [m for m in session.messages if isinstance(m, ToolResultMessage)][0]
    assert "world" in _msg_text(result)


@pytest.mark.anyio
async def test_edit_tool_modifies_file(
    coding_session_factory,
    tmp_path: Path,
) -> None:
    """Edit tool modifies file content in-place."""

    (tmp_path / "file.txt").write_text("aaa\nbbb\nccc")
    streams = tool_call_stream(
        tool_name="edit",
        tool_args={"path": "file.txt", "oldText": "bbb", "newText": "BBB"},
        text="File edited.",
    )
    session = await coding_session_factory(streams)

    async for _event in session.prompt("Edit file.txt"):
        pass

    assert (tmp_path / "file.txt").read_text() == "aaa\nBBB\nccc"


@pytest.mark.anyio
async def test_bash_tool_prints_output(
    coding_session_factory,
    tmp_path: Path,
) -> None:
    """Bash tool executes a command and returns output."""

    streams = tool_call_stream(
        tool_name="bash",
        tool_args={"command": "echo hello"},
        text="Command executed.",
    )
    session = await coding_session_factory(streams)

    async for _event in session.prompt("Run echo"):
        pass

    result = [m for m in session.messages if isinstance(m, ToolResultMessage)][0]
    assert "hello" in _msg_text(result)
