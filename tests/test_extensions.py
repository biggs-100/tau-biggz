"""Tests for the Tau extension system."""

from __future__ import annotations

from pathlib import Path

from tau_coding.extensions import (
    Extension,
    ExtensionInstance,
    ExtensionRegistry,
    command,
    create_default_registry,
    on,
    tool,
    ui_widget,
)


def test_extension_registration_via_decorators() -> None:
    """Decorators should register tools, commands, and event handlers."""

    class TestExt(Extension):
        @tool("my_tool", "A test tool")
        def my_tool(self, name: str = "world") -> str:
            return f"Hello {name}"

        @command("my_cmd", description="A test command")
        def my_cmd(self, args: str) -> str:
            return f"cmd: {args}"

        @on("tool_call")
        def on_tool(self, event: dict) -> None:
            pass

    ext = TestExt()
    reg = ExtensionRegistry()
    # Manually collect
    tools = reg._collect_tools(ext)
    commands = reg._collect_commands(ext)
    handlers = reg._collect_handlers(ext)

    assert len(tools) == 1
    assert tools[0].name == "my_tool"
    assert tools[0].description == "A test tool"

    assert len(commands) == 1
    assert commands[0].name == "my_cmd"
    assert commands[0].description == "A test command"

    assert "tool_call" in handlers
    assert len(handlers["tool_call"]) == 1


def test_extension_loading_from_directory(tmp_path: Path) -> None:
    """Extensions in a directory should be discoverable and loadable."""
    ext_dir = tmp_path / "extensions"
    ext_dir.mkdir()
    ext_file = ext_dir / "my_ext.py"
    ext_file.write_text("""
from tau_coding.extensions import Extension, tool

class MyExt(Extension):
    @tool("hello", "Say hello")
    def hello(self, name: str = "world") -> str:
        return f"Hello, {name}!"
""")

    reg = ExtensionRegistry()
    reg.add_search_path(ext_dir)
    instances = reg.load_all()

    assert len(instances) == 1
    assert instances[0].name == "MyExt"
    assert len(instances[0].tools) == 1
    assert instances[0].tools[0].name == "hello"


def test_extension_discover_no_files(tmp_path: Path) -> None:
    """Empty extension directory should discover nothing."""
    ext_dir = tmp_path / "empty_ext"
    ext_dir.mkdir()

    reg = ExtensionRegistry()
    reg.add_search_path(ext_dir)
    instances = reg.load_all()

    assert len(instances) == 0


