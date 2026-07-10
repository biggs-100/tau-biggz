---
title: Model Context Protocol (MCP)
description: Connect Tau to MCP servers so their tools appear as native agent tools — extending Tau's capabilities through the Model Context Protocol.
---

The **Model Context Protocol** (MCP) is an open standard for connecting AI
agents to external tools and data sources. Tau can connect to MCP servers so
their tools appear as native `AgentTool` instances, callable by the model
alongside built-in tools like `read` and `bash`.

## How it works

MCP servers are configured in `.tau/mcp.toml` (project-level) or
`~/.tau/mcp.toml` (user-level). Each server definition specifies a transport
(stdio or HTTP) and how to launch or reach the server.

```toml
# .tau/mcp.toml
[[servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]

[[servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]

[[servers]]
name = "custom-api"
transport = "http"
url = "http://localhost:3000/mcp"
```

When Tau starts, it reads the MCP config, connects to each server, and
discovers available tools. Each discovered tool is registered with a prefixed
name like `mcp_github_search_repositories` so the model can call it.

### Configuration fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique server identifier |
| `transport` | string | yes | `"stdio"` or `"http"` |
| `command` | string | for stdio | The executable to launch |
| `args` | string[] | no | Arguments passed to the command |
| `url` | string | for HTTP | The MCP server URL |
| `env` | table | no | Extra environment variables for the server |

## The `tau mcp` commands

Use the `tau mcp` subcommands to manage MCP servers without editing TOML files
by hand:

### `tau mcp search`

Search the npm registry for MCP server packages:

```bash
tau mcp search github
tau mcp search filesystem
```

Returns matching packages with their name, description, and latest version.

### `tau mcp install`

Install an MCP server package and add it to `.tau/mcp.toml`:

```bash
tau mcp install @modelcontextprotocol/server-github
tau mcp install @modelcontextprotocol/server-filesystem
```

This runs `npx -y <package>` under the hood and creates a `[[servers]]` entry
in `.tau/mcp.toml`.

### `tau mcp list`

List all installed MCP servers:

```bash
tau mcp list
```

Shows each server's name, transport, and command or URL.

### `tau mcp remove`

Remove a server from the configuration:

```bash
tau mcp remove github
```

Removes the matching `[[servers]]` entry from `.tau/mcp.toml`.

## How tools are exposed

Discovered MCP tools are wrapped as `AgentTool` instances with prefixed names:

| MCP tool | Tau tool name |
|----------|---------------|
| `search_repositories` | `mcp_github_search_repositories` |
| `create_issue` | `mcp_github_create_issue` |
| `read_file` | `mcp_filesystem_read_file` |

The prefix helps the model distinguish between tools from different servers and
avoid naming conflicts with built-in tools.

## Config location and precedence

Tau loads MCP configuration from:

1. `.tau/mcp.toml` — project-local, checked first
2. `~/.tau/mcp.toml` — user-level fallback

Both files are loaded if they exist. Servers from both files are merged, with
project-level entries taking precedence on name conflicts.

## Reloading MCP servers

If you modify `.tau/mcp.toml` while the TUI is open, run **`/reload`** to
disconnect and reconnect all MCP servers. This discovers new tools and applies
configuration changes without restarting Tau.

## See also

- [Configuration]({{< relref "../reference/configuration.md" >}}) — MCP server configuration reference
- [Harness system]({{< relref "./harness.md" >}}) — controlling which tools are available
- [Extensions]({{< relref "./extensions.md" >}}) — adding custom tools without MCP
