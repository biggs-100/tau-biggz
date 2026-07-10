# Tau Extension System

Tau extensions let you add custom tools, slash commands, UI widgets, and event
handlers without modifying Tau's source code. They are Python files
placed in ``~/.tau/extensions/`` or ``.tau/extensions/``.

---

## Quick start

Create `~/.tau/extensions/my_ext.py`:

```python
from tau_coding.extensions import Extension, tool, command, on


class MyExtension(Extension):
    @tool("greet", "Greet someone by name")
    def greet(self, name: str = "world") -> str:
        return f"Hello, {name}!"

    @command("hello", description="Say hello")
    def hello_cmd(self, args: str) -> str:
        return f"Hello {args or 'world'}!"

    @on("tool_call")
    def blocker(self, event):
        if event.get("tool_name") == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd:
                return {"block": True, "reason": "Blocked by extension"}
        return None
```

Run Tau normally. Extensions are auto-discovered.

---

## Location

```
~/.tau/extensions/*.py        global (all projects)
.tau/extensions/*.py          project-local
```

---

## API

### Decorators

| Decorator | Purpose |
|-----------|---------|
| `@tool(name, description)` | Register a tool callable by the LLM |
| `@command(name, description=)` | Register a slash command (`/name`) |
| `@on(event_name)` | Subscribe to lifecycle events |
| `@ui_widget(zone="status-bar")` | Register a UI widget for the TUI status bar |

### `UIWidget` dataclass

```python
@dataclass
class UIWidget:
    zone: str
    name: str
    text_fn: Callable[[], str]
```

Extensions that register UI widgets produce `UIWidget` instances. The `zone`
determines where in the TUI the widget renders (currently only `"status-bar"`).
The `text_fn` is called each frame to produce the widget's display text.

See the working example at `example_extensions/ui_status_ext.py`:

```python
"""Example extension: status bar widget.

Install by placing this file in ~/.tau/extensions/ or .tau/extensions/.
"""

from __future__ import annotations

import datetime

from tau_coding.extensions import Extension, ui_widget


class UiStatusExt(Extension):
    """Demonstrates extension UI widgets in the status bar."""

    @ui_widget("status-bar")
    def clock(self) -> str:
        """Return the current time for the status bar."""
        return f"🕒 {datetime.datetime.now():%H:%M:%S}"

    @ui_widget("status-bar")
    def greeting(self) -> str:
        """Return a greeting."""
        return "👋 Tau ready"
```

### Events

| Event | Payload | When |
|-------|---------|------|
| `session_start` | `{"session": ...}` | After a session starts |
| `session_end` | `{"session": ...}` | Before a session ends |
| `before_prompt` | `{"session": ..., "prompt": content}` | Before the agent processes a prompt |
| `after_prompt` | `{"session": ..., "prompt": content}` | After the agent responds |
| `tool_call` | `{tool_name, input, tool_call_id}` | Before **any** tool executes |
| `after_tool_call` | `{tool_name, input, result}` | After any tool executes |

**Note:** `tool_call` and `after_tool_call` fire for ALL tools:
built-in (read, write, edit, bash, web_search, subagent_run), MCP, and
extension tools. This is achieved via `_wrap_tool_with_events()` in `tools.py`.

### Event handler return values

- `tool_call` — return `{"block": True, "reason": "..."}` to block execution
- Other events — return values are collected but not acted on

---

## Tool blocking

```python
@on("tool_call")
def block_rm(self, event):
    if event.get("tool_name") == "bash":
        cmd = event.get("input", {}).get("command", "")
        if "rm -rf" in cmd or "sudo" in cmd:
            return {"block": True, "reason": "Blocked by safety extension"}
    return None
```

This works for **any tool**: read, write, bash, edit, web_search,
subagent_run, MCP tools, and other extensions.

---

## Enable / disable extensions at runtime

Extensions are enabled by default when loaded. You can toggle them
programmatically via the registry API:

```python
from tau_coding.extensions import get_default_registry

registry = get_default_registry()

# Disable an extension by class name
registry.disable_extension("MyExtension")

# Re-enable
registry.enable_extension("MyExtension")

# Check status
if registry.is_extension_enabled("MyExtension"):
    ...
```

Disabling an extension at runtime prevents its tools, commands, UI widgets,
and event handlers from being returned or dispatched. The extension remains
loaded in memory and can be re-enabled without re-loading.

---

## `ExtensionRegistry` API

| Method | Returns | Description |
|--------|---------|-------------|
| `add_search_path(path, project_local=False)` | `None` | Add a directory to scan for extensions |
| `discover()` | `list[Path]` | Return candidate extension file paths |
| `load_all()` | `list[ExtensionInstance]` | Discover and load all extensions |
| `get_tools()` | `list[ToolRegistration]` | Return tools from enabled extensions |
| `get_commands()` | `list[CommandRegistration]` | Return commands from enabled extensions |
| `get_ui_widgets(zone)` | `list[UIWidget]` | Return UI widgets for a zone from enabled extensions |
| `dispatch_event(event_name, event_data)` | `list[Any]` | Dispatch event to enabled extension handlers |
| `enable_extension(name)` | `None` | Enable a loaded extension |
| `disable_extension(name)` | `None` | Disable a loaded extension |
| `is_extension_enabled(name)` | `bool` | Check if a loaded extension is enabled |
| `unload_all()` | `None` | Unload all extensions |

---

## Available tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents |
| `write` | Write content to a file |
| `edit` | Edit a file using exact text replacement |
| `bash` | Execute shell commands |
| `web_search` | Search the web (DuckDuckGo, no API key required) |
| `subagent_run` | Spawn an isolated sub-agent with custom instructions |
| `mcp_<server>_<tool>` | Tools from connected MCP servers |
| (extension tools) | Tools registered via `@tool` |

### subagent_run

```python
# From an agent markdown
subagent_run(task="Review this code", agent="reviewer")

# With inline instructions
subagent_run(
  task="Check for security issues",
  instructions="You are a security auditor."
)
```

### web_search

```python
web_search(query="latest AI advances 2026")
```

Uses DuckDuckGo HTML search. No API key required.

---

## Lifecycle

1. **Discovery** — Tau scans extension directories at startup
2. **Load** — each `.py` is imported and `Extension` subclasses are instantiated
3. **on_load()** — called after instantiation (override for setup)
4. **Registration** — tools, commands, and handlers are collected from decorated methods
5. **Enable/disable** — extensions can be toggled at runtime without re-loading
6. **on_unload()** — called when extensions are unloaded

---

## vs MCP

| Aspect | Extension | MCP Server |
|--------|-----------|------------|
| Language | Python | Any |
| Process | Inside Tau | Separate process |
| Distribution | `.py` file | npm/PyPI/binary package |
| Isolation | Shares process with Tau | Isolated process |
| Ideal for | Small tools, events, blocking | Complex tools, external ecosystem |

---

## Architecture

- `src/tau_coding/extensions.py` — core (Extension, Registry, decorators)
- `src/tau_coding/tools.py` — `_wrap_tool_with_events()` dispatches events
- `src/tau_coding/commands.py` — extension command routing via `_extension_command_handler()`
- `src/tau_coding/session.py` — session lifecycle events
- `src/tau_coding/tui/app.py` / `src/tau_coding/tui/widgets.py` — UI widget rendering
- Loader: Python `importlib`
- Event dispatch: synchronous (do not block for long)
