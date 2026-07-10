---
title: Harness system
description: Define custom agent personalities with .tau/harness.toml — configure system prompts, tools, providers, approval policies, and sandboxing.
---

A **harness** is a TOML configuration file that defines an agent's personality,
available tools, provider selection, approval policies, and sandbox
restrictions. Harnesses let you tailor Tau for different domains — a coding
agent, a documentation agent, a review agent — each with its own system prompt
and toolset.

## How it works

Place a `.tau/harness.toml` in your project root. Tau auto-detects it on
startup:

```bash
cd my-project
tau          # auto-loads .tau/harness.toml
```

You can also switch harnesses explicitly:

```bash
tau --harness legal       # loads .tau/harnesses/legal.toml
tau --harness review      # loads ~/.tau/harnesses/review.toml
```

### Discovery order

Tau searches in this order (first match wins):

1. `.tau/harnesses/<name>.toml` — named project harness
2. `.tau/harness.toml` — default project harness (when name is `default` or omitted)
3. `~/.tau/harnesses/<name>.toml` — named user-level harness
4. Built-in "coding" harness — the implicit fallback

## Configuration reference

```toml
# .tau/harness.toml
name = "coding"
description = "Coding agent with file/shell tools"

[personality]
system_prompt = """
You are an expert coding assistant.
You help users read, write, edit, and debug code.
"""
guidelines = [
    "Always explain your reasoning before making changes.",
    "Ask for clarification when requirements are ambiguous.",
]

[provider]
name = "openai"
model = "gpt-4o"
thinking = "medium"

[tools]
builtin = ["read", "write", "edit", "bash"]
extensions = ["my_custom_tool"]

[approval]
default = "allow"           # "allow", "deny", or "ask"

[approval.rules]
bash = "ask"                # per-tool override
write = "deny"

[sandbox]
mode = "strict"             # "permissive" or "strict"
allowed_paths = ["data", "outputs"]
allow_home_tau = true
allow_temp = true
```

### `[personality]` — the agent's persona

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `system_prompt` | string | Built-in coding prompt | The agent's system prompt |
| `guidelines` | string[] | `[]` | Additional behavioral guidelines appended to the prompt |

The system prompt can also come from a `SYSTEM.md` file alongside the harness
TOML. If `SYSTEM.md` exists, it takes precedence over `system_prompt` in the
TOML. An `APPEND_SYSTEM.md` file, if present, is appended after the prompt.

### `[provider]` — default provider and model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `""` | Provider name (e.g. `"openai"`, `"anthropic"`) |
| `model` | string | `""` | Default model for this harness |
| `thinking` | string | `""` | Default thinking level (`"off"`, `"low"`, `"medium"`, `"high"`) |

### `[tools]` — which tools are available

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `builtin` | string[] | `["read", "write", "edit", "bash"]` | Built-in tools to expose |
| `extensions` | string[] | `[]` | Names of extension-provided tools to include |

### `[approval]` — tool approval chain

Controls which tools require user confirmation before executing.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default` | string | `"allow"` | Default policy: `"allow"`, `"deny"`, or `"ask"` |
| `rules` | table | `{}` | Per-tool overrides: `{tool_name = "allow" \| "deny" \| "ask"}` |

When a tool resolves to `"ask"`, Tau checks the [trust store]({{< relref "./trust-system.md" >}})
for a persistent approval decision. If the tool is trusted, it runs; otherwise
the user is prompted to approve or trust it.

### `[sandbox]` — path access restrictions

Controls which filesystem paths the agent's file tools may access. See
[Sandboxing]({{< relref "./sandboxing.md" >}}) for details.

## Using `SYSTEM.md` and `APPEND_SYSTEM.md`

For complex system prompts, keep them in Markdown files alongside the harness
TOML:

```text
.tau/
├── harness.toml
├── SYSTEM.md        # replaces [personality].system_prompt
└── APPEND_SYSTEM.md # appended after SYSTEM.md or system_prompt
```

The `SYSTEM.md` file takes precedence over the inline `system_prompt` field.
`APPEND_SYSTEM.md` is appended to whatever the final system prompt is.

## Listing available harnesses

```bash
tau --list-harnesses
```

This shows all discoverable harnesses with their names and descriptions,
including the built-in "coding" harness.

## See also

- [Sandboxing]({{< relref "./sandboxing.md" >}}) — path sandbox configuration
- [Trust system]({{< relref "./trust-system.md" >}}) — persistent tool approval
- [Extensions]({{< relref "./extensions.md" >}}) — custom tools and event handlers
