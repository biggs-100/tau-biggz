"""Tests for tool-event wrapping and extension-tool conversion.

Covers ``_wrap_tool_with_events`` and ``_extension_tool_to_agent_tool``
from ``tau_coding.tools_events``.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from tau_agent.tools import AgentTool, AgentToolResult
from tau_agent.types import JSONValue
from tau_coding.extensions import ExtensionRegistry, ToolRegistration
from tau_coding.harness import HarnessApproval
from tau_coding.tools_events import _extension_tool_to_agent_tool, _wrap_tool_with_events

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_fake_executor(
    result: str | None = "ok",
    *,
    fail: bool = False,
) -> type:
    """Return an async callable that can serve as a tool executor."""

    async def fake_executor(
        arguments: Mapping[str, JSONValue],
        signal=None,
    ) -> AgentToolResult:
        if fail:
            raise RuntimeError("executor exploded")
        return AgentToolResult(
            tool_call_id="call_1",
            name="test_tool",
            ok=True,
            content=result or "",
        )

    return fake_executor


def _make_agent_tool(
    name: str = "test_tool",
    *,
    executor=None,
) -> AgentTool:
    """Build a minimal AgentTool for use in tests."""
    return AgentTool(
        name=name,
        description="A test tool",
        input_schema={"type": "object", "properties": {}, "required": []},
        executor=executor or _make_fake_executor(),
    )


# ── _wrap_tool_with_events ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_wrap_happy_path_no_approval_no_extensions(monkeypatch) -> None:
    """No approval config + no extensions → tool passes through."""
    monkeypatch.setattr(
        "tau_coding.tools_events.get_default_registry",
        lambda: _FakeRegistry(),
    )
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: None,
    )

    tool = _make_agent_tool()
    wrapped = _wrap_tool_with_events(tool, approval=None)
    result = await wrapped.executor({"arg": 1})

    assert result.ok is True
    assert result.content == "ok"


@pytest.mark.anyio
async def test_wrap_approval_denied(monkeypatch) -> None:
    """Approval check returns a denial string → result is blocked."""
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: "Tool 'test_tool' is denied",
    )

    tool = _make_agent_tool()
    approval = HarnessApproval(default="deny")
    wrapped = _wrap_tool_with_events(tool, approval=approval)
    result = await wrapped.executor({"arg": 1})

    assert result.ok is False
    assert result.error == "Tool 'test_tool' is denied"
    assert result.content == "Tool 'test_tool' is denied"


@pytest.mark.anyio
async def test_wrap_extension_blocks(monkeypatch) -> None:
    """Extension dispatch_event returns a block dict → result is blocked."""
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: None,
    )

    class BlockingRegistry(ExtensionRegistry):
        def dispatch_event(self, event_name, event_data):
            if event_name == "tool_call":
                return [{"block": True, "reason": "Blocked by safety"}]
            return []

    monkeypatch.setattr(
        "tau_coding.tools_events.get_default_registry",
        lambda: BlockingRegistry(),
    )

    tool = _make_agent_tool()
    wrapped = _wrap_tool_with_events(tool, approval=None)
    result = await wrapped.executor({"command": "rm -rf /"})

    assert result.ok is False
    assert result.error == "Blocked by safety"
    assert result.content == "Blocked by safety"


@pytest.mark.anyio
async def test_wrap_extension_no_blockers_passes_through(monkeypatch) -> None:
    """dispatch_event returns non-blocking results → tool executes normally."""
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: None,
    )

    class LoggingRegistry(ExtensionRegistry):
        def __init__(self):
            super().__init__()
            self.events = []

        def dispatch_event(self, event_name, event_data):
            self.events.append((event_name, event_data))
            return [{"logged": True}]  # not a block

    monkeypatch.setattr(
        "tau_coding.tools_events.get_default_registry",
        lambda: LoggingRegistry(),
    )

    tool = _make_agent_tool()
    wrapped = _wrap_tool_with_events(tool, approval=None)
    result = await wrapped.executor({"arg": 1})

    assert result.ok is True
    assert result.content == "ok"


@pytest.mark.anyio
async def test_wrap_executor_raises_exception(monkeypatch) -> None:
    """Tool executor raises → exception is caught and returned as error result."""
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: None,
    )

    class EmptyRegistry(ExtensionRegistry):
        def dispatch_event(self, event_name, event_data):
            return []

    monkeypatch.setattr(
        "tau_coding.tools_events.get_default_registry",
        lambda: EmptyRegistry(),
    )

    async def failing_executor(arguments, signal=None):
        raise ValueError("something broke")

    tool = _make_agent_tool(executor=failing_executor)
    wrapped = _wrap_tool_with_events(tool, approval=None)
    result = await wrapped.executor({"arg": 1})

    assert result.ok is False
    assert "something broke" in result.error or result.error is not None


@pytest.mark.anyio
async def test_wrap_after_tool_call_event_fired(monkeypatch) -> None:
    """After successful execution, after_tool_call event is dispatched."""
    monkeypatch.setattr(
        "tau_coding.tools_events._check_tool_approval",
        lambda *a, **kw: None,
    )

    class TrackingRegistry(ExtensionRegistry):
        def __init__(self):
            super().__init__()
            self.events = []

        def dispatch_event(self, event_name, event_data):
            self.events.append((event_name, event_data))
            return []

    registry = TrackingRegistry()
    monkeypatch.setattr(
        "tau_coding.tools_events.get_default_registry",
        lambda: registry,
    )

    tool = _make_agent_tool()
    wrapped = _wrap_tool_with_events(tool, approval=None)
    result = await wrapped.executor({"arg": 1})

    # Should have both tool_call and after_tool_call events
    event_names = [e[0] for e in registry.events]
    assert "tool_call" in event_names
    assert "after_tool_call" in event_names
    assert result.ok is True
    assert result.content == "ok"


# ── _extension_tool_to_agent_tool ────────────────────────────────────────────


def test_ext_to_agent_basic_sync() -> None:
    """Basic sync extension tool → AgentTool with correct metadata."""
    reg = ToolRegistration(
        name="greet",
        description="A greeting tool",
        parameters=[],
        executor=lambda: "Hello!",
    )
    agent_tool = _extension_tool_to_agent_tool(reg)

    assert agent_tool.name == "greet"
    assert agent_tool.description == "A greeting tool"
    assert agent_tool.input_schema == {
        "type": "object",
        "properties": {},
        "required": [],
    }
    assert agent_tool.prompt_snippet is None
    assert agent_tool.prompt_guidelines == ()


@pytest.mark.anyio
async def test_ext_to_agent_sync_executor() -> None:
    """Sync executor returns an AgentTool with correct result."""
    reg = ToolRegistration(
        name="hi",
        description="Say hi",
        parameters=[],
        executor=lambda: "Hi there!",
    )
    agent_tool = _extension_tool_to_agent_tool(reg)
    result = await agent_tool.executor({})

    assert result.ok is True
    assert result.content == "Hi there!"
    assert result.name == "hi"


@pytest.mark.anyio
async def test_ext_to_agent_async_executor() -> None:
    """Async executor (awaitable) is awaited and result is correct."""

    async def async_greet() -> str:
        return "Hello async!"

    reg = ToolRegistration(
        name="async_greet",
        description="Async greeting",
        parameters=[],
        executor=async_greet,
    )
    agent_tool = _extension_tool_to_agent_tool(reg)
    result = await agent_tool.executor({})

    assert result.ok is True
    assert result.content == "Hello async!"


@pytest.mark.anyio
async def test_ext_to_agent_with_parameters() -> None:
    """Registration with parameters → input_schema built correctly."""

    def greet(name: str) -> str:
        return f"Hello, {name}!"

    reg = ToolRegistration(
        name="greet",
        description="Greet someone",
        parameters=[
            {"name": "name", "kind": "str"},
        ],
        executor=greet,
    )
    agent_tool = _extension_tool_to_agent_tool(reg)

    assert agent_tool.input_schema == {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Parameter name"},
        },
        "required": ["name"],
    }


@pytest.mark.anyio
async def test_ext_to_agent_multiple_parameters() -> None:
    """Multiple parameters → all added to input_schema."""

    def add(a: int, b: int) -> int:
        return a + b

    reg = ToolRegistration(
        name="add",
        description="Add two numbers",
        parameters=[
            {"name": "a", "kind": "int"},
            {"name": "b", "kind": "int"},
        ],
        executor=add,
    )
    agent_tool = _extension_tool_to_agent_tool(reg)

    assert agent_tool.input_schema["required"] == ["a", "b"]
    assert "a" in agent_tool.input_schema["properties"]
    assert "b" in agent_tool.input_schema["properties"]


@pytest.mark.anyio
async def test_ext_to_agent_executor_raises() -> None:
    """Executor raises → caught and returned as error result."""

    def crash() -> str:
        raise ValueError("boom")

    reg = ToolRegistration(
        name="crash",
        description="A crashing tool",
        parameters=[],
        executor=crash,
    )
    agent_tool = _extension_tool_to_agent_tool(reg)
    result = await agent_tool.executor({})

    assert result.ok is False
    assert result.error == "boom"
    assert "boom" in result.content


# ── Fake / helper registries ────────────────────────────────────────────────


class _FakeRegistry(ExtensionRegistry):
    """Registry that returns empty results from dispatch_event."""

    def __init__(self):
        super().__init__()

    def dispatch_event(self, event_name, event_data):
        return []
