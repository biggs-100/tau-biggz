---
title: Extensions
description: Extend Tau with custom tools, slash commands, event handlers, and UI widgets.
---

Extensions let you add custom capabilities to Tau — tools the AI model can call,
slash commands you can run, event handlers that react to session events, and
widgets that display live information in the TUI status bar.

Extensions are Python files placed in `~/.tau/extensions/` (global, always
loaded) or `.tau/extensions/` (project-local, shared with collaborators).

## Writing an extension

Every extension is a Python file that exports a subclass of `Extension` and uses
the provided decorators to register capabilities:

```python
# ~/.tau/extensions/my_ext.py
from tau_coding.extensions import Extension, tool, command, on, ui_widget


class MyExtension(Extension):
    """A minimal extension demonstrating all decorators."""

    @tool("greet", "Greet someone by name")
    def greet(self, name: str = "world") -> str:
        """Return a friendly greeting. Used by the AI model."""
        return f"Hello, {name}!"

    @command("hello", description="Say hello interactively")
    def hello_cmd(self, args: str) -> str | None:
        """Slash command triggered by /hello."""
        return f"Hello {args or 'world'}!"

    @on("session_start")
    def on_session_start(self, event: dict) -> None:
        """React to session lifecycle events."""
        print(f"Session started: {event.get('session_id')}")

    @ui_widget(zone="status-bar")
    def clock(self) -> str:
        """Show a live clock in the status bar."""
        import datetime
        return f"🕒 {datetime.datetime.now():%H:%M:%S}"
```

### `@tool` — custom tools for the AI model

The `@tool(name, description)` decorator registers a method as a tool the model
can invoke. The method's parameters become the tool's input schema — each
parameter name and type hint is exposed to the model:

```python
@tool("search_docs", "Search project documentation")
def search_docs(self, query: str, max_results: int = 5) -> str:
    """Search documentation files for a query."""
    # ... implementation ...
    return results
```

Tools return a string that is sent back to the model as the tool result.

### `@command` — slash commands

The `@command(name, description=...)` decorator registers a slash command
available in the TUI prompt. The handler receives the full argument string:

```python
@command("status", description="Show extension status")
def status_cmd(self, args: str) -> str:
    """Handle /status [verbose]."""
    if "verbose" in args:
        return "Detailed status..."
    return "All good."
```

Commands return a string or `None`. Returned text is displayed in the
transcript.

### `@on` — event handlers

The `@on(event_name)` decorator registers a handler for a framework event.
Events are dispatched before and after key actions, letting extensions observe,
log, or block tool calls.

Available events:

| Event | When triggered | Handler signature |
|-------|---------------|-------------------|
| `session_start` | A new session begins | `def handler(self, event: dict) -> None` |
| `session_end` | A session ends | `def handler(self, event: dict) -> None` |
| `tool_call` | Before a tool is invoked | `def handler(self, event: dict) -> dict \| None` |

The `tool_call` event is special — the handler can return a dict with
`{"block": True, "reason": "..."}` to prevent the tool from executing. Return
`None` to allow the call.

```python
@on("tool_call")
def block_dangerous_commands(self, event: dict) -> dict | None:
    """Block rm -rf calls for safety."""
    if event.get("tool_name") == "bash":
        cmd = event.get("input", {}).get("command", "")
        if "rm -rf" in cmd:
            return {"block": True, "reason": "rm -rf is blocked for safety"}
    return None
```

### `@ui_widget` — status bar widgets

The `@ui_widget(zone="status-bar")` decorator registers a method that provides
live text for the TUI status bar. The method is called periodically to refresh
the display:

```python
@ui_widget(zone="status-bar")
def tool_counter(self) -> str:
    """Show a live tool call counter."""
    return f"🔧 {self._call_count}"
```

Widgets can be placed in different zones (currently only `"status-bar"` is
supported).

### Lifecycle hooks

Override `on_load()` and `on_unload()` for setup and teardown:

```python
class MyExtension(Extension):
    def on_load(self) -> None:
        """Called after the extension is loaded."""
        self._data_dir = Path(tempfile.gettempdir()) / "my_ext"
        self._data_dir.mkdir(exist_ok=True)

    def on_unload(self) -> None:
        """Called when the extension is being unloaded."""
        shutil.rmtree(self._data_dir, ignore_errors=True)
```

## Extension discovery

Extensions are loaded from these locations, in order:

1. `~/.tau/extensions/` — user-level, always loaded
2. `.tau/extensions/` — project-level, relative to session working directory
3. `~/.agents/extensions/` — alternative user-level path

Each `.py` file (or directory with `__init__.py`) in these paths is loaded as
an extension. Files starting with `_` are skipped. After adding or editing an
extension while the TUI is open, run **`/reload`** to rediscover them.

## Tool blocking

Event handlers for `tool_call` can block dangerous tool invocations by returning
a block dict. This is checked **before** tool execution, making it suitable for
safety policies:

```python
@on("tool_call")
def block_writes_to_dotfiles(self, event: dict) -> dict | None:
    if event.get("tool_name") == "write":
        path = event.get("input", {}).get("path", "")
        if path.startswith("/etc") or path.startswith("/usr"):
            return {"block": True, "reason": "System file writes are blocked"}
    return None
```

## Event dispatch

Events are dispatched synchronously before the action they guard. The dispatch
order for `tool_call` is:

1. Approval chain check (see [Harness]({{< relref "./harness.md" >}}))
2. Extension `on("tool_call")` handlers (in registration order)
3. Trust store check (see [Trust system]({{< relref "./trust-system.md" >}}))
4. Tool execution

If any step blocks the call, the remaining steps are skipped and the user sees
the denial message.

## See also

- [Harness system]({{< relref "./harness.md" >}}) — personality config and tool approval chains
- [Trust system]({{< relref "./trust-system.md" >}}) — persistent tool approval decisions
- Example extensions under `example_extensions/` in the repository
