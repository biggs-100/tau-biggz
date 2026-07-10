"""Tests for tau_coding.agents — agent-as-markdown discovery and parsing."""

from __future__ import annotations

from pathlib import Path

from tau_coding.agents import (
    _parse_yaml_like,
    discover_agents,
    load_agent,
    parse_agent_markdown,
)

# ── parse_agent_markdown ───────────────────────────────────────────────


def test_parse_full_frontmatter() -> None:
    text = """---
name: planner
description: Senior architect
tools: [read, web_search]
---

You are a senior architect. Break down complex tasks.
"""
    agent = parse_agent_markdown(text, source="/fake/planner.md")
    assert agent.name == "planner"
    assert agent.description == "Senior architect"
    assert agent.tools == ("read", "web_search")
    assert agent.system_prompt == "You are a senior architect. Break down complex tasks."
    assert agent.source_path == "/fake/planner.md"


def test_parse_no_frontmatter() -> None:
    text = "Just a plain prompt with no frontmatter."
    agent = parse_agent_markdown(text, source="/fake/plain.md")
    assert agent.name == "plain"
    assert agent.system_prompt == "Just a plain prompt with no frontmatter."
    assert agent.description == ""
    assert agent.tools == ()


def test_parse_no_frontmatter_no_source() -> None:
    text = "Plain prompt without a source path."
    agent = parse_agent_markdown(text)
    assert agent.name == "unnamed"
    assert agent.system_prompt == "Plain prompt without a source path."


def test_parse_minimal_frontmatter() -> None:
    text = """---
name: coder
---

You write code.
"""
    agent = parse_agent_markdown(text, source="coder.md")
    assert agent.name == "coder"
    assert agent.description == ""
    assert agent.tools == ()
    assert agent.system_prompt == "You write code."


def test_parse_empty_frontmatter() -> None:
    text = """---

---

Body only.
"""
    agent = parse_agent_markdown(text, source="empty.md")
    # name comes from the file stem since meta is empty
    assert agent.name == "empty"
    assert agent.system_prompt == "Body only."


def test_parse_missing_frontmatter_separator() -> None:
    """Text that starts with --- but has no closing --- should be treated as no match."""
    text = "--- not really frontmatter\nbody"
    agent = parse_agent_markdown(text)
    assert agent.name == "unnamed"
    assert agent.system_prompt == text.strip()


# ── _parse_yaml_like ────────────────────────────────────────────────────


def test_parse_yaml_like_basic() -> None:
    result = _parse_yaml_like("name: planner\ndescription: Senior architect")
    assert result["name"] == "planner"
    assert result["description"] == "Senior architect"


def test_parse_yaml_like_with_list() -> None:
    result = _parse_yaml_like("tools: [read, web_search, write]")
    assert result["tools"] == ["read", "web_search", "write"]


def test_parse_yaml_like_with_quoted_values() -> None:
    result = _parse_yaml_like('name: "my-agent"\n')
    assert result["name"] == "my-agent"


def test_parse_yaml_like_skips_invalid_lines() -> None:
    result = _parse_yaml_like("name: coder\n\nno-colon-line\nkey: value")
    assert result["name"] == "coder"
    assert result["key"] == "value"
    assert "no-colon-line" not in result


def test_parse_yaml_like_empty_string() -> None:
    result = _parse_yaml_like("")
    assert result == {}


def test_parse_yaml_like_empty_list() -> None:
    result = _parse_yaml_like("tools: []")
    assert result["tools"] == []


# ── discover_agents ────────────────────────────────────────────────────


def test_discover_agents_from_project_dir(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".tau" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "planner.md").write_text(
        "---\nname: planner\ndescription: Plans things\ntools: [read]\n---\n\nYou plan."
    )
    (agents_dir / "coder.md").write_text(
        "---\nname: coder\ndescription: Codes things\n---\n\nYou code."
    )

    agents = discover_agents(cwd=tmp_path)
    assert "planner" in agents
    assert "coder" in agents
    assert agents["planner"].description == "Plans things"
    assert agents["coder"].description == "Codes things"


def test_discover_agents_no_dir(tmp_path: Path) -> None:
    agents = discover_agents(cwd=tmp_path)
    assert agents == {}


def test_discover_agents_skips_invalid_files(tmp_path: Path) -> None:
    """A directory entry that is not a regular file is silently skipped."""
    agents_dir = tmp_path / ".tau" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "good.md").write_text("---\nname: good\n---\n\nHello.")
    # A subdirectory (not a file) can't be read as text and is skipped
    (agents_dir / "bad.md").mkdir()

    agents = discover_agents(cwd=tmp_path)
    assert "good" in agents
    # bad subdirectory is silently skipped
    assert len(agents) == 1


def test_discover_agents_sorted_order(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".tau" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "zebra.md").write_text("---\nname: zebra\n---\n\nZ.")
    (agents_dir / "alpha.md").write_text("---\nname: alpha\n---\n\nA.")

    agents = discover_agents(cwd=tmp_path)
    # Both are found regardless of order
    assert "alpha" in agents
    assert "zebra" in agents


# ── load_agent ─────────────────────────────────────────────────────────


def test_load_agent_found(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".tau" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "debugger.md").write_text(
        "---\nname: debugger\ndescription: Finds bugs\n---\n\nDebug things."
    )

    agent = load_agent("debugger", cwd=tmp_path)
    assert agent is not None
    assert agent.name == "debugger"
    assert agent.description == "Finds bugs"


def test_load_agent_not_found(tmp_path: Path) -> None:
    agent = load_agent("nonexistent", cwd=tmp_path)
    assert agent is None


def test_load_agent_empty_dir(tmp_path: Path) -> None:
    (tmp_path / ".tau" / "agents").mkdir(parents=True)
    agent = load_agent("anything", cwd=tmp_path)
    assert agent is None
