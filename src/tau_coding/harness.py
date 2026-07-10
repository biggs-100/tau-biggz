"""Harness system — define custom agent personalities per project.

A harness is a TOML file that configures an agent's personality, tools,
provider, and memory settings. Users place ``.tau/harness.toml`` in their
project to customize Tau for that project's domain.

Usage::

    # Auto-detect .tau/harness.toml
    tau

    # Explicit harness name
    tau --harness legal

Discovery order (first match wins):
  1. .tau/harnesses/<name>.toml          (project)
  2. .tau/harness.toml                   (project, for name="default")
  3. ~/.tau/harnesses/<name>.toml        (global)
  4. Built-in implicit "coding" harness  (fallback)
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple


# ── data model ──────────────────────────────────────────────────────────


@dataclass
class HarnessPersonality:
    """The agent's persona definition."""

    system_prompt: str = ""
    guidelines: tuple[str, ...] = ()


@dataclass
class HarnessProvider:
    """Provider and model selection for this harness."""

    name: str = ""
    model: str = ""
    thinking: str = ""


@dataclass
class HarnessTools:
    """Tool selection for this harness."""

    builtin: tuple[str, ...] = ("read", "write", "edit", "bash")
    extensions: tuple[str, ...] = ()


@dataclass
class HarnessApproval:
    """Tool approval chain policy."""

    default: str = "allow"
    rules: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxConfig:
    """Sandbox policy for built-in file tools.

    Controls which paths the agent's file tools (read, write, edit) may
    access.  In ``"strict"`` mode only paths under the project working
    directory plus explicitly allowed directories are permitted.
    """

    mode: str = "permissive"
    allowed_paths: tuple[str, ...] = ()
    allow_home_tau: bool = True
    allow_temp: bool = True


class ApprovalAction(NamedTuple):
    """Resolved approval action for a single tool."""

    action: str  # One of "allow", "deny", "ask"


@dataclass
class HarnessSubAgent:
    """A sub-agent type available to the orchestrator."""

    name: str = ""
    instructions: str = ""
    tools: tuple[str, ...] = ()


@dataclass
class HarnessDefinition:
    """Complete definition of one agent harness."""

    name: str = "coding"
    description: str = "Coding agent"
    personality: HarnessPersonality = field(default_factory=HarnessPersonality)
    provider: HarnessProvider = field(default_factory=HarnessProvider)
    tools: HarnessTools = field(default_factory=HarnessTools)
    subagents: tuple[HarnessSubAgent, ...] = ()
    approval: HarnessApproval = field(default_factory=HarnessApproval)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)


# ── the built-in coding harness (implicit, no file needed) ─────────────


def coding_harness() -> HarnessDefinition:
    """Return the default coding-agent harness.

    Checks ``~/.tau/SYSTEM.md`` and ``~/.tau/APPEND_SYSTEM.md`` for
    custom system prompts (same convention as named harnesses).
    """
    system_prompt = (
        "You are Tau, a coding agent. "
        "You help users read, write, edit, and debug code."
    )

    home_system = Path.home() / ".tau" / "SYSTEM.md"
    if home_system.exists():
        system_prompt = home_system.read_text(encoding="utf-8").strip()

    home_append = Path.home() / ".tau" / "APPEND_SYSTEM.md"
    if home_append.exists():
        append_text = home_append.read_text(encoding="utf-8").strip()
        if append_text:
                system_prompt = (system_prompt + "\n\n" + append_text) if system_prompt else append_text

    return HarnessDefinition(
        name="coding",
        description="Coding agent with file/shell tools",
        personality=HarnessPersonality(
            system_prompt=system_prompt,
        ),
    )


# ── search paths ────────────────────────────────────────────────────────


# Global active harness (set at CLI startup, read by session init)
_active_harness: HarnessDefinition | None = None


def set_active_harness(h: HarnessDefinition | None) -> None:
    """Set the active harness for the current session."""
    global _active_harness
    _active_harness = h


def get_active_harness() -> HarnessDefinition:
    """Return the active harness or the built-in coding harness."""
    global _active_harness
    if _active_harness is not None:
        return _active_harness
    return coding_harness()


