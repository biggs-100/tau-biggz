"""Integration tests for run_print_mode end-to-end."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_agent import AssistantMessage
from tau_agent.provider_events import (
    AssistantDoneEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
)
from tau_agent.tools import ToolCall
from tau_ai import FakeProvider
from tau_coding.cli import run_print_mode


@pytest.mark.anyio
async def test_print_mode_text_only(
    tmp_path: Path,
    capsys,
) -> None:
    """Pattern A: text-only stream prints output and returns True."""
    provider = FakeProvider([
        [
            AssistantStartEvent(partial=AssistantMessage(content="")),
            TextDeltaEvent(content_index=0, delta="Hello, "),
            TextDeltaEvent(content_index=0, delta="world!"),
            AssistantDoneEvent(
                message=AssistantMessage(content="Hello, world!"),
                reason="stop",
            ),
        ]
    ])

    result = await run_print_mode(
        prompt="Say hello",
        model="fake",
        cwd=tmp_path,
        provider=provider,
    )

    assert result is True
    captured = capsys.readouterr()
    assert "Hello, world!" in captured.out
    assert len(provider.calls) == 1
    model, system, messages, tools, signal = provider.calls[0]
    assert model == "fake"


@pytest.mark.anyio
async def test_print_mode_with_tool_call(
    tmp_path: Path,
    capsys,
) -> None:
    """Pattern B: tool call is executed, session is persisted."""
    tool_call = ToolCall(
        id="call-1",
        name="write",
        arguments={"path": "out.txt", "content": "data"},
    )
    provider = FakeProvider([
        [
            AssistantStartEvent(partial=AssistantMessage(content="")),
            ToolCallDeltaEvent(content_index=0, partial=tool_call),
            AssistantDoneEvent(
                message=AssistantMessage(content="", tool_calls=[tool_call]),
                reason="tool_calls",
            ),
        ],
        [
            AssistantStartEvent(partial=AssistantMessage(content="")),
            TextDeltaEvent(content_index=0, delta="File written."),
            AssistantDoneEvent(
                message=AssistantMessage(content="File written."),
                reason="stop",
            ),
        ],
    ])

    from tau_agent.session import JsonlSessionStorage

    storage = JsonlSessionStorage(tmp_path / "session.jsonl")

    result = await run_print_mode(
        prompt="Write out.txt",
        model="fake",
        cwd=tmp_path,
        provider=provider,
        storage=storage,
    )

    assert result is True
    assert (tmp_path / "out.txt").read_text() == "data"

    # Session was persisted
    entries = await storage.read_all()
    assert len(entries) > 3  # SessionInfoEntry + messages + LeafEntry
