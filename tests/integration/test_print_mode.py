"""Integration tests for run_print_mode end-to-end."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_agent import AssistantMessage
from tau_agent.tools import ToolCall
from tau_ai import ProviderResponseEndEvent, ProviderResponseStartEvent, ProviderTextDeltaEvent
from tau_ai.events import ProviderEvent
from tau_coding.cli import run_print_mode


@pytest.mark.anyio
async def test_print_mode_text_only(
    fake_provider,
    tmp_path: Path,
    capsys,
) -> None:
    """Pattern A: text-only stream prints output and returns True."""
    fake_provider._streams = [
        [
            ProviderResponseStartEvent(model="fake"),
            ProviderTextDeltaEvent(delta="Hello, "),
            ProviderTextDeltaEvent(delta="world!"),
            ProviderResponseEndEvent(
                message=AssistantMessage(content="Hello, world!"),
                finish_reason="stop",
            ),
        ]
    ]

    result = await run_print_mode(
        prompt="Say hello",
        model="fake",
        cwd=tmp_path,
        provider=fake_provider,
    )

    assert result is True
    captured = capsys.readouterr()
    assert "Hello, world!" in captured.out
    assert len(fake_provider.calls) == 1
    model, system, messages, tools = fake_provider.calls[0]
    assert model == "fake"


@pytest.mark.anyio
async def test_print_mode_with_tool_call(
    fake_provider,
    tmp_path: Path,
    capsys,
) -> None:
    """Pattern B: tool call is executed, session is persisted."""
    tool_call = ToolCall(
        id="call-1",
        name="write",
        arguments={"path": "out.txt", "content": "data"},
    )
    fake_provider._streams = [
        [
            ProviderResponseStartEvent(model="fake"),
            ProviderResponseEndEvent(
                message=AssistantMessage(content="", tool_calls=[tool_call]),
                finish_reason="tool_calls",
            ),
        ],
        [
            ProviderResponseStartEvent(model="fake"),
            ProviderTextDeltaEvent(delta="File written."),
            ProviderResponseEndEvent(
                message=AssistantMessage(content="File written."),
                finish_reason="stop",
            ),
        ],
    ]

    from tau_agent.session import JsonlSessionStorage

    storage = JsonlSessionStorage(tmp_path / "session.jsonl")

    result = await run_print_mode(
        prompt="Write out.txt",
        model="fake",
        cwd=tmp_path,
        provider=fake_provider,
        storage=storage,
    )

    assert result is True
    assert (tmp_path / "out.txt").read_text() == "data"

    # Session was persisted
    entries = await storage.read_all()
    assert len(entries) > 3  # SessionInfoEntry + messages + LeafEntry
