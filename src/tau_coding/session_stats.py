"""Session statistics — turn counts, token estimates, cost estimates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from tau_agent.messages import AssistantMessage, UserMessage


@dataclass
class SessionStats:
    """Derivable and estimated session statistics."""

    turn_count: int = 0
    tool_call_count: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float | None = None


CostResolver = Callable[[int], dict[str, float] | None]


def estimate_text_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(0, len(text) // 4)


def calculate_session_stats(
    messages: list,
    *,
    context_token_estimate: int = 0,
    model_cost_resolver: CostResolver | None = None,
) -> SessionStats:
    """Calculate session stats from a list of messages.

    Args:
        messages: List of AgentMessage objects from the session.
        context_token_estimate: Estimated input context tokens
            (from system prompt, tools, etc.).
        model_cost_resolver: Optional callable ``(total_input_tokens)``
            returning a cost dict with ``"input"`` and ``"output"`` keys
            (dollars per million tokens), or ``None`` when cost data is
            unavailable.

    Returns:
        A ``SessionStats`` dataclass with derived and estimated values.
    """
    turns = 0
    tool_calls = 0
    output_text = ""

    for msg in messages:
        if isinstance(msg, UserMessage):
            turns += 1
        elif isinstance(msg, AssistantMessage):
            output_text += msg.content
            tool_calls += len(msg.tool_calls)

    estimated_output = estimate_text_tokens(output_text)
    estimated_cost: float | None = None

    if model_cost_resolver is not None:
        costs = model_cost_resolver(context_token_estimate + estimated_output)
        if costs is not None:
            input_cost_per_m = costs.get("input", 0.0)
            output_cost_per_m = costs.get("output", 0.0)
            estimated_cost = (
                input_cost_per_m * context_token_estimate / 1_000_000
                + output_cost_per_m * estimated_output / 1_000_000
            )

    return SessionStats(
        turn_count=turns,
        tool_call_count=tool_calls,
        estimated_input_tokens=context_token_estimate,
        estimated_output_tokens=estimated_output,
        estimated_cost=estimated_cost,
    )
