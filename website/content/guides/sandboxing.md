---
title: Sandboxing
description: Restrict which filesystem paths Tau's file tools can access — preventing accidental writes outside your project.
---

Path sandboxing restricts which directories Tau's built-in file tools
(`read`, `write`, `edit`) may access. In **strict** mode, any path that
resolves outside the project working directory (or explicitly permitted
directories) is rejected with a clear error message.

## How it works

Sandbox validation runs before every file-tool invocation. When strict mode is
active, the resolved path is checked against:

1. **Explicitly allowed paths** from the sandbox configuration
2. **`~/.tau/`** — allowed by default (configurable)
3. **System temp directory** — allowed by default (configurable)
4. **The project working directory** — always allowed

If none of these match, the tool call is rejected.

## Configuration

Sandbox settings live in your [harness configuration]({{< relref "./harness.md" >}}):

```toml
# .tau/harness.toml
[sandbox]
mode = "strict"              # "permissive" or "strict"
allowed_paths = [
    "data",
    "outputs/reports",
    "/shared/cache"
]
allow_home_tau = true         # allow ~/.tau/ paths
allow_temp = true             # allow system temp directory
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"permissive"` | `"strict"` enables sandbox validation; `"permissive"` disables it |
| `allowed_paths` | string[] | `[]` | Paths (relative to project root or absolute) that are always allowed |
| `allow_home_tau` | bool | `true` | Allow paths under `~/.tau/` |
| `allow_temp` | bool | `true` | Allow system temporary directory |

## The `--unsafe` flag

Pass `--unsafe` at startup to disable sandbox restrictions for the current
session:

```bash
tau --unsafe
```

This sets the sandbox mode to `"permissive"` for the session, overriding
the harness configuration.

## Validation behavior

When a path is rejected, Tau shows a clear error:

```
Path '/etc/passwd' resolves outside the working directory '/home/user/project'.
To allow it, add the path to [sandbox].allowed_paths in your harness config,
or use --unsafe to disable sandboxing for this session.
```

### What happens in permissive mode

When `mode` is `"permissive"` (the default), sandbox validation is a no-op —
all paths are allowed. This matches Tau's original behavior and is suitable for
single-project work where the agent only touches project files.

### What happens in strict mode

Every file-tool call (`read`, `write`, `edit`) validates the target path:

1. **Resolve** the path (expand symlinks, normalize).
2. **Check allowed_paths** — if the resolved path is under any listed path,
   allow it.
3. **Check `~/.tau/`** — if `allow_home_tau` is true and the path is under
   `~/.tau/`, allow it.
4. **Check temp directory** — if `allow_temp` is true and the path is under
   the system temp directory, allow it.
5. **Check working directory** — if the path is under the project working
   directory, allow it.
6. **Reject** — if nothing matched, raise a `ToolInputError`.

## Example scenarios

### Allow writes to a shared data directory

```toml
[sandbox]
mode = "strict"
allowed_paths = ["data", "/mnt/shared/corpus"]
allow_home_tau = false
```

This lets the agent read/write files under `./data/` and `/mnt/shared/corpus/`,
but blocks access to `~/.tau/` and any path outside those directories and the
project root.

### Lock down for sensitive projects

```toml
[sandbox]
mode = "strict"
allowed_paths = []
allow_home_tau = false
allow_temp = false
```

Only the project working directory is accessible. No `~/.tau/` paths, no temp
files.

### Fully open (default behavior)

```toml
[sandbox]
mode = "permissive"
```

No sandbox restrictions. The agent can read/write any path the user has
permission to access.

## Sandbox vs. approval chain

Sandboxing and the [approval chain]({{< relref "./trust-system.md" >}}) serve
different purposes:

| Mechanism | What it controls | How it works |
|-----------|-----------------|--------------|
| **Sandbox** | Which paths file tools can touch | Automatic path validation; no user prompt |
| **Approval chain** | Which tools the model may invoke | Policy rules + trust store + extension handlers |

You can use both together: lock paths with sandboxing, and require approval for
specific tools with the approval chain.

## See also

- [Harness system]({{< relref "./harness.md" >}}) — complete harness configuration
- [Trust system]({{< relref "./trust-system.md" >}}) — tool-level approval
- [Configuration]({{< relref "../reference/configuration.md" >}}) — sandbox config reference
