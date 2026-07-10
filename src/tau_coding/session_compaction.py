"""Compaction-plan helpers for coding sessions."""

from __future__ import annotations

from tau_agent import ErrorEvent
from tau_agent.messages import AgentMessage

from tau_coding.context_window import estimate_message_tokens


def _first_recent_context_index(
    rows: tuple[tuple[str, AgentMessage], ...],
    *,
    keep_recent_tokens: int,
) -> int:
    if keep_recent_tokens <= 0:
        return len(rows)

    accumulated_tokens = 0
    candidate_index: int | None = None
    for index in range(len(rows) - 1, -1, -1):
        _entry_id, message = rows[index]
        accumulated_tokens += estimate_message_tokens(message)
        if accumulated_tokens >= keep_recent_tokens:
            candidate_index = index
            break

    if candidate_index is None:
        return 0

    candidate_message = rows[candidate_index][1]
    if candidate_message.role == "user":
        if candidate_index > 0:
            return candidate_index
        next_user_index = _next_user_message_index(rows, start=1)
        return next_user_index if next_user_index is not None else 0

    next_user_index = _next_user_message_index(rows, start=candidate_index + 1)
    if next_user_index is not None:
        return next_user_index

    for index in range(candidate_index, len(rows)):
        if rows[index][1].role != "tool":
            return index
    return len(rows)


def _next_user_message_index(
    rows: tuple[tuple[str, AgentMessage], ...],
    *,
    start: int,
) -> int | None:
    for index in range(start, len(rows)):
        if rows[index][1].role == "user":
            return index
    return None


def _is_context_overflow_error(event: ErrorEvent) -> bool:
    text = event.message
    if event.data is not None:
        text = f"{text} {event.data}"
    normalized = text.lower()
    markers = (
        "context length",
        "context window",
        "context limit",
        "maximum context",
        "max context",
        "input is too long",
        "input length",
        "prompt is too long",
        "too many tokens",
        "token limit",
        "exceeds the limit",
        "exceeded the limit",
    )
    return any(marker in normalized for marker in markers)
