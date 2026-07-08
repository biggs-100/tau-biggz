# Tau Extension System

Tau extensions let you add custom tools, slash commands, and event
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

## Ubicacion

```
~/.tau/extensions/*.py        global (todos los proyectos)
.tau/extensions/*.py          proyecto-local
```

---

## API

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

**Nota:** `tool_call` y `after_tool_call` se disparan para TODAS las tools:
built-in (read, write, edit, bash, web_search, subagent_run), MCP, y de
extensiones. Esto se logra via `_wrap_tool_with_events()` en `tools.py`.

### Event handler return values

- `tool_call` — return `{"block": True, "reason": "..."}` to block execution
- Other events — return values are collected but not acted on

---

## Bloqueo de tools

```python
@on("tool_call")
def block_rm(self, event):
    if event.get("tool_name") == "bash":
        cmd = event.get("input", {}).get("command", "")
        if "rm -rf" in cmd or "sudo" in cmd:
            return {"block": True, "reason": "Blocked by safety extension"}
    return None
```

Esto funciona para **cualquier tool**: read, write, bash, edit, web_search,
subagent_run, MCP tools, y otras extensiones.

---

## Tools disponibles

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
# Desde un agente markdown
subagent_run(task="Review this code", agent="reviewer")

# Con instrucciones inline
subagent_run(
  task="Check for security issues",
  instructions="You are a security auditor."
)
```

### web_search

```python
web_search(query="ultimos avances IA 2026")
```

Usa DuckDuckGo HTML search. No requiere API key.

---

## Ciclo de vida

1. **Discovery** — Tau escanea los directorios de extensiones al arrancar
2. **Load** — cada `.py` se importa y las subclases de `Extension` se instancian
3. **on_load()** — llamado despues de instanciar (override para setup)
4. **Registration** — tools, commands, y handlers se recolectan de los metodos decorados
5. **on_unload()** — llamado cuando se descargan las extensiones

---

## vs MCP

| Aspecto | Extension | MCP Server |
|---------|-----------|------------|
| Lenguaje | Python | Cualquiera |
| Proceso | Dentro de Tau | Proceso separado |
| Distribucion | Archivo `.py` | Paquete npm/PyPI/binario |
| Aislamiento | Comparte proceso con Tau | Proceso aislado |
| Ideal para | Tools chicas, eventos, blocking | Tools complejas, ecosistema externo |

---

## Arquitectura

- `src/tau_coding/extensions.py` — core (Extension, Registry, decorators)
- `src/tau_coding/tools.py` — `_wrap_tool_with_events()` dispatches events
- `src/tau_coding/agents.py` — agent markdown loading
- Loader: Python `importlib`
- Event dispatch: sincronico (no bloquear por mucho tiempo)