def _project_harness_dir(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".tau" / "harnesses"


def _project_harness_file(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".tau" / "harness.toml"


def _global_harness_dir() -> Path:
    return Path.home() / ".tau" / "harnesses"


# ── SYSTEM.md / APPEND_SYSTEM.md resolution ────────────────────────────


def _find_system_md(toml_path: Path) -> Path | None:
    """Return SYSTEM.md path alongside the harness TOML, if it exists."""
    candidate = toml_path.with_name("SYSTEM.md")
    return candidate if candidate.exists() else None


def _find_append_system_md(toml_path: Path) -> Path | None:
    """Return APPEND_SYSTEM.md path alongside the harness TOML, if it exists."""
    candidate = toml_path.with_name("APPEND_SYSTEM.md")
    return candidate if candidate.exists() else None


# ── load / parse ────────────────────────────────────────────────────────


def load_harness(name: str | None = None, cwd: Path | None = None) -> HarnessDefinition:
    """Load a harness by name, auto-detecting from cwd if name is None.

    Resolution order:
      1. .tau/harnesses/<name>.toml
      2. .tau/harness.toml (only when name is None or "default")
      3. ~/.tau/harnesses/<name>.toml
      4. Built-in coding harness
    """
    resolved = cwd or Path.cwd()

    # 1. Project harnesses dir
    proj_dir = _project_harness_dir(resolved)
    if name:
        candidate = proj_dir / f"{name}.toml"
        if candidate.exists():
            return _parse_harness_file(candidate)

    # 2. Project default harness file (only for None or "default")
    if name is None or name == "default":
        candidate = _project_harness_file(resolved)
        if candidate.exists():
            return _parse_harness_file(candidate)

    # 3. Global harnesses dir
    if name:
        candidate = _global_harness_dir() / f"{name}.toml"
        if candidate.exists():
            return _parse_harness_file(candidate)

    # 4. Fallback to built-in coding
    return coding_harness()


def list_available_harnesses(cwd: Path | None = None) -> list[dict[str, str]]:
    """List all discoverable harness names and descriptions."""
    resolved = cwd or Path.cwd()
    result: list[dict[str, str]] = [{"name": "coding", "description": "Coding agent (default)"}]

    # Project harnesses dir
    proj_dir = _project_harness_dir(resolved)
    if proj_dir.is_dir():
        for f in sorted(proj_dir.glob("*.toml")):
            try:
                d = _parse_harness_file(f)
                result.append({"name": d.name, "description": d.description})
            except Exception:
                result.append({"name": f.stem, "description": "(invalid)"})

    # Project default harness file
    proj_file = _project_harness_file(resolved)
    if proj_file.exists() and proj_file.stem != "harness":
        try:
            d = _parse_harness_file(proj_file)
            result.append({"name": d.name, "description": d.description})
        except Exception:
            pass

    # Global harnesses dir
    global_dir = _global_harness_dir()
    if global_dir.is_dir():
        for f in sorted(global_dir.glob("*.toml")):
            try:
                d = _parse_harness_file(f)
                result.append({"name": d.name, "description": d.description})
            except Exception:
                result.append({"name": f.stem, "description": "(invalid)"})

    return result


# ── parser ──────────────────────────────────────────────────────────────


def _parse_harness_file(path: Path) -> HarnessDefinition:
    """Parse a TOML harness file into a HarnessDefinition."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    name = raw.get("name", path.stem)
    description = raw.get("description", "")

    personality_raw = raw.get("personality", {})
    personality = HarnessPersonality(
        system_prompt=personality_raw.get("system_prompt", ""),
        guidelines=tuple(personality_raw.get("guidelines", [])),
    )

    provider_raw = raw.get("provider", {})
    provider = HarnessProvider(
        name=provider_raw.get("name", ""),
        model=provider_raw.get("model", ""),
        thinking=provider_raw.get("thinking", ""),
    )

    tools_raw = raw.get("tools", {})
    tools = HarnessTools(
        builtin=tuple(tools_raw.get("builtin", ["read", "write", "edit", "bash"])),
        extensions=tuple(tools_raw.get("extensions", [])),
    )

    approval_raw = raw.get("approval", {})
    approval = HarnessApproval(
        default=approval_raw.get("default", "allow"),
        rules=dict(approval_raw.get("rules", {})),
    )

    # Prefer SYSTEM.md over [personality].system_prompt
    system_md = _find_system_md(path)
    if system_md is not None:
        personality.system_prompt = system_md.read_text(encoding="utf-8").strip()

    # Append APPEND_SYSTEM.md if it exists
    append_md = _find_append_system_md(path)
    if append_md is not None:
        append_text = append_md.read_text(encoding="utf-8").strip()
        if append_text:
            if personality.system_prompt:
                personality.system_prompt += "\n\n" + append_text
            else:
                personality.system_prompt = append_text

    sandbox_raw = raw.get("sandbox", {})
    sandbox = SandboxConfig(
        mode=sandbox_raw.get("mode", "permissive"),
        allowed_paths=tuple(sandbox_raw.get("allowed_paths", [])),
        allow_home_tau=sandbox_raw.get("allow_home_tau", True),
        allow_temp=sandbox_raw.get("allow_temp", True),
    )

    return HarnessDefinition(
        name=name,
        description=description,
        personality=personality,
        provider=provider,
        tools=tools,
        approval=approval,
        sandbox=sandbox,
    )
