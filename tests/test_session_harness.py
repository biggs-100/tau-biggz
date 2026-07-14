"""Tests for session_harness helper functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_agent.tools import AgentTool
from tau_coding.harness import HarnessDefinition, HarnessPersonality, HarnessTools
from tau_coding.session_harness import _harness_filtered_tools, _harness_system_prompt
from tau_coding.session_models import CodingSessionConfig, SessionResources
from tau_coding.system_prompt import BuildSystemPromptOptions


def _stub_tool(name: str) -> AgentTool:
    """Create a minimal AgentTool for testing."""
    return AgentTool(
        name=name,
        description=f"Tool {name}",
        input_schema={"type": "object", "properties": {}},
        executor=lambda arguments, signal=None: None,  # type: ignore[arg-type]  # never called
    )


FAKE_TOOLS = [_stub_tool(n) for n in ("read", "write", "edit", "bash")]


class FakeRegistry:
    """Stub extension registry with no tools."""

    def get_tools(self) -> list:
        return []


def _config(cwd: Path, **overrides: object) -> CodingSessionConfig:
    return CodingSessionConfig(
        provider=None,  # type: ignore[arg-type]
        model="fake",
        storage=None,  # type: ignore[arg-type]
        cwd=cwd,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture
def resources() -> SessionResources:
    return SessionResources(
        skills=(),
        prompt_templates=(),
        context_files=(),
        diagnostics=(),
    )


# ── _harness_filtered_tools ────────────────────────────────────────────────


class TestFilteredTools:
    """_harness_filtered_tools scenarios."""

    def test_coding_harness_returns_all(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Coding harness returns all tools unfiltered."""
        harness = HarnessDefinition(name="coding")
        monkeypatch.setattr("tau_coding.harness.get_active_harness", lambda: harness)
        monkeypatch.setattr("tau_coding.tools.create_coding_tools", lambda **kw: FAKE_TOOLS)
        monkeypatch.setattr("tau_coding.extensions.get_default_registry", lambda: FakeRegistry())

        result = _harness_filtered_tools(_config(tmp_path))

        assert result is FAKE_TOOLS
        assert [t.name for t in result] == ["read", "write", "edit", "bash"]

    def test_non_coding_harness_filters(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Non-coding harness with specific allowed tools filters the list."""
        harness = HarnessDefinition(
            name="legal",
            tools=HarnessTools(builtin=("read", "write")),
        )
        monkeypatch.setattr("tau_coding.harness.get_active_harness", lambda: harness)
        monkeypatch.setattr("tau_coding.tools.create_coding_tools", lambda **kw: FAKE_TOOLS)
        monkeypatch.setattr("tau_coding.extensions.get_default_registry", lambda: FakeRegistry())

        result = _harness_filtered_tools(_config(tmp_path))

        assert [t.name for t in result] == ["read", "write"]
        assert len(result) == 2

    def test_non_coding_empty_allowed_returns_all(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Non-coding harness with empty builtin set returns all tools."""
        harness = HarnessDefinition(
            name="restricted",
            tools=HarnessTools(builtin=()),
        )
        monkeypatch.setattr("tau_coding.harness.get_active_harness", lambda: harness)
        monkeypatch.setattr("tau_coding.tools.create_coding_tools", lambda **kw: FAKE_TOOLS)
        monkeypatch.setattr("tau_coding.extensions.get_default_registry", lambda: FakeRegistry())

        result = _harness_filtered_tools(_config(tmp_path))

        assert result is FAKE_TOOLS
        assert [t.name for t in result] == ["read", "write", "edit", "bash"]


# ── _harness_system_prompt ──────────────────────────────────────────────────


class TestSystemPrompt:
    """_harness_system_prompt scenarios."""

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        harness: HarnessDefinition,
    ) -> list[BuildSystemPromptOptions]:
        """Install common monkeypatches and return capture list."""
        monkeypatch.setattr("tau_coding.harness.get_active_harness", lambda: harness)

        captured: list[BuildSystemPromptOptions] = []

        def fake_build(options: BuildSystemPromptOptions) -> str:
            captured.append(options)
            return "built prompt"

        monkeypatch.setattr("tau_coding.system_prompt.build_system_prompt", fake_build)
        return captured

    def test_coding_harness_no_personality_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        resources: SessionResources,
    ) -> None:
        """Coding harness keeps config.custom_system_prompt unchanged."""
        harness = HarnessDefinition(name="coding")
        captured = self._patch(monkeypatch, harness)

        config = _config(tmp_path, custom_system_prompt="my custom prompt")
        result = _harness_system_prompt(config, FAKE_TOOLS, resources)

        assert result == "built prompt"
        assert len(captured) == 1
        assert captured[0].custom_prompt == "my custom prompt"

    def test_non_coding_with_personality_overrides(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        resources: SessionResources,
    ) -> None:
        """Non-coding harness with personality overrides custom_prompt."""
        harness = HarnessDefinition(
            name="legal",
            personality=HarnessPersonality(system_prompt="You are a lawyer."),
        )
        captured = self._patch(monkeypatch, harness)

        config = _config(tmp_path, custom_system_prompt="original custom")
        result = _harness_system_prompt(config, FAKE_TOOLS, resources)

        assert result == "built prompt"
        assert len(captured) == 1
        assert captured[0].custom_prompt == "You are a lawyer."

    def test_non_coding_no_personality_leaves_custom(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        resources: SessionResources,
    ) -> None:
        """Non-coding harness with empty system_prompt keeps original custom_prompt."""
        harness = HarnessDefinition(
            name="legal",
            personality=HarnessPersonality(system_prompt=""),
        )
        captured = self._patch(monkeypatch, harness)

        config = _config(tmp_path, custom_system_prompt="original custom")
        result = _harness_system_prompt(config, FAKE_TOOLS, resources)

        assert result == "built prompt"
        assert len(captured) == 1
        assert captured[0].custom_prompt == "original custom"
