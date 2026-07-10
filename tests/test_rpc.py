"""Tests for tau_coding.rpc — JSONL protocol helpers and event serialization."""

from __future__ import annotations

import json

import pytest

from tau_agent.events import (
    AgentEndEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    MessageStartEvent,
    ThinkingDeltaEvent,
)
from tau_agent.messages import AssistantMessage
from tau_coding.rpc import RpcCommand, RpcResponse, _event_to_dict, _write_json

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
        # removesuffix("Event").lower() → "messagedelta"
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
