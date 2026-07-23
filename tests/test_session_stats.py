"""Tests for session statistics derivation."""

from __future__ import annotations

from tau_agent.messages import AssistantMessage, ToolResultMessage, UserMessage
from tau_agent.tools import ToolCall
from tau_coding.session_stats import (
    SessionStats,
    calculate_session_stats,
    estimate_text_tokens,
)


def test_estimate_text_tokens_empty() -> None:
    assert estimate_text_tokens("") == 0


def test_estimate_text_tokens_short() -> None:
    assert estimate_text_tokens("hello") == 1  # 5 // 4


def test_estimate_text_tokens_exact() -> None:
    assert estimate_text_tokens("abcd") == 1  # 4 // 4


def test_estimate_text_tokens_long() -> None:
    assert estimate_text_tokens("a" * 100) == 25  # 100 // 4


def test_calculate_stats_empty_messages() -> None:
    stats = calculate_session_stats([])
    assert stats == SessionStats()


def test_calculate_stats_turn_count() -> None:
    messages = [
        UserMessage(content="hello"),
        AssistantMessage(content="hi there"),
        UserMessage(content="again"),
        AssistantMessage(content="ok"),
    ]
    stats = calculate_session_stats(messages)
    assert stats.turn_count == 2
    assert stats.tool_call_count == 0
    assert stats.estimated_output_tokens == estimate_text_tokens("hi thereok")


def test_calculate_stats_turn_count_mixed() -> None:
    """ToolResultMessage should not affect turn count or output estimate."""
    messages = [
        UserMessage(content="run"),
        AssistantMessage(
            content="ok",
            tool_calls=[ToolCall(id="1", name="bash", arguments={}),
            ],
        ),
        ToolResultMessage(tool_call_id="1", name="bash", content="done", ok=True),
        AssistantMessage(content="finished"),
    ]
    stats = calculate_session_stats(messages)
    assert stats.turn_count == 1
    assert stats.tool_call_count == 1
    # Combined output text: "ok" + "finished" = 10 chars -> 2 tokens
    assert stats.estimated_output_tokens == estimate_text_tokens("okfinished")


def test_calculate_stats_tool_calls() -> None:
    messages = [
        UserMessage(content="do something"),
        AssistantMessage(
            content="sure",
            tool_calls=[
                ToolCall(id="1", name="bash", arguments={}),
                ToolCall(id="2", name="read", arguments={}),
            ],
        ),
    ]
    stats = calculate_session_stats(messages)
    assert stats.turn_count == 1
    assert stats.tool_call_count == 2





def test_calculate_stats_context_token_estimate() -> None:
    stats = calculate_session_stats(
        [UserMessage(content="hi")],
        context_token_estimate=5000,
    )
    assert stats.estimated_input_tokens == 5000


def test_calculate_stats_cost_resolver_returns_none() -> None:
    stats = calculate_session_stats(
        [UserMessage(content="hi")],
        model_cost_resolver=lambda total: None,
    )
    assert stats.estimated_cost is None


def test_calculate_stats_cost_resolver_returns_values() -> None:
    stats = calculate_session_stats(
        [UserMessage(content="hi"), AssistantMessage(content="hello world")],
        context_token_estimate=1000,
        model_cost_resolver=lambda total: {"input": 3.0, "output": 15.0},
    )
    assert stats.estimated_input_tokens == 1000
    # estimated_output = len("hello world") // 4 = 11 // 4 = 2
    assert stats.estimated_output_tokens == 2
    # cost = 3.0 * 1000 / 1_000_000 + 15.0 * 2 / 1_000_000 = 0.003 + 0.00003
    assert stats.estimated_cost is not None
    assert abs(stats.estimated_cost - 0.00303) < 1e-10


def test_calculate_stats_cost_resolver_zero_tokens() -> None:
    stats = calculate_session_stats(
        [],
        context_token_estimate=0,
        model_cost_resolver=lambda total: {"input": 3.0, "output": 15.0},
    )
    assert stats.estimated_cost == 0.0


def test_calculate_stats_cost_resolver_missing_keys() -> None:
    stats = calculate_session_stats(
        [UserMessage(content="hi"), AssistantMessage(content="hello")],
        context_token_estimate=1000,
        model_cost_resolver=lambda total: {"input": 3.0},
    )
    assert stats.estimated_cost is not None
    # output cost should default to 0.0
    # cost = 3.0 * 1000 / 1_000_000 + 0.0 * 2 / 1_000_000 = 0.003
    assert abs(stats.estimated_cost - 0.003) < 1e-10
