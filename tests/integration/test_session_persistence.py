"""Integration tests for JSONL session persistence round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_agent.messages import AssistantMessage, ToolResultMessage, UserMessage
from tau_agent.session import JsonlSessionStorage, MessageEntry
from tau_agent.tools import AgentTool
from tau_ai import FakeProvider
from tau_coding.session import CodingSession, CodingSessionConfig
from tests.integration.helpers import tool_call_stream


@pytest.mark.anyio
async def test_multi_turn_persistence(
    coding_session_factory,
    session_storage: JsonlSessionStorage,
) -> None:
    """Pattern B session persists entry types and roles."""

    streams = tool_call_stream(
        tool_name="bash",
        tool_args={"command": "echo persisted"},
        text="Done.",
    )
    session = await coding_session_factory(streams, storage=session_storage)

    async for _event in session.prompt("Run command"):
        pass

    entries = await session_storage.read_all()
    entry_types = [e.type for e in entries]
    assert "session_info" in entry_types
    assert "message" in entry_types
    assert "leaf" in entry_types

    # Verify message roles
    msg_entries = [e for e in entries if isinstance(e, MessageEntry)]
    roles = [e.message.role for e in msg_entries]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles


@pytest.mark.anyio
async def test_reload_from_storage(
    coding_session_factory,
    session_storage: JsonlSessionStorage,
    tmp_path: Path,
    tools: list[AgentTool],
) -> None:
    """Session messages survive round-trip through JSONL storage."""

    # First session
    streams = tool_call_stream(
        tool_name="write",
        tool_args={"path": "persisted.txt", "content": "round-trip"},
        text="Written.",
    )
    session1 = await coding_session_factory(streams, storage=session_storage)
    async for _event in session1.prompt("Write file"):
        pass
    await session1.aclose()

    original_messages = list(session1.messages)

    # Reload from same storage
    session2 = await CodingSession.load(
        CodingSessionConfig(
            provider=FakeProvider([]),
            model="fake",
            cwd=tmp_path,
            storage=session_storage,
            tools=tools,
            provider_name="openai",
        )
    )

    assert len(session2.messages) == len(original_messages)
    for m1, m2 in zip(original_messages, session2.messages):
        assert type(m1) is type(m2)
        assert m1.role == m2.role
