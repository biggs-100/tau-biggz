"""MCP server management commands for Tau CLI.

Usage::
    tau mcp search <query>     Search for MCP packages
    tau mcp install <package>  Install an MCP server
    tau mcp list               List installed servers
    tau mcp remove <name>      Remove a server
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import tomllib


def mcp_install(package: str) -> str:
    """Install an MCP server package and add to .tau/mcp.toml."""
    name = _package_to_name(package)
    path = _mcp_config_path()

    configs = _load_configs()
    for s in configs:
        if s.get("name") == name:
            return f"MCP server '{name}' is already installed."

    entry = _entry_for_package(package, name)
    configs.append(entry)
    _save_configs(configs)

    return f"Installed MCP server '{name}'. Added to {path}"


def mcp_remove(name: str) -> str:
    """Remove an MCP server from the config."""
    path = _mcp_config_path()
    configs = _load_configs()
    before = len(configs)
    configs = [s for s in configs if s.get("name") != name]
    if len(configs) == before:
        return f"MCP server '{name}' not found."
    _save_configs(configs)
    return f"Removed MCP server '{name}' from {path}"


def mcp_list() -> list[dict[str, str]]:
    """List installed MCP servers."""
    return [
        {"name": s.get("name", "?"), "transport": s.get("transport", "?"), "command": s.get("command", s.get("url", "?"))}
        for s in _load_configs()
    ]


def mcp_search(query: str) -> list[dict[str, str]]:
    """Search for MCP packages (stub - queries npm registry)."""
    import httpx
    try:
        resp = httpx.get(
            f"https://registry.npmjs.org/-/v1/search",
            params={"text": f"modelcontextprotocol {query}", "size": 10},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            results.append({
                "name": pkg.get("name", ""),
                "description": pkg.get("description", ""),
                "version": pkg.get("version", ""),
            })
        return results
    except Exception:
        return [{"name": f"npm:@modelcontextprotocol/server-{query}", "description": f"MCP server for {query}", "version": "latest"}]


def _package_to_name(package: str) -> str:
    """Derive a server name from a package identifier."""
    name = package.strip()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name.startswith("server-"):
        name = name[7:]
    return name


def _entry_for_package(package: str, name: str) -> dict[str, Any]:
    """Create an MCP server config entry for a package."""
    package = package.strip()
    entry: dict[str, Any] = {
        "name": name,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", package],
    }
    return entry


def _mcp_config_path() -> Path:
    """Return the project-local MCP config path."""
    return Path.cwd() / ".tau" / "mcp.toml"


def _load_configs() -> list[dict[str, Any]]:
    """Load existing MCP server configs."""
    path = _mcp_config_path()
    if not path.exists():
        return []
    try:
        raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("servers", []))
    except Exception:
        return []


def _save_configs(configs: list[dict[str, Any]]) -> None:
    """Save MCP server configs to TOML."""
    path = _mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Tau MCP server configuration\n"]
    for s in configs:
        lines.append("[[servers]]\n")
        lines.append(f'name = "{s["name"]}"\n')
        lines.append(f'transport = "{s["transport"]}"\n')
        lines.append(f'command = "{s["command"]}"\n')
        if s.get("args"):
            args_str = ", ".join(f'"{a}"' for a in s["args"])
            lines.append(f"args = [{args_str}]\n")
        if s.get("url"):
            lines.append(f'url = "{s["url"]}"\n')
        if s.get("env"):
            lines.append("[servers.env]\n")
            for k, v in s["env"].items():
                lines.append(f'{k} = "{v}"\n')
        lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")
