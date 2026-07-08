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
        if event.get("tool_name") == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd:
                return {"block": True, "reason": "Blocked by extension"}
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
| `tool_call` | `{tool_name, input, tool_call_id}` | Before a tool executes |
| `after_tool_call` | `{tool_name, result}` | After a tool executes |
| `before_prompt` | `{content}` | Before the agent processes a prompt |
| `after_prompt` | `{content, response}` | After the agent responds |

### Tool return format

Tools return a string (or anything str()-able) as the result.

### Event handler return values

- `tool_call` — return `{"block": True, "reason": "..."}` to block execution
- Other events — return values are collected but not acted on (future use)

## Extension lifecycle

1. Discovery — Tau scans extension directories at startup
2. Load — each `.py` file is imported and Extension subclasses are instantiated
3. `on_load()` — called after instantiation (override for setup)
4. Registration — tools, commands, and handlers are collected from decorated method
5. `on_unload()` — called when extensions are unloaded

## Architecture

- `src/tau_coding/extensions.py` — core system (Extension, Registry, decorators)
- Extensions use Python's `importlib` for dynamic loading
- Event dispatch is synchronous (extensions should not block for long)
