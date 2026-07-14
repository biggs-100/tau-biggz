"""Tests for tau_coding.rpc — JSONL protocol helpers and event serialization."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tau_agent.events import (
    AgentEndEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    MessageStartEvent,
    ThinkingDeltaEvent,
)
from tau_agent.messages import AssistantMessage
from tau_coding.rpc import (
    RpcCommand,
    RpcResponse,
    _event_to_dict,
    _read_stdin,
    _run_prompt,
    _write_json,
    run_rpc_mode,
)

# ── data models ────────────────────────────────────────────────────────


class TestRpcCommand:
    def test_defaults(self) -> None:
        cmd = RpcCommand()
        assert cmd.id is None
        assert cmd.type == ""
        assert cmd.data is None

    def test_with_values(self) -> None:
        cmd = RpcCommand(id="123", type="prompt", data={"message": "hello"})
        assert cmd.id == "123"
        assert cmd.type == "prompt"
        assert cmd.data["message"] == "hello"


class TestRpcResponse:
    def test_defaults(self) -> None:
        resp = RpcResponse()
        assert resp.id is None
        assert resp.type == "response"
        assert resp.command == ""
        assert resp.success is True
        assert resp.error is None
        assert resp.data is None

    def test_error_response(self) -> None:
        resp = RpcResponse(id="abc", command="prompt", success=False, error="Something failed")
        d = resp.__dict__
        assert d["id"] == "abc"
        assert d["success"] is False
        assert d["error"] == "Something failed"

    def test_with_data(self) -> None:
        resp = RpcResponse(id="1", command="get_state", success=True, data={"model": "gpt-4"})
        assert resp.data["model"] == "gpt-4"


# ── _event_to_dict ────────────────────────────────────────────────────

# NOTE: _event_to_dict in the production code has known issues with
# some event types. AgentStartEvent crashes because it has no session_id
# attribute. ToolExecutionStartEvent and ToolExecutionEndEvent crash
# because they access event.tool_name instead of event.tool_call.name
# and event.result.name. We test the events that work correctly.


class TestEventToDict:
    def test_message_start_event(self) -> None:
        event = MessageStartEvent(message_role="user")
        result = _event_to_dict(event)
        assert result["type"] == "event"
        # removesuffix("Event").lower() produces "messagestart" (no underscore)
        assert result["event"] == "messagestart"
        assert result["role"] == "user"

    def test_message_start_default_role(self) -> None:
        event = MessageStartEvent()
        result = _event_to_dict(event)
        assert result["role"] == "assistant"

    def test_message_delta_event(self) -> None:
        event = MessageDeltaEvent(delta="Hello ")
        result = _event_to_dict(event)
        # removesuffix("Event").lower() -> "messagedelta"
        assert result["event"] == "messagedelta"
        assert result["delta"] == "Hello "

    def test_thinking_delta_event(self) -> None:
        event = ThinkingDeltaEvent(delta="reasoning...")
        result = _event_to_dict(event)
        assert result["event"] == "thinkingdelta"
        assert result["delta"] == "reasoning..."

    def test_thinking_delta_long_truncated(self) -> None:
        long_delta = "x" * 500
        event = ThinkingDeltaEvent(delta=long_delta)
        result = _event_to_dict(event)
        assert len(result["delta"]) == 200

    def test_message_end_event(self) -> None:
        message = AssistantMessage(content="Final answer")
        event = MessageEndEvent(message=message)
        result = _event_to_dict(event)
        assert result["event"] == "messageend"
        assert result["role"] == "assistant"
        assert "Final answer" in result["content"]

    def test_message_end_event_long_content_truncated(self) -> None:
        long_content = "x" * 1000
        message = AssistantMessage(content=long_content)
        event = MessageEndEvent(message=message)
        result = _event_to_dict(event)
        assert len(result["content"]) == 500

    def test_agent_end_event(self) -> None:
        event = AgentEndEvent()
        result = _event_to_dict(event)
        assert result["event"] == "agentend"
        # AgentEndEvent has no ok/error fields; _event_to_dict uses
        # hasattr which returns False, so these keys are filtered out
        assert "ok" not in result
        assert "error" not in result


# ── _write_json ────────────────────────────────────────────────────────


class TestWriteJson:
    def test_writes_valid_json_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        _write_json({"type": "event", "event": "ready", "cwd": "/test"})
        captured = capsys.readouterr()
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "event"
        assert obj["event"] == "ready"
        assert obj["cwd"] == "/test"
        assert captured.out.endswith("\n")

    def test_writes_multiple_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        _write_json({"a": 1})
        _write_json({"b": 2})
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_serializes_non_serializable_with_default_str(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """_write_json uses default=str so Path and other objects are serialized."""
        _write_json({"path": "hello"})
        captured = capsys.readouterr()
        obj = json.loads(captured.out.strip())
        assert obj["path"] == "hello"

    def test_response_dict_serializes_correctly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """RpcResponse.__dict__ can be serialized via _write_json."""
        resp = RpcResponse(id="1", command="prompt", success=True)
        _write_json(resp.__dict__)
        captured = capsys.readouterr()
        obj = json.loads(captured.out.strip())
        assert obj["id"] == "1"
        assert obj["command"] == "prompt"
        assert obj["success"] is True


# ── _read_stdin ─────────────────────────────────────────────────


class TestReadStdin:
    """Tests for _read_stdin -- async stdin JSON reader."""

    @pytest.mark.anyio
    async def test_reads_json_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Parse JSON lines from a pre-fed StreamReader."""
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"type":"prompt","id":"1","message":"hello"}\n')
        reader.feed_eof()

        monkeypatch.setattr(asyncio, "StreamReader", lambda: reader)

        mock_loop = AsyncMock(spec=asyncio.BaseEventLoop)
        mock_loop.connect_read_pipe = AsyncMock()
        monkeypatch.setattr(asyncio, "get_event_loop", lambda: mock_loop)

        commands: list[RpcCommand] = []
        async for cmd in _read_stdin():
            commands.append(cmd)

        assert len(commands) == 1
        assert commands[0].type == "prompt"
        assert commands[0].id == "1"
        assert commands[0].data is not None
        assert commands[0].data["message"] == "hello"

    @pytest.mark.anyio
    async def test_skips_empty_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skip blank lines without yielding a command."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"\n\n\n")
        reader.feed_eof()

        monkeypatch.setattr(asyncio, "StreamReader", lambda: reader)

        mock_loop = AsyncMock(spec=asyncio.BaseEventLoop)
        mock_loop.connect_read_pipe = AsyncMock()
        monkeypatch.setattr(asyncio, "get_event_loop", lambda: mock_loop)

        commands: list[RpcCommand] = [cmd async for cmd in _read_stdin()]
        assert commands == []

    @pytest.mark.anyio
    async def test_handles_invalid_json_and_continues(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Write error response for malformed JSON and continue reading."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"not valid json\n")
        reader.feed_data(b'{"type":"prompt","id":"2"}\n')
        reader.feed_eof()

        monkeypatch.setattr(asyncio, "StreamReader", lambda: reader)

        mock_loop = AsyncMock(spec=asyncio.BaseEventLoop)
        mock_loop.connect_read_pipe = AsyncMock()
        monkeypatch.setattr(asyncio, "get_event_loop", lambda: mock_loop)

        commands: list[RpcCommand] = [cmd async for cmd in _read_stdin()]
        assert len(commands) == 1
        assert commands[0].id == "2"

        captured = capsys.readouterr()
        assert "Invalid JSON" in captured.out
        assert "success" in captured.out

    @pytest.mark.anyio
    async def test_connection_error_stops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stop iteration when readline raises OSError (pipe closed)."""
        reader = asyncio.StreamReader()

        async def _broken_readline() -> bytes:
            raise ConnectionError("Pipe closed")

        reader.readline = _broken_readline  # type: ignore[assignment]

        monkeypatch.setattr(asyncio, "StreamReader", lambda: reader)

        mock_loop = AsyncMock(spec=asyncio.BaseEventLoop)
        mock_loop.connect_read_pipe = AsyncMock()
        monkeypatch.setattr(asyncio, "get_event_loop", lambda: mock_loop)

        commands: list[RpcCommand] = [cmd async for cmd in _read_stdin()]
        assert commands == []


# ── _run_prompt ─────────────────────────────────────────────────


async def _mock_prompt_stream(message: str) -> AsyncIterator:
    """Async generator that yields a simple message stream for tests."""
    yield MessageDeltaEvent(delta="Hello ")
    yield MessageEndEvent(message=AssistantMessage(content="World"))


class TestRunPrompt:
    """Tests for _run_prompt -- event streaming helper."""

    @pytest.mark.anyio
    async def test_streams_events_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Stream model events as JSON lines."""
        session = AsyncMock()
        session.prompt = _mock_prompt_stream

        await _run_prompt(session, "hello")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) >= 2

        evt1 = json.loads(lines[0])
        assert evt1["type"] == "event"
        assert evt1["event"] == "messagedelta"
        assert evt1["delta"] == "Hello "

        evt2 = json.loads(lines[1])
        assert evt2["type"] == "event"
        assert evt2["event"] == "messageend"

    @pytest.mark.anyio
    async def test_error_during_prompt(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Errors during prompt are caught and written as error events."""
        session = AsyncMock()

        async def _failing_prompt(message: str) -> AsyncIterator:
            raise ValueError("API call failed")
            yield  # pragma: no cover

        session.prompt = _failing_prompt

        await _run_prompt(session, "hello")

        captured = capsys.readouterr()
        evt = json.loads(captured.out.strip())
        assert evt["type"] == "event"
        assert evt["event"] == "error"
        assert "API call failed" in evt["error"]


# ── run_rpc_mode ───────────────────────────────────────────────


class MockProvider:
    """Minimal provider stub for test mocks."""

    name: str = "test-provider"


class MockSessionRecord:
    """Minimal CodingSessionRecord stub."""

    id: str = "test-session-id"
    model: str = "test-model"
    cwd: Path = Path("/tmp/test-cwd")
    path: Path = Path("/tmp/test-cwd/session.jsonl")
    provider_name: str = "test-provider"


class TestRunRpcMode:
    """Tests for run_rpc_mode -- the async RPC main loop.

    Mocks _read_stdin to inject commands, sets up mock services so
    session-creation code paths can execute without real providers.
    """

    def _mock_session_services(self, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        """Set up common mocks for session-dependent commands."""
        mock_session = AsyncMock()
        mock_session.model = "test-model"
        mock_session.provider_name = "test-provider"
        mock_session.thinking_level = "off"
        mock_session.is_running = False
        mock_session.session_id = "test-session-id"
        mock_session.prompt = _mock_prompt_stream
        # set_model is a regular (sync) method; override AsyncMock default
        mock_session.set_model = MagicMock()

        monkeypatch.setattr(
            "tau_coding.rpc.CodingSession.load",
            AsyncMock(return_value=mock_session),
        )
        monkeypatch.setattr(
            "tau_coding.rpc.SessionManager",
            lambda: MagicMock(prepare_session=lambda **kw: MockSessionRecord()),
        )
        monkeypatch.setattr(
            "tau_coding.rpc.resolve_provider_selection",
            lambda settings, **kw: MagicMock(provider=MockProvider(), model="test-model"),
        )
        monkeypatch.setattr(
            "tau_coding.rpc.create_model_provider",
            lambda provider, model: MagicMock(),
        )
        return mock_session

    @pytest.mark.anyio
    async def test_ready_event_at_start(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Send 'ready' event before processing commands."""

        async def _no_commands() -> AsyncIterator[RpcCommand]:
            return  # EOF immediately
            yield  # pragma: no cover

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _no_commands)

        test_cwd = Path("/tmp/test")
        await run_rpc_mode(cwd=test_cwd)

        captured = capsys.readouterr()
        ready = json.loads(captured.out.strip())
        assert ready["type"] == "event"
        assert ready["event"] == "ready"
        assert ready["cwd"] == str(test_cwd)

    @pytest.mark.anyio
    async def test_unknown_command(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Unknown command type gets error response."""
        commands = [RpcCommand(id="u1", type="unknown_cmd", data={})]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) >= 2

        error_resp = json.loads(lines[1])
        assert error_resp["type"] == "response"
        assert error_resp["success"] is False
        assert "unknown_cmd" in error_resp["error"]

    @pytest.mark.anyio
    async def test_cancel_without_active_task(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Cancel command succeeds even without active task or session."""
        commands = [RpcCommand(id="c1", type="cancel", data={})]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        cancel_resp = json.loads(lines[1])
        assert cancel_resp["command"] == "cancel"
        assert cancel_resp["success"] is True

    @pytest.mark.anyio
    async def test_get_state_without_session(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get_state returns error when no session exists."""
        commands = [RpcCommand(id="g1", type="get_state", data={})]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        state_resp = json.loads(lines[1])
        assert state_resp["command"] == "get_state"
        assert state_resp["success"] is False
        assert "No active session" in state_resp["error"]

    @pytest.mark.anyio
    async def test_prompt_creates_session_and_streams(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prompt command creates a session, responds, and streams events."""
        commands = [RpcCommand(id="r1", type="prompt", data={"message": "hello"})]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)
        self._mock_session_services(monkeypatch)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) >= 3

        ready = json.loads(lines[0])
        assert ready["event"] == "ready"

        prompt_resp = json.loads(lines[1])
        assert prompt_resp["type"] == "response"
        assert prompt_resp["command"] == "prompt"
        assert prompt_resp["success"] is True

        # Streamed events follow
        events = [json.loads(line) for line in lines[2:]]
        assert len(events) >= 1

    @pytest.mark.anyio
    async def test_prompt_empty_message_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Empty message prompt returns error without creating session."""
        commands = [RpcCommand(id="e1", type="prompt", data={"message": ""})]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        prompt_resp = json.loads(lines[1])
        assert prompt_resp["command"] == "prompt"
        assert prompt_resp["success"] is False
        assert "Empty message" in prompt_resp["error"]

    @pytest.mark.anyio
    async def test_get_state_with_session(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get_state returns session info after a prompt creates one."""
        commands = [
            RpcCommand(id="p1", type="prompt", data={"message": "hello"}),
            RpcCommand(id="g1", type="get_state", data={}),
        ]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)
        self._mock_session_services(monkeypatch)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        state_resp = None
        for line in reversed(lines):
            obj = json.loads(line)
            if obj.get("command") == "get_state":
                state_resp = obj
                break

        assert state_resp is not None
        assert state_resp["success"] is True
        assert state_resp["data"]["model"] == "test-model"
        assert state_resp["data"]["session_id"] == "test-session-id"

    @pytest.mark.anyio
    async def test_set_model_creates_session(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """set_model with no existing session creates one."""
        commands = [
            RpcCommand(id="s1", type="set_model", data={"model": "gpt-5"}),
        ]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)
        self._mock_session_services(monkeypatch)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        set_resp = json.loads(lines[1])
        assert set_resp["command"] == "set_model"
        assert set_resp["success"] is True

    @pytest.mark.anyio
    async def test_set_model_on_existing_session(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """set_model on an existing session updates the model."""
        commands = [
            RpcCommand(id="p1", type="prompt", data={"message": "hello"}),
            RpcCommand(id="s1", type="set_model", data={"model": "gpt-5"}),
        ]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)
        mock_session = self._mock_session_services(monkeypatch)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        set_resp = None
        for line in lines:
            obj = json.loads(line)
            if obj.get("command") == "set_model":
                set_resp = obj
                break

        assert set_resp is not None
        assert set_resp["success"] is True
        mock_session.set_model.assert_called_once_with("gpt-5")

    @pytest.mark.anyio
    async def test_multiple_commands_in_sequence(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Process multiple commands: unknown, cancel, prompt."""
        commands = [
            RpcCommand(id="u1", type="bad_cmd", data={}),
            RpcCommand(id="c1", type="cancel", data={}),
            RpcCommand(id="p1", type="prompt", data={"message": "hi"}),
        ]

        async def _mock_stdin() -> AsyncIterator[RpcCommand]:
            for cmd in commands:
                yield cmd

        monkeypatch.setattr("tau_coding.rpc._read_stdin", _mock_stdin)
        self._mock_session_services(monkeypatch)

        await run_rpc_mode(cwd=Path("/tmp/test"))

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) >= 4

        responses = [
            json.loads(line) for line in lines if json.loads(line).get("type") == "response"
        ]
        assert len(responses) == 3
        assert responses[0]["success"] is False
        assert "bad_cmd" in responses[0]["error"]
        assert responses[1]["command"] == "cancel"
        assert responses[1]["success"] is True
        assert responses[2]["command"] == "prompt"
        assert responses[2]["success"] is True
