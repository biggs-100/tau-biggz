"""Agent-as-markdown system for Tau harnesses.

Sub-agents are defined as markdown files with YAML frontmatter::

    ---
    name: planner
    description: Senior architect
    tools: [read, web_search]
    ---

    You are a senior architect. Break down complex tasks.

Agents are auto-discovered from:

- ``.tau/agents/*.md`` (project)
- ``~/.tau/agents/*.md`` (global)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentDef:
    """A sub-agent defined in a markdown file."""

    name: str
    description: str = ""
    tools: tuple[str, ...] = ()
    system_prompt: str = ""
    source_path: str = ""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_agent_markdown(text: str, *, source: str = "") -> AgentDef:
    """Parse a markdown file with YAML frontmatter into an AgentDef."""
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        return AgentDef(
            name=Path(source).stem if source else "unnamed",
            system_prompt=text.strip(),
            source_path=source,
        )

    yaml_text = match.group(1)
    body = match.group(2).strip()
    meta = _parse_yaml_like(yaml_text)

    return AgentDef(
        name=meta.get("name", Path(source).stem if source else "unnamed"),
        description=meta.get("description", ""),
        tools=tuple(meta.get("tools", [])),
        system_prompt=body,
        source_path=source,
    )


def _parse_yaml_like(text: str) -> dict[str, Any]:
    """Simple YAML frontmatter parser (no dependency)."""
    result: dict[str, Any] = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        parsed: Any = raw.strip()
        if parsed.startswith("[") and parsed.endswith("]"):
            parsed = [v.strip().strip("\"'") for v in parsed[1:-1].split(",") if v.strip()]
        else:
            parsed = parsed.strip("\"'")
        result[key] = parsed
    return result


# ── discovery ───────────────────────────────────────────────────────────


def discover_agents(cwd: Path | None = None) -> dict[str, AgentDef]:
    """Discover all agent markdown files from search paths."""
    agents: dict[str, AgentDef] = {}
    resolved = cwd or Path.cwd()
    candidates: list[Path] = []

    # Project agents
    proj_dir = resolved / ".tau" / "agents"
    if proj_dir.is_dir():
        candidates.extend(sorted(proj_dir.glob("*.md")))

    # Global agents
    global_dir = Path.home() / ".tau" / "agents"
    if global_dir.is_dir():
        candidates.extend(sorted(global_dir.glob("*.md")))

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
            agent = parse_agent_markdown(text, source=str(path))
            agents[agent.name] = agent
        except Exception:
            continue

    return agents


def load_agent(name: str, cwd: Path | None = None) -> AgentDef | None:
    """Load a single agent by name."""
    return discover_agents(cwd).get(name)
