"""Tests for session_compaction helpers."""

from tau_agent import ErrorEvent
from tau_agent.messages import AssistantMessage, ToolResultMessage, UserMessage
from tau_coding.session_compaction import (
    _first_recent_context_index,
    _is_context_overflow_error,
)

# ---- _first_recent_context_index -------------------------------------------


def test_first_recent_index_returns_len_when_keep_recent_non_positive() -> None:
    """keep_recent_tokens <= 0 should return len(rows)."""
    rows = (("e1", UserMessage(content="hi")),)
    assert _first_recent_context_index(rows, keep_recent_tokens=0) == 1
    assert _first_recent_context_index(rows, keep_recent_tokens=-1) == 1


def test_first_recent_index_returns_candidate_when_user_at_index_gt_zero() -> None:
    """Candidate is a user message at index > 0 → return that index."""
    rows = (
        ("e1", AssistantMessage(content="x")),
        ("e2", UserMessage(content="hello")),
        ("e3", AssistantMessage(content="y")),
    )
    # Scanning from end: index 2 (assistant "y") ≈ 5 tokens < 1 continues…
    # No — keep_recent_tokens=1 means the very first scanned row (index 2)
    # already accumulates >= 1, so candidate = 2. But we need the user
    # candidate.  Use keep_recent_tokens=6 so index 2 (5) < 6, then
    # index 1 (user "hello" ≈ 6) accumulates to 11 >= 6 → candidate = 1.
    assert _first_recent_context_index(rows, keep_recent_tokens=6) == 1


def test_first_recent_index_user_at_index_zero_searches_next_user() -> None:
    """Candidate is user at index 0 → search for next user from index 1."""
    rows = (
        ("e1", UserMessage(content="hello")),
        ("e2", AssistantMessage(content="x")),
        ("e3", UserMessage(content="world")),
    )
    # keep_recent_tokens=15: index 2 (6) < 15, index 1 (5) cum=11 < 15,
    # index 0 (6) cum=17 >= 15 → candidate=0 (user, index==0).
    # _next_user_message_index(rows, start=1) → index 2 (user).
    assert _first_recent_context_index(rows, keep_recent_tokens=15) == 2


def test_first_recent_index_user_at_index_zero_no_next_user() -> None:
    """Candidate is user at index 0 and no other user exists → return 0."""
    rows = (
        ("e1", UserMessage(content="hello")),
        ("e2", AssistantMessage(content="x")),
        ("e3", AssistantMessage(content="y")),
    )
    # keep_recent_tokens=15: candidate=0, user at index 0, no next user.
    assert _first_recent_context_index(rows, keep_recent_tokens=15) == 0


def test_first_recent_index_searches_next_user_when_candidate_not_user() -> None:
    """Candidate is non-user → search for next user message."""
    rows = (
        ("e1", AssistantMessage(content="a")),
        ("e2", AssistantMessage(content="b")),
        ("e3", AssistantMessage(content="c")),
        ("e4", UserMessage(content="d")),
    )
    # keep_recent_tokens=11: index 3 (5) < 11, index 2 (5) cum=10 < 11,
    # index 1 (5) cum=15 >= 11 → candidate=1 (assistant).
    # _next_user_message_index(rows, start=2) → index 3 (user).
    assert _first_recent_context_index(rows, keep_recent_tokens=11) == 3


def test_first_recent_index_falls_through_to_non_tool_scan() -> None:
    """Candidate non-user, no next user → scan for first non-tool entry."""
    rows = (
        ("e1", AssistantMessage(content="a")),
        ("e2", AssistantMessage(content="b")),
        ("e3", ToolResultMessage(tool_call_id="t1", name="read", content="d")),
        ("e4", ToolResultMessage(tool_call_id="t2", name="write", content="e")),
    )
    # keep_recent_tokens=12: index 3 (7) < 12, index 2 (6) cum=13 >= 12 → candidate=2.
    # Candidate is tool, not user. _next_user_message_index returns None.
    # Fallback scan: index 2 (tool) skip, index 3 (tool) skip → return len(4).
    assert _first_recent_context_index(rows, keep_recent_tokens=12) == 4


def test_first_recent_index_returns_non_tool_in_fallback() -> None:
    """Fallback scan finds a non-tool entry and returns its index."""
    rows = (
        ("e1", AssistantMessage(content="a")),
        ("e2", AssistantMessage(content="b")),
        ("e3", AssistantMessage(content="c")),
        ("e4", ToolResultMessage(tool_call_id="t1", name="read", content="d")),
    )
    # keep_recent_tokens=11: index 3 (6) < 11, index 2 (5) cum=11 >= 11 → candidate=2.
    # Candidate is assistant, not user. No next user.
    # Fallback scan: index 2 (assistant, not tool) → return 2.
    assert _first_recent_context_index(rows, keep_recent_tokens=11) == 2


def test_first_recent_index_fallback_to_len_when_all_tool() -> None:
    """Fallback scan yields only tool entries → return len(rows)."""
    rows = (
        ("e1", AssistantMessage(content="a")),
        ("e2", ToolResultMessage(tool_call_id="t1", name="read", content="d")),
        ("e3", ToolResultMessage(tool_call_id="t2", name="read", content="e")),
    )
    # keep_recent_tokens=6: index 2 (tool, ~6) >= 6 → candidate=2.
    # Candidate not user, no next user, fallback scan both tool → return 3.
    assert _first_recent_context_index(rows, keep_recent_tokens=6) == 3


def test_first_recent_index_returns_zero_when_never_reaches_threshold() -> None:
    """No row accumulates enough tokens → candidate_index stays None → return 0."""
    rows = (
        ("e1", AssistantMessage(content="a")),
        ("e2", UserMessage(content="hi")),
    )
    # Each message ≈ 5-6 tokens, keep_recent_tokens=50 >> total → candidate is None → return 0.
    assert _first_recent_context_index(rows, keep_recent_tokens=50) == 0


# ---- _is_context_overflow_error --------------------------------------------


def test_is_context_overflow_returns_true_for_each_marker() -> None:
    """Every marker string should trigger a True match."""
    markers = [
        ("context length",),
        ("context window",),
        ("context limit",),
        ("maximum context",),
        ("max context",),
        ("input is too long",),
        ("input length",),
        ("prompt is too long",),
        ("too many tokens",),
        ("token limit",),
        ("exceeds the limit",),
        ("exceeded the limit",),
    ]
    for (marker,) in markers:
        event = ErrorEvent(message=marker)
        assert _is_context_overflow_error(event), f"Expected True for: {marker}"


def test_is_context_overflow_includes_data_field() -> None:
    """Markers matched in event.data should also return True."""
    event = ErrorEvent(message="", data={"detail": "too many tokens"})
    assert _is_context_overflow_error(event)


def test_is_context_overflow_returns_false_for_unrelated_error() -> None:
    """Non-overflow error messages should return False."""
    event = ErrorEvent(message="connection refused")
    assert not _is_context_overflow_error(event)


def test_is_context_overflow_case_insensitive() -> None:
    """Matching should be case-insensitive."""
    event = ErrorEvent(message="CONTEXT WINDOW limit")
    assert _is_context_overflow_error(event)
