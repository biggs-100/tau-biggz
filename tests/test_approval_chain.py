"""Tests for the tool approval chain in the harness system."""

from __future__ import annotations

from tau_coding.harness import HarnessApproval
from tau_coding.tools import _check_tool_approval


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


def test_ask_falls_through_to_allow() -> None:
    """The 'ask' rule should fall through to allow when no handler is available."""
    approval = HarnessApproval(default="ask")
    assert _check_tool_approval("bash", approval) is None

    approval = HarnessApproval(default="deny", rules={"read": "ask"})
    assert _check_tool_approval("read", approval) is None
    assert _check_tool_approval("bash", approval) is not None


def test_deny_message_includes_tool_name() -> None:
    """The denial reason should mention which tool was blocked."""
    approval = HarnessApproval(default="deny")
    reason = _check_tool_approval("write", approval)
    assert reason is not None
    assert "write" in reason
