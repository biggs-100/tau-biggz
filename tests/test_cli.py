from pathlib import Path

import pytest
from typer.testing import CliRunner

from tau_agent import AssistantMessage
from tau_ai import (
    FakeProvider,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderTextDeltaEvent,
)
from tau_coding.cli import app, build_default_system_prompt, run_print_mode


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "tau 0.1.0"


def test_cli_without_prompt_prints_print_mode_hint() -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert "Tau print mode is installed" in result.stdout


def test_default_system_prompt_includes_tool_snippets_and_guidelines() -> None:
    prompt = build_default_system_prompt()

    assert "You are Tau" in prompt
    assert "- read: Read file contents" in prompt
    assert "Use read to examine files instead of cat or sed." in prompt


@pytest.mark.anyio
async def test_run_print_mode_streams_assistant_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    provider = FakeProvider(
        [
            [
                ProviderResponseStartEvent(model="fake"),
                ProviderTextDeltaEvent(delta="Hel"),
                ProviderTextDeltaEvent(delta="lo"),
                ProviderResponseEndEvent(message=AssistantMessage(content="Hello")),
            ]
        ]
    )

    await run_print_mode(prompt="Say hello", model="fake", cwd=tmp_path, provider=provider)

    captured = capsys.readouterr()
    assert captured.out == "Hello\n"
    assert captured.err == ""
    assert provider.calls[0][0] == "fake"
    assert provider.calls[0][1] == build_default_system_prompt()
    assert [tool.name for tool in provider.calls[0][3]] == ["read", "write", "edit", "bash"]
