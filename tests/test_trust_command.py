"""Tests for the /trust slash command."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_coding.commands import CommandContext, CommandRegistry, CommandResult, SlashCommand
from tau_coding.trust_store import TrustStore


@pytest.fixture
def isolated_trust(tmp_path: Path, monkeypatch) -> None:
    """Point TrustStore to a temp directory so tests don't interfere."""
    monkeypatch.setattr(TrustStore, "_default_data_dir", lambda self: tmp_path)


def _make_trust_command() -> SlashCommand:
    """Return the /trust SlashCommand without needing a full registry."""
    from tau_coding.commands import _trust_command

    return SlashCommand(
        name="trust",
        description="Manage trusted tools for approval policy.",
        usage="/trust add|remove|list|help",
        handler=_trust_command,
    )


def _execute(cmd: SlashCommand, args: str) -> CommandResult:
    """Execute a slash command with the given args."""
    # Create a minimal fake context
    from dataclasses import dataclass

    @dataclass
    class FakeSession:
        ...

    registry = CommandRegistry()
    context = CommandContext(
        session=FakeSession(),  # type: ignore
        registry=registry,
        text=f"/trust {args}".strip(),
        name="trust",
        args=args,
    )
    return cmd.handler(context)


class TestTrustCommand:
    """Tests for the /trust command handler."""

    def test_trust_add(self, isolated_trust) -> None:
        """/trust add <tool> should trust the tool."""
        cmd = _make_trust_command()
        result = _execute(cmd, "add bash")
        assert result.handled is True
        assert result.message == "Tool 'bash' is now trusted."

        # Verify persistence
        store = TrustStore.load()
        assert store.is_trusted("bash") is True

    def test_trust_add_duplicate(self, isolated_trust) -> None:
        """/trust add on already-trusted tool should say 'already trusted'."""
        store = TrustStore()
        store.add("bash")

        cmd = _make_trust_command()
        result = _execute(cmd, "add bash")
        assert result.handled is True
        assert "already trusted" in result.message

    def test_trust_remove(self, isolated_trust) -> None:
        """/trust remove <tool> should remove trust."""
        store = TrustStore()
        store.add("bash")

        cmd = _make_trust_command()
        result = _execute(cmd, "remove bash")
        assert result.handled is True
        assert "no longer trusted" in result.message

        # Verify persistence
        store = TrustStore.load()
        assert store.is_trusted("bash") is False

    def test_trust_remove_nonexistent(self, isolated_trust) -> None:
        """/trust remove on untrusted tool should say 'not trusted'."""
        cmd = _make_trust_command()
        result = _execute(cmd, "remove nonexistent")
        assert result.handled is True
        assert "not trusted" in result.message

    def test_trust_list(self, isolated_trust) -> None:
        """/trust list should show trusted tools."""
        store = TrustStore()
        store.add("bash")
        store.add("read")

        cmd = _make_trust_command()
        result = _execute(cmd, "list")
        assert result.handled is True
        assert "Trusted tools:" in result.message
        assert "- bash" in result.message
        assert "- read" in result.message

    def test_trust_list_empty(self, isolated_trust) -> None:
        """/trust list on empty store should say 'No trusted tools'."""
        cmd = _make_trust_command()
        result = _execute(cmd, "list")
        assert result.handled is True
        assert result.message == "No trusted tools."

    def test_trust_help(self, isolated_trust) -> None:
        """/trust help should show usage."""
        cmd = _make_trust_command()
        result = _execute(cmd, "help")
        assert result.handled is True
        assert "Usage" in result.message
        assert "/trust add" in result.message

    def test_trust_no_args(self, isolated_trust) -> None:
        """/trust with no args should show usage (same as help)."""
        cmd = _make_trust_command()
        result = _execute(cmd, "")
        assert result.handled is True
        assert "Usage" in result.message
        assert "/trust add" in result.message

    def test_trust_add_no_name(self, isolated_trust) -> None:
        """/trust add with no tool name should show usage."""
        cmd = _make_trust_command()
        result = _execute(cmd, "add")
        assert result.handled is True
        assert "Usage: /trust add" in result.message

    def test_trust_remove_no_name(self, isolated_trust) -> None:
        """/trust remove with no tool name should show usage."""
        cmd = _make_trust_command()
        result = _execute(cmd, "remove")
        assert result.handled is True
        assert "Usage: /trust remove" in result.message
