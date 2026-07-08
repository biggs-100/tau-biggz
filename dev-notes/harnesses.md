# Custom Harnesses — Guia completa

Un harness define **todo** lo que un agente de Tau necesita para trabajar:
personalidad, herramientas, sub-agentes, servidores MCP, y mas.

Los harnesses son portables: podes copiar un `.tau/` entero de un proyecto
a otro y llevar toda la configuracion del agente con vos.

---

## Indice

1. [Quick start](#quick-start)
2. [Schema TOML completo](#schema-toml-completo)
3. [Agentes como markdown](#agentes-como-markdown)
4. [Orquestador + subagentes](#orquestador--subagentes)
5. [Servidores MCP](#servidores-mcp)
6. [Extensiones Python](#extensiones-python)
7. [Tool filtering](#tool-filtering)
8. [Global vs proyecto](#global-vs-proyecto)
9. [Ejemplos completos](#ejemplos-completos)
10. [Arquitectura](#arquitectura)

---

## Quick start

### 1. Crea el harness

```bash
mkdir -p mi-proyecto/.tau
```

Crea `mi-proyecto/.tau/harness.toml`:

```toml
name = "legal"
description = "Corporate law assistant"

[personality]
system_prompt = """
You are a corporate law assistant.
Help with contract review, legal research, and document drafting.
Maintain a formal and precise tone.
"""

[tools]
builtin = ["read", "write"]
```

### 2. Corre Tau

```bash
cd mi-proyecto
tau   # auto-detecta .tau/harness.toml
```

Eso es todo. Tau usa el system prompt del harness, filtra tools, y arranca.

---

## Schema TOML completo

```toml
name = "mi-harness"                  # requerido: identificador unico
description = "Que hace"             # opcional: descripcion legible

[personality]
system_prompt = """                  # reemplaza el prompt default de coding
You are an assistant specialized in...
"""
guidelines = []                      # opcional: reglas adicionales (reservado)

[provider]                           # opcional: provider default para este harness
name = "opencode-zen"                # nombre del provider (debe estar configurado via /login)
model = "gpt-5.5"                    # modelo default
thinking = "medium"                  # nivel de thinking default

[tools]
builtin = ["read", "write"]          # tools built-in habilitadas
                                     # default: todas (read, write, edit, bash)
                                     # si esta vacio, solo tools de extensiones/MCP
extensions = []                      # tools de extensiones (reservado)

[[subagents]]                        # sub-agentes disponibles para el orquestador
name = "planner"
instructions = "You are a senior architect. Create plans."
tools = ["read", "web_search"]

[[subagents]]
name = "reviewer"
instructions = "You are a strict code reviewer."
tools = ["read"]
```

### Campos opcionales

| Campo | Default | Descripcion |
|-------|---------|-------------|
| `provider.name` | (default del usuario) | Provider a usar |
| `provider.model` | (default del provider) | Modelo default |
| `provider.thinking` | `"medium"` | Thinking level inicial |
| `tools.builtin` | `["read", "write", "edit", "bash"]` | Tools built-in activas |
| `subagents` | `[]` | Lista de sub-agentes disponibles |

---

## Agentes como markdown

Los sub-agentes se definen como archivos markdown con frontmatter YAML.
Esto permite tener agentes complejos sin ensuciar el harness.toml.

### Ubicacion

```
.tau/agents/            ← proyecto
~/.tau/agents/          ← global
```

### Formato

```markdown
---
name: planner
description: Senior architect that creates plans
tools: [read, web_search]
---

You are a senior architect. Break down complex tasks into step-by-step
implementation plans. Consider edge cases, dependencies, risks, and
recommend the best approach. Be specific and actionable.
```

### Uso desde subagent_run

El orquestador llama:

```python
subagent_run(
  task="Plan the implementation of the payment module",
  agent="planner"
)
```

Esto:
1. Busca `.tau/agents/planner.md`
2. Parsea el frontmatter: `name`, `description`, `tools`
3. Usa el body como system prompt del sub-agente
4. Crea un `AgentHarness` limpio con ese prompt
5. Ejecuta la tarea
6. Devuelve el resultado

### Ventajas

- **Sin impacto en tokens**: la definicion del agente NO esta en el prompt del orquestador
- **Carga bajo demanda**: solo se lee el archivo cuando `subagent_run(agent="...")` se ejecuta
- **Contexto fresco**: cada sub-agente arranca sin historial
- **Portable**: podes copiar `.tau/agents/` entre proyectos

### Ejemplo: planner + reviewer

```markdown
---
name: reviewer
description: Code reviewer focused on security
tools: [read]
---

You are a strict code reviewer. Find bugs, security vulnerabilities,
and bad practices. Report each finding with severity (BLOCKER,
CRITICAL, WARNING, SUGGESTION), the exact file/line, and why it
matters. If the code is clean, say "No findings."
```

```python
# El orquestador lo usa asi:
subagent_run(task="Review src/auth.py for security issues", agent="reviewer")
```

---

## Orquestador + subagentes

El orquestador es el agente principal. Su personalidad se define en
`[personality]` del harness. El orquestador usa `subagent_run()`
para delegar trabajo a sub-agentes.

### Como funciona

1. El orquestador recibe el objetivo del usuario
2. Decide que sub-agentes necesita
3. Llama `subagent_run(task, agent="name")` para cada uno
4. Recolecta los resultados
5. Decide el siguiente paso

### Ejemplo de orquestador

```toml
name = "dev-team"
description = "Development team with planner + reviewer sub-agents"

[personality]
system_prompt = """
You are a project lead. You decompose tasks and delegate them to your team.

Team workflow:
1. Call subagent_run with agent="planner" to create a plan
2. Review the plan
3. Execute the implementation yourself (you have read/write/edit/bash)
4. Call subagent_run with agent="reviewer" to review the result
5. Fix any issues found
"""

[tools]
builtin = ["read", "write", "edit", "bash"]

[[subagents]]
name = "planner"
instructions = "You are a senior architect. Create detailed plans."

[[subagents]]
name = "reviewer"
instructions = "You are a strict code reviewer. Find bugs and vulnerabilities."
```

### subagent_run API

```python
# Usar un agente markdown
subagent_run(task="Review this code", agent="reviewer")

# Usar instrucciones inline (sin archivo markdown)
subagent_run(
  task="Check for security issues",
  instructions="You are a security auditor. Find vulnerabilities."
)

# Ambos: instructions sobreescribe al agente si se proveen ambos
```

### Tips para el orquestador

- Definí el workflow en el `system_prompt` del harness
- Usá agentes markdown para sub-agentes reutilizables
- Usá `instructions` inline para tareas unicas
- Cada sub-agente arranca limpio, no arrastra contexto

---

## Servidores MCP

MCP (Model Context Protocol) conecta Tau con servidores externos que
exponen tools adicionales.

### Configuracion

```toml
# .tau/mcp.toml
[[servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]

[[servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "tu-token" }

[[servers]]
name = "custom-api"
transport = "http"
url = "http://localhost:3456"
```

### Como funciona

1. Tau lee `.tau/mcp.toml` al iniciar la sesion
2. Conecta a cada servidor MCP
3. Descubre las tools disponibles (`list_tools`)
4. Las expone como `AgentTool` con prefijo `mcp_<server>_<tool>`
5. Al cerrar la sesion, desconecta los servidores

### Usar MCP tools en el harness

MCP tools se agregan automaticamente a la lista de tools. Si tu harness
filtra con `tools.builtin`, las MCP tools igual estan disponibles porque
el filtro solo aplica a built-in tools.

### Ejemplo: harness con MCP + agentes

```toml
name = "devops"
description = "DevOps assistant with GitHub + filesystem access"

[personality]
system_prompt = """
You are a DevOps assistant. You have access to GitHub and filesystem
via MCP servers. Use them to manage repos, issues, and files.
"""

[[subagents]]
name = "investigator"
instructions = "You are an investigator. Research issues in GitHub."
```

Y `.tau/mcp.toml`:

```toml
[[servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
```

---


### Comandos tau mcp

```bash
# Buscar servers en npm
tau mcp search filesystem

# Instalar un server (agrega a .tau/mcp.toml)
tau mcp install @modelcontextprotocol/server-filesystem

# Listar servers instalados
tau mcp list

# Remover un server
tau mcp remove filesystem
```

Al instalar un paquete, Tau genera automaticamente la entrada en `.tau/mcp.toml`
usando `npx -y <package>` como comando STDIO. La proxima vez que inicies Tau,
el server se conectara automaticamente y sus tools estaran disponibles.


## Extensiones Python

Las extensiones permiten agregar tools, comandos slash, y event handlers
personalizados sin modificar Tau.

### Crear una extension

```python
# .tau/extensions/mi_ext.py
from tau_coding.extensions import Extension, tool, command, on

class MiExt(Extension):
    @tool("saludar", "Saluda a alguien")
    def saludar(self, name: str = "mundo") -> str:
        return f"Hola, {name}!"

    @command("ping", description="Pong")
    def ping(self, args: str) -> str:
        return "pong"

    @on("tool_call")
    def bloquear_rm(self, event):
        if event.get("tool_name") == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd:
                return {"block": True, "reason": "Comando bloqueado por seguridad"}
        return None
```

### Ubicacion

```
.tau/extensions/         ← proyecto
~/.tau/extensions/       ← global
```

### Eventos disponibles

| Evento | Payload | Cuando |
|--------|---------|--------|
| `session_start` | `{}` | Inicio de sesion |
| `session_end` | `{}` | Fin de sesion |
| `tool_call` | `{tool_name, input, tool_call_id}` | Antes de EJECUTAR cualquier tool |
| `after_tool_call` | `{tool_name, input, result}` | Despues de cualquier tool |
| `before_prompt` | `{content}` | Antes de procesar un prompt |
| `after_prompt` | `{content, response}` | Despues de responder |

### Bloquear tools desde extensiones

```python
@on("tool_call")
def bloquear(self, event):
    if event.get("tool_name") == "bash":
        cmd = event.get("input", {}).get("command", "")
        if "rm -rf" in cmd:
            return {"block": True, "reason": "Destructive command blocked"}
    return None
```

El bloqueo funciona para TODAS las tools: built-in, MCP, y de extensiones.

---

## Tool filtering

El harness puede restringir que tools built-in estan disponibles.

### Ejemplos

```toml
# Solo lectura (agente legal/reviewer)
[tools]
builtin = ["read"]

# Lectura + web (agente investigador)
[tools]
builtin = ["read", "web_search"]

# Todas excepto bash (agente seguro)
[tools]
builtin = ["read", "write", "edit"]

# Solo herramientas de extensiones y MCP (sin built-in)
[tools]
builtin = []

# Todas las tools (default si se omite)
# builtin = ["read", "write", "edit", "bash"]
```

### Notas

- `web_search` y `subagent_run` siempre estan disponibles si no se filtra
- MCP tools NO se filtran (siempre disponibles si el servidor responde)
- Extension tools NO se filtran (siempre disponibles si la extension esta cargada)

---

## Global vs proyecto

Los harnesses pueden vivir en dos niveles:

### Proyecto (`.tau/`)

```
mi-proyecto/
├── .tau/
│   ├── harness.toml          ← harness de este proyecto
│   ├── agents/
│   │   ├── planner.md
│   │   └── reviewer.md
│   ├── extensions/
│   │   └── mi_ext.py
│   ├── mcp.toml              ← servidores MCP
│   └── skills/               ← skills markdown
```

### Global (`~/.tau/`)

```
~/.tau/
├── harnesses/                ← harnesses reutilizables
│   ├── legal.toml
│   └── accounting.toml
├── agents/                   ← agentes globales
├── extensions/               ← extensiones globales
└── mcp.toml                  ← MCP servers globales
```

### Orden de resolucion

```
1. .tau/harnesses/<name>.toml    explicito
2. .tau/harness.toml             default del proyecto
3. ~/.tau/harnesses/<name>.toml  global
4. coding (built-in)             implicito, sin archivo
```

Los archivos del proyecto tienen prioridad sobre los globales.

---

## Ejemplos completos

### Harness: Legal (asistente juridico)

```toml
name = "legal"
description = "Corporate law assistant with research tools"

[personality]
system_prompt = """
You are a corporate law assistant at a law firm.
Help lawyers with:
- Contract review and drafting
- Legal research
- Document organization
- Citation checking

Maintain a formal and precise tone. When unsure, say so.
"""

[tools]
builtin = ["read", "write", "web_search"]

[[subagents]]
name = "researcher"
instructions = "You are a legal researcher. Find relevant cases and legislation."
tools = ["web_search"]

[[subagents]]
name = "reviewer"
instructions = "You are a senior partner reviewing documents. Check for errors."
tools = ["read"]
```

### Harness: DevOps (ingeniero de plataforma)

Ubicar en `.tau/harness.toml`:

```toml
name = "devops"
description = "DevOps engineer with infrastructure tools"

[personality]
system_prompt = """
You are a senior DevOps engineer.
You manage infrastructure, deployments, and monitoring.
Use MCP servers to interact with GitHub and your infrastructure.
"""

[tools]
builtin = ["read", "write", "edit", "bash", "web_search"]

[[subagents]]
name = "investigator"
instructions = "You investigate production issues. Be thorough."
tools = ["read", "web_search", "bash"]
```

Y `.tau/mcp.toml`:

```toml
[[servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
```

### Harness: Data analyst

```toml
name = "analyst"
description = "Data analyst assistant"

[personality]
system_prompt = """
You are a data analyst. Help users understand their data.
You can read files, search the web, and delegate research.
"""

[tools]
builtin = ["read", "write", "web_search"]

[[subagents]]
name = "researcher"
instructions = "You research data sources and methodologies."
tools = ["web_search"]
```

---

## Arquitectura

```
.tau/harness.toml
    ↓ parse
HarnessDefinition (harness.py)
    ↓
CLI: --harness, --list-harnesses
    ↓
set_active_harness() (harness.py)
    ↓
Session init:
  ├─ _harness_filtered_tools()     filtra tools segun [tools]
  ├─ _harness_system_prompt()      usa [personality] + [[subagents]]
  ├─ McpRegistry.connect_all()     conecta servidores MCP
  └─ AgentHarness creado con:
       ├─ system prompt del harness
       ├─ tools filtradas + MCP + extensiones
       └─ provider configurado
```

### Componentes

| Archivo | Rol |
|---------|-----|
| `src/tau_coding/harness.py` | HarnessDefinition, load, parser, global state |
| `src/tau_coding/agents.py` | Agent markdown parser, discovery |
| `src/tau_coding/mcp_integration.py` | MCP server connection, tool wrapping |
| `src/tau_coding/extensions.py` | Extension system (tools, commands, events) |
| `src/tau_coding/tools.py` | Built-in tools + subagent_run + web_search |
| `src/tau_coding/session.py` | _harness_filtered_tools, _harness_system_prompt |
| `src/tau_coding/cli.py` | --harness, --list-harnesses flags |

### Flujo de subagent_run

```
Orquestador llama subagent_run(task, agent="planner")
    ↓
create_subagent_tool() busca .tau/agents/planner.md
    ↓
agents.load_agent() parsea frontmatter + body
    ↓
Crea AgentHarness con:
  - system prompt = body del markdown
  - tools = [] (sin tools del orquestador)
  - provider = mismo que el orquestador
    ↓
Ejecuta task en contexto limpio
    ↓
Devuelve resultado al orquestador
```
