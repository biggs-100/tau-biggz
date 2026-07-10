"""Tests for the tool approval chain in the harness system."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_coding.harness import ApprovalAction, HarnessApproval
from tau_coding.tools import _check_tool_approval
from tau_coding.trust_store import TrustStore


@pytest.fixture
def isolated_trust(tmp_path: Path, monkeypatch) -> None:
    """Point TrustStore to a temp directory so tests don't interfere."""
    monkeypatch.setattr(TrustStore, "_default_data_dir", lambda self: tmp_path)


def test_no_approval_allows() -> None:
    """When no approval config is set, all tools should be allowed."""
    assert _check_tool_approval("bash", None) is None


def test_default_allow_allows() -> None:
    """default=allow should permit any tool without an explicit rule."""
    approval = HarnessApproval(default="allow")
    assert _check_tool_approval("bash", approval) is None
    assert _check_tool_approval("read", approval) is None


def test_default_deny_blocks() -> None:
    """default=deny should block any tool without an explicit allow rule."""
    approval = HarnessApproval(default="deny")
    reason = _check_tool_approval("bash", approval)
    assert reason is not None
    assert "denied" in reason
    assert "bash" in reason


def test_explicit_deny_overrides_default() -> None:
    """An explicit deny rule should block the tool even with default=allow."""
    approval = HarnessApproval(default="allow", rules={"bash": "deny"})
    reason = _check_tool_approval("bash", approval)
    assert reason is not None
    assert "denied" in reason

    # Other tools still allowed
    assert _check_tool_approval("read", approval) is None


def test_explicit_allow_overrides_default() -> None:
    """An explicit allow rule should permit the tool even with default=deny."""
    approval = HarnessApproval(default="deny", rules={"read": "allow"})
    assert _check_tool_approval("read", approval) is None

    # Other tools still denied
    assert _check_tool_approval("write", approval) is not None


def test_ask_untrusted_blocks(isolated_trust) -> None:
    """When policy is 'ask' and tool is not trusted, it should be blocked."""
    approval = HarnessApproval(default="ask")
    denial = _check_tool_approval("bash", approval)
    assert denial is not None
    assert "bash" in denial
    assert "/trust add" in denial


def test_ask_trusted_allows(isolated_trust) -> None:
    """When policy is 'ask' and tool IS trusted, it should be allowed."""
    store = TrustStore()
    store.add("bash")

    approval = HarnessApproval(default="ask")
    result = _check_tool_approval("bash", approval)
    assert result is None


def test_ask_with_args_in_message(isolated_trust) -> None:
    """When policy is 'ask' and untrusted, denial should include args."""
    approval = HarnessApproval(default="ask")
    denial = _check_tool_approval("bash", approval, arguments={"command": "echo hello"})
    assert denial is not None
    assert "Args:" in denial
    assert "command=echo hello" in denial


def test_deny_unaffected_by_trust(isolated_trust) -> None:
    """Explicit deny policy blocks even when tool IS trusted."""
    store = TrustStore()
    store.add("bash")

    approval = HarnessApproval(default="deny", rules={"bash": "deny"})
    denial = _check_tool_approval("bash", approval)
    assert denial is not None
    assert "denied" in denial

    approval = HarnessApproval(default="deny")
    denial = _check_tool_approval("bash", approval)
    assert denial is not None
    assert "denied" in denial


def test_approval_action_construction() -> None:
    """ApprovalAction can be constructed with valid actions."""
    a = ApprovalAction(action="allow")
    assert a.action == "allow"
    assert ApprovalAction(action="deny").action == "deny"
    assert ApprovalAction(action="ask").action == "ask"


def test_approval_action_invalid_no_runtime_error() -> None:
    """Invalid action doesn't raise at construction (Python doesn't enforce at runtime)."""
    a = ApprovalAction(action="maybe")
    assert a.action == "maybe"


def test_deny_message_includes_tool_name() -> None:
    """The denial reason should mention which tool was blocked."""
    approval = HarnessApproval(default="deny")
    reason = _check_tool_approval("write", approval)
    assert reason is not None
    assert "write" in reason
