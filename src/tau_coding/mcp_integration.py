"""MCP (Model Context Protocol) integration for Tau.

Connects Tau to MCP servers so their tools appear as native AgentTool
instances. Configured in ``.tau/mcp.toml`` or ``~/.tau/mcp.toml``.

Usage::

    # .tau/mcp.toml
    [[servers]]
    name = "github"
    transport = "stdio"
    command = "npx"
    args = ["-y", "@modelcontextprotocol/server-github"]
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from tau_agent.types import JSONValue


@dataclass
class McpServerConfig:
    """Configuration for one MCP server."""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class McpToolInfo:
    """A tool discovered from an MCP server."""

    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


class McpRegistry:
    """Manages MCP server connections and tool discovery."""

    def __init__(self) -> None:
        self._servers: dict[str, McpServerConfig] = {}
        self._sessions: dict[str, Any] = {}
        self._tools: list[McpToolInfo] = []
        self._connected = False

    def add_server(self, config: McpServerConfig) -> None:
        """Register an MCP server configuration."""
        self._servers[config.name] = config

    async def connect_all(self) -> list[str]:
        """Connect to all registered MCP servers and discover tools."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        connected: list[str] = []
        for name, config in self._servers.items():
            try:
                if config.transport == "stdio" and config.command:
                    env = dict(os.environ)
                    env.update(config.env)
                    params = type("Params", (), {
                        "command": config.command,
                        "args": list(config.args),
                        "env": env,
                    })()
                    streams = await stdio_client(params)
                    session = await ClientSession(streams[0], streams[1]).__aenter__()
                    self._sessions[name] = (session, streams)
                    await session.initialize()
                    result = await session.list_tools()
                    for tool in result.tools:
                        self._tools.append(McpToolInfo(
                            server_name=name,
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                        ))
                    connected.append(name)
                elif config.transport == "http" and config.url:
                    # HTTP transport - simplified for now
                    from mcp.client.http import http_client
                    session = await http_client(config.url)
                    await session.initialize()
                    self._sessions[name] = (session, None)
                    result = await session.list_tools()
                    for tool in result.tools:
                        self._tools.append(McpToolInfo(
                            server_name=name,
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {},
                        ))
                    connected.append(name)
            except Exception as exc:
                import traceback
                traceback.print_exc()
        self._connected = True
        return connected

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name, (session, streams) in self._sessions.items():
            try:
                await session.__aexit__(None, None, None)
                if streams:
                    await streams[0].aclose()
                    await streams[1].aclose()
            except Exception:
                pass
        self._sessions.clear()
        self._tools.clear()
        self._connected = False

    def get_tools(self) -> list[McpToolInfo]:
        """Return all discovered MCP tools."""
        return list(self._tools)

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call a tool on an MCP server."""
        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"MCP server not connected: {server_name}")
        result = await session[0].call_tool(tool_name, arguments)
        return result


# Global singleton
_default_mcp: McpRegistry | None = None


def get_mcp_registry() -> McpRegistry:
    """Return or create the global MCP registry singleton."""
    global _default_mcp
    if _default_mcp is None:
        _default_mcp = McpRegistry()
    return _default_mcp


# ── config loading ──────────────────────────────────────────────────────


def load_mcp_config(cwd: Path | None = None) -> list[McpServerConfig]:
    """Load MCP server config from .tau/mcp.toml or ~/.tau/mcp.toml."""
    import tomllib

    configs: list[McpServerConfig] = []
    resolved_cwd = cwd or Path.cwd()

    # Project-local config
    candidates = [
        resolved_cwd / ".tau" / "mcp.toml",
        Path.home() / ".tau" / "mcp.toml",
    ]
    for path in candidates:
        if path.exists():
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            for server_raw in raw.get("servers", []):
                configs.append(McpServerConfig(
                    name=server_raw.get("name", ""),
                    transport=server_raw.get("transport", "stdio"),
                    command=server_raw.get("command", ""),
                    args=tuple(server_raw.get("args", [])),
                    url=server_raw.get("url", ""),
                    env=dict(server_raw.get("env", {})),
                ))
    return configs


# ── convert MCP tools to AgentTool ──────────────────────────────────────


async def call_mcp_tool(
    registry: McpRegistry,
    server_name: str,
    mcp_tool: McpToolInfo,
    arguments: Mapping[str, JSONValue],
) -> AgentToolResult:
    """Execute an MCP tool and return an AgentToolResult."""
    try:
        result = await registry.call_tool(server_name, mcp_tool.name, dict(arguments))
        content_parts: list[str] = []
        if hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                elif isinstance(item, dict):
                    content_parts.append(str(item.get("text", "")))
        return AgentToolResult(
            tool_call_id="mcp",
            name=mcp_tool.name,
            ok=True,
            content="\n".join(content_parts) or "(empty result)",
            data={"server": server_name},
        )
    except Exception as exc:
        return AgentToolResult(
            tool_call_id="mcp",
            name=mcp_tool.name,
            ok=False,
            content=f"MCP error: {exc}",
            error=str(exc),
            data={"server": server_name},
        )


def mcp_tool_to_agent_tool(
    registry: McpRegistry,
    server_name: str,
    mcp_tool: McpToolInfo,
) -> AgentTool:
    """Wrap an MCP tool as an AgentTool."""
    input_schema: dict[str, JSONValue] = mcp_tool.input_schema or {
        "type": "object",
        "properties": {},
    }

    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        return await call_mcp_tool(registry, server_name, mcp_tool, arguments)

    return AgentTool(
        name=f"mcp_{server_name}_{mcp_tool.name}",
        description=f"[MCP {server_name}] {mcp_tool.description}",
        input_schema=input_schema,
        executor=executor,
        prompt_snippet=f"MCP tool from {server_name}: {mcp_tool.description}",
    )
