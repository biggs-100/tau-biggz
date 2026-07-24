"""Provider protocol — re-exports Pi-compatible contract (backward compat)."""

from tau_agent.provider import CancellationToken as CancellationToken
from tau_agent.provider import ModelProvider as ModelProvider
from tau_agent.provider_events import (
    AssistantDoneEvent as AssistantDoneEvent,
    AssistantErrorEvent as AssistantErrorEvent,
    AssistantMessageEvent as AssistantMessageEvent,
    AssistantStartEvent as AssistantStartEvent,
)

from tau_ai._provider_events import (
    ProviderErrorEvent as ProviderErrorEvent,
    ProviderEvent as ProviderEvent,
    ProviderResponseEndEvent as ProviderResponseEndEvent,
    ProviderResponseStartEvent as ProviderResponseStartEvent,
    ProviderRetryEvent as ProviderRetryEvent,
    ProviderTextDeltaEvent as ProviderTextDeltaEvent,
    ProviderThinkingDeltaEvent as ProviderThinkingDeltaEvent,
    ProviderToolCallEvent as ProviderToolCallEvent,
)

__all__ = [
    "CancellationToken", "ModelProvider",
    "AssistantMessageEvent",
    "AssistantStartEvent", "AssistantDoneEvent", "AssistantErrorEvent",
    "ProviderEvent", "ProviderResponseStartEvent",
    "ProviderTextDeltaEvent", "ProviderThinkingDeltaEvent",
    "ProviderToolCallEvent", "ProviderResponseEndEvent",
    "ProviderErrorEvent", "ProviderRetryEvent",
]