def test_default_registry_uses_tau_paths(tmp_path: Path, monkeypatch) -> None:
    """Default registry should set up global and project paths."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("tau_coding.extensions.Path.cwd", lambda: tmp_path)

    reg = create_default_registry()
    candidates = reg.discover()

    assert isinstance(candidates, list)


def test_greeting_extension_loads() -> None:
    """Greeting extension is discoverable and loads correctly."""
    reg = ExtensionRegistry()
    reg.add_search_path(Path("example_extensions"))
    instances = reg.load_all()
    greeting_exts = [i for i in instances if "greeting" in i.path.lower()]
    assert len(greeting_exts) == 1
    ext = greeting_exts[0]
    tool_names = [t.name for t in ext.tools]
    cmd_names = [c.name for c in ext.commands]
    assert "hello" in tool_names
    assert "hi" in cmd_names


def test_greeting_tool_returns_greeting() -> None:
    """@tool('hello') returns a greeting string when called."""

    class TestGreetingExt(Extension):
        @tool("hello", "Greet the user")
        def hello(self, name: str = "world") -> str:
            return f"Hello, {name}!"

    ext = TestGreetingExt()
    assert ext.hello() == "Hello, world!"
    assert ext.hello("Tau") == "Hello, Tau!"


# ── Integration tests ───────────────────────────────────────────────────────


def test_event_dispatch() -> None:
    """Register @on('session_start'), dispatch event, verify handler called."""
    call_log: list[tuple[str, object]] = []

    class TestExt(Extension):
        @on("session_start")
        def on_start(self, event: object) -> None:
            call_log.append(("session_start", event))

    reg = ExtensionRegistry()
    ext = TestExt()
    handlers = reg._collect_handlers(ext)
    reg._extensions["TestExt"] = ExtensionInstance(
        name="TestExt",
        path="",
        instance=ext,
        handlers=handlers,
    )

    reg.dispatch_event("session_start", {"session_id": "test-123"})
    assert len(call_log) == 1
    assert call_log[0][0] == "session_start"
    assert call_log[0][1] == {"session_id": "test-123"}  # type: ignore[comparison-overlap]


def test_tool_blocking() -> None:
    """Register an extension with @on('tool_call') that returns {"block": True}."""
    class TestExt(Extension):
        @on("tool_call")
        def blocker(self, event: object) -> dict:
            return {"block": True, "reason": "Blocked by test"}

    reg = ExtensionRegistry()
    ext = TestExt()
    handlers = reg._collect_handlers(ext)
    reg._extensions["TestExt"] = ExtensionInstance(
        name="TestExt",
        path="",
        instance=ext,
        handlers=handlers,
    )

    results = reg.dispatch_event(
        "tool_call", {"tool_name": "bash", "input": {}, "tool_call_id": "test"}
    )
    assert len(results) == 1
    assert isinstance(results[0], dict)
    assert results[0].get("block") is True
    assert results[0].get("reason") == "Blocked by test"


def test_command_routing() -> None:
    """Extension @command() appears in get_commands() and handler works."""
    class TestExt(Extension):
        @command("test_cmd", description="A test command")
        def my_cmd(self, args: str) -> str:
            return f"executed: {args}"

    reg = ExtensionRegistry()
    ext = TestExt()
    commands = reg._collect_commands(ext)
    reg._extensions["TestExt"] = ExtensionInstance(
        name="TestExt",
        path="",
        instance=ext,
        commands=commands,
    )

    cmds = reg.get_commands()
    assert len(cmds) == 1
    assert cmds[0].name == "test_cmd"
    assert cmds[0].description == "A test command"

    # Handler is the unbound function; real code calls it as handler(cmd_registration, args)
    result = cmds[0].handler(cmds[0], "arg1")
    assert result == "executed: arg1"


def test_enable_disable() -> None:
    """Disable an extension, verify get_tools() empty, re-enable, verify tools return."""
    class TestExt(Extension):
        @tool("greet", "A test tool")
        def greet(self, name: str = "world") -> str:
            return f"Hello, {name}!"

    reg = ExtensionRegistry()
    ext = TestExt()
    tools = reg._collect_tools(ext)
    reg._extensions["TestExt"] = ExtensionInstance(
        name="TestExt",
        path="",
        instance=ext,
        tools=tools,
    )

    # Initially enabled
    assert reg.is_extension_enabled("TestExt")
    assert len(reg.get_tools()) == 1

    # Disable
    reg.disable_extension("TestExt")
    assert not reg.is_extension_enabled("TestExt")
    assert len(reg.get_tools()) == 0

    # Re-enable
    reg.enable_extension("TestExt")
    assert reg.is_extension_enabled("TestExt")
    assert len(reg.get_tools()) == 1


def test_enable_disable_unknown_extension() -> None:
    """enable/disable/is_enabled on unknown extension raises KeyError."""
    reg = ExtensionRegistry()
    import pytest

    with pytest.raises(KeyError, match="NonExistent"):
        reg.enable_extension("NonExistent")
    with pytest.raises(KeyError, match="NonExistent"):
        reg.disable_extension("NonExistent")
    with pytest.raises(KeyError, match="NonExistent"):
        reg.is_extension_enabled("NonExistent")


def test_ui_widget_collection() -> None:
    """Create an extension with @ui_widget(), call get_ui_widgets(), verify the widget."""
    class TestExt(Extension):
        @ui_widget("status-bar")
        def clock(self) -> str:
            return "🕒 12:00:00"

    reg = ExtensionRegistry()
    ext = TestExt()
    ui_widgets = reg._collect_ui_widgets(ext)
    reg._extensions["TestExt"] = ExtensionInstance(
        name="TestExt",
        path="",
        instance=ext,
        ui_widgets=ui_widgets,
    )

    widgets = reg.get_ui_widgets(zone="status-bar")
    assert len(widgets) == 1
    assert widgets[0].zone == "status-bar"
    assert widgets[0].name == "clock"
    assert widgets[0].text_fn() == "🕒 12:00:00"
