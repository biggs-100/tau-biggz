# Tau Extension System

Tau extensions let you add custom tools, slash commands, and event
handlers without modifying Tau's source code.

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
    def on_tool_call(self, event: dict) -> dict | None:
        """Block dangerous bash commands."""
        if event.get("tool_name") == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd:
                return {"block": True, "reason": "Destructive command blocked"}
        return None
```

Run Tau normally. Extensions are auto-discovered from:

- `~/.tau/extensions/*.py` — global (all projects)
- `.tau/extensions/*.py` — project-local

## API Reference

### Decorators

| Decorator | Purpose |
|-----------|---------|
| `@tool(name, description)` | Register a tool callable by the LLM |
| `@command(name, description=)` | Register a slash command (`/name`) |
| `@on(event_name)` | Subscribe to lifecycle events |

### Events

| Event | Payload | When |
|-------|---------|------|
| `session_start` | `{}` | After a session starts |
| `session_end` | `{}` | Before a session ends |
| `tool_call` | `{tool_name, input, tool_call_id}` | Before **any** tool executes |
| `after_tool_call` | `{tool_name, input, result}` | After any tool executes |
| `before_prompt` | `{content}` | Before the agent processes a prompt |
| `after_prompt` | `{content, response}` | After the agent responds |

Note: `tool_call` and `after_tool_call` fire for **all** tools — built-in
(read, write, edit, bash, web_search, subagent_run) and extension tools.
This is handled by wrapping every tool's executor in `_wrap_tool_with_events()`.

### Event handler return values

- `tool_call` — return `{"block": True, "reason": "..."}` to block execution
- `after_tool_call` — return values are collected for future use
- Other events — return values are collected but not acted on

## Blocking example

```python
@on("tool_call")
def block_rm(self, event):
    if event.get("tool_name") == "bash":
        cmd = event.get("input", {}).get("command", "")
        if "rm -rf" in cmd or "sudo" in cmd:
            return {"block": True, "reason": "Blocked by safety extension"}
    return None
```

## Built-in tools available to the agent

| Tool | Description |
|------|-------------|
| `read` | Read file contents |
| `write` | Write content to a file |
| `edit` | Edit a file using exact text replacement |
| `bash` | Execute shell commands |
| `web_search` | Search the web (DuckDuckGo, no API key) |
| `subagent_run` | Spawn an isolated sub-agent with custom instructions |

## `subagent_run` tool

The LLM can delegate work to sub-agents:

```python
subagent_run(
  task="Review this code for security issues",
  instructions="You are a security reviewer. Find vulnerabilities."
)
```

The orchestrator LLM sets the sub-agent's personality via `instructions`.
The sub-agent runs in an isolated `AgentHarness` with its own provider
and returns the response.

## Extension lifecycle

1. Discovery — Tau scans extension directories at startup
2. Load — each `.py` file is imported and Extension subclasses instantiated
3. `on_load()` — called after instantiation (override for setup)
4. Registration — tools, commands, and handlers collected from decorated methods
5. `on_unload()` — called when extensions are unloaded

## Architecture

- `src/tau_coding/extensions.py` — core system (Extension, Registry, decorators)
- `src/tau_coding/tools.py` — `_wrap_tool_with_events()` dispatches events for all tools
- Extensions use Python's `importlib` for dynamic loading
- Event dispatch is synchronous (extensions should not block for long)
