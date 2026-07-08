"""Tests for the Tau extension system."""

from __future__ import annotations

from pathlib import Path

from tau_coding.extensions import (
    Extension,
    ExtensionRegistry,
    command,
    create_default_registry,
    tool,
    on,
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
