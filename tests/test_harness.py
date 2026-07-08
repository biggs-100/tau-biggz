"""Tests for the harness system."""

from __future__ import annotations

from pathlib import Path

from tau_coding.harness import (
    HarnessDefinition,
    coding_harness,
    list_available_harnesses,
    load_harness,
)


def test_coding_harness_default() -> None:
    """The built-in coding harness should have sensible defaults."""
    h = coding_harness()
    assert h.name == "coding"
    assert h.description == "Coding agent with file/shell tools"
    assert "coding agent" in h.personality.system_prompt.lower()


def test_load_harness_from_project_dir(tmp_path: Path) -> None:
    """Project .tau/harnesses/<name>.toml should be discovered."""
    harness_dir = tmp_path / ".tau" / "harnesses"
    harness_dir.mkdir(parents=True)
    hfile = harness_dir / "legal.toml"
    hfile.write_text("""
name = "legal"
description = "Abogado corporativo"

[personality]
system_prompt = "You are a lawyer."

[provider]
name = "opencode-zen"
model = "gpt-5.5"

[tools]
builtin = ["read", "write"]
""")

    h = load_harness("legal", cwd=tmp_path)
    assert h.name == "legal"
    assert h.description == "Abogado corporativo"
    assert "lawyer" in h.personality.system_prompt
    assert h.provider.name == "opencode-zen"


def test_load_harness_from_project_file(tmp_path: Path) -> None:
    """Project .tau/harness.toml should be discovered when name is None."""
    tau_dir = tmp_path / ".tau"
    tau_dir.mkdir(parents=True)
    hfile = tau_dir / "harness.toml"
    hfile.write_text("""
name = "mio"
description = "Mi harness"

[personality]
system_prompt = "You are an assistant."
""")

    h = load_harness(cwd=tmp_path)
    assert h.name == "mio"
    assert h.description == "Mi harness"


def test_load_harness_fallback_to_coding(tmp_path: Path) -> None:
    """When no harness file exists, should return the built-in coding harness."""
    h = load_harness(cwd=tmp_path)
    assert h.name == "coding"


def test_list_harnesses_empty_project(tmp_path: Path) -> None:
    """An empty project should only list 'coding'."""
    harnesses = list_available_harnesses(cwd=tmp_path)
    names = [h["name"] for h in harnesses]
    assert names == ["coding"]


def test_list_harnesses_with_project_harness(tmp_path: Path) -> None:
    """Project harnesses should appear in the listing."""
    harness_dir = tmp_path / ".tau" / "harnesses"
    harness_dir.mkdir(parents=True)
    (harness_dir / "legal.toml").write_text("""
name = "legal"
description = "Abogado"
[personality]
system_prompt = "test"
""")

    harnesses = list_available_harnesses(cwd=tmp_path)
    names = [h["name"] for h in harnesses]
    assert "legal" in names
