"""Tests for Google Gemini provider.

Covers model/field defaults, schema sanitization, thinking-level payload
generation, SSE streaming (thinking deltas, text deltas, tool calls,
thought-signature round-trip, finish reasons), and error/retry scenarios.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from json import loads
from typing import Any

import httpx
import pytest

from tau_agent import (
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    SimpleCancellationToken,
    ToolCall,
    UserMessage,
)
from tau_agent.types import JSONValue
from tau_ai import (
    GoogleGenerativeAIProvider,
    OpenAICompatibleConfig,
    ProviderErrorEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderRetryEvent,
    ProviderTextDeltaEvent,
    ProviderThinkingDeltaEvent,
    ProviderToolCallEvent,
)
from tau_ai.google import _sanitize_google_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


def _make_provider(
    *,
    reasoning_effort: str | None = None,
    max_retries: int = 0,
    max_retry_delay_seconds: float = 0,
    client: httpx.AsyncClient | None = None,
) -> GoogleGenerativeAIProvider:
    return GoogleGenerativeAIProvider(
        OpenAICompatibleConfig(
            api_key="test-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            reasoning_effort=reasoning_effort,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
        ),
        client=client,
    )


_OK_SSE = 'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}\n\n'


def _ok_handler(requests: list[httpx.Request] | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(
            200,
            text=_OK_SSE,
            headers={"content-type": "text/event-stream"},
        )

    return handler


# ---------------------------------------------------------------------------
# Group 1 — Model / field tests
# ---------------------------------------------------------------------------

class TestModelFields:
    """ToolCall.thought_signature and AssistantMessage.thinking_text defaults
    and serialization."""

    def test_tool_call_thought_signature_default_none(self) -> None:
        tc = ToolCall(id="t1", name="foo")
        assert tc.thought_signature is None

    def test_tool_call_thought_signature_set(self) -> None:
        tc = ToolCall(id="t1", name="foo", thought_signature="abc")
        assert tc.thought_signature == "abc"

    def test_tool_call_thought_signature_in_model_dump(self) -> None:
        tc = ToolCall(id="t1", name="foo", thought_signature="abc")
        dumped = tc.model_dump()
        assert dumped["thought_signature"] == "abc"

    def test_assistant_message_thinking_text_default_empty(self) -> None:
        msg = AssistantMessage()
        assert msg.thinking_text == ""

    def test_assistant_message_thinking_text_set(self) -> None:
        msg = AssistantMessage(thinking_text="reasoned")
        assert msg.thinking_text == "reasoned"

    def test_assistant_message_thinking_text_in_model_dump(self) -> None:
        msg = AssistantMessage(thinking_text="reasoned")
        dumped = msg.model_dump()
        assert dumped["thinking_text"] == "reasoned"


# ---------------------------------------------------------------------------
# Group 2 — Sanitization tests
# ---------------------------------------------------------------------------

class TestSanitizeGoogleSchema:
    """_sanitize_google_schema() pure-function tests."""

    def test_sanitize_strips_additional_properties(self) -> None:
        schema = {"type": "object", "additionalProperties": False}
        result = _sanitize_google_schema(schema)
        assert "additionalProperties" not in result
        assert result == {"type": "object"}

    def test_sanitize_strips_dollar_schema(self) -> None:
        schema = {"type": "string", "$schema": "http://json-schema.org/draft-07/schema#"}
        result = _sanitize_google_schema(schema)
        assert "$schema" not in result
        assert result == {"type": "string"}

    def test_sanitize_strips_default(self) -> None:
        schema = {"type": "string", "default": "hello"}
        result = _sanitize_google_schema(schema)
        assert "default" not in result
        assert result == {"type": "string"}

    def test_sanitize_strips_title(self) -> None:
        schema = {"type": "object", "title": "MySchema"}
        result = _sanitize_google_schema(schema)
        assert "title" not in result
        assert result == {"type": "object"}

    def test_sanitize_strips_all_banned_keys(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
            "default": {"key": "val"},
            "title": "Full",
        }
        result = _sanitize_google_schema(schema)
        assert "additionalProperties" not in result
        assert "$schema" not in result
        assert "default" not in result
        assert "title" not in result
        assert result == {"type": "object"}

    def test_sanitize_nested_properties(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "inner": {"type": "object", "additionalProperties": False},
            },
        }
        result = _sanitize_google_schema(schema)
        inner = result["properties"]["inner"]  # type: ignore[index]
        assert "additionalProperties" not in inner
        assert isinstance(inner, dict)
        assert inner == {"type": "object"}

    def test_sanitize_items_array(self) -> None:
        schema = {
            "type": "array",
            "items": {"type": "string", "title": "Item", "default": ""},
        }
        result = _sanitize_google_schema(schema)
        items = result["items"]  # type: ignore[index]
        assert "title" not in items
        assert "default" not in items
        assert isinstance(items, dict)
        assert items == {"type": "string"}

    def test_sanitize_clean_schema_unchanged(self) -> None:
        schema = {"type": "string", "description": "A name"}
        result = _sanitize_google_schema(schema)
        assert result == schema

    def test_sanitize_does_not_mutate_original(self) -> None:
        original = {"type": "object", "additionalProperties": False}
        _sanitize_google_schema(original)
        assert "additionalProperties" in original

    def test_sanitize_empty_dict(self) -> None:
        assert _sanitize_google_schema({}) == {}

    def test_sanitize_none_values(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": None,  # type: ignore[typeddict-item]
        }
        result = _sanitize_google_schema(schema)  # type: ignore[arg-type]
        assert result == {"type": "object", "properties": None}

    def test_sanitize_list_values(self) -> None:
        """Banned keys inside list items are also stripped."""
        schema = {
            "type": "object",
            "enum": [
                {"value": "a", "title": "Option A", "default": "a"},
                {"value": "b", "title": "Option B"},
            ],
        }
        result = _sanitize_google_schema(schema)
        for item in result["enum"]:  # type: ignore[union-attr]
            assert "title" not in item
            assert "default" not in item


# ---------------------------------------------------------------------------
# Group 3 — Thinking-level tests
# ---------------------------------------------------------------------------

class TestThinkingLevel:
    """Verify reasoning_effort produces correct thinkingConfig in payload."""

    @pytest.mark.anyio
    async def test_thinking_level_minimal(self) -> None:
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="minimal", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 128,
        }

    @pytest.mark.anyio
    async def test_thinking_level_low(self) -> None:
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="low", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 2048,
        }

    @pytest.mark.anyio
    async def test_thinking_level_medium(self) -> None:
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="medium", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 8192,
        }

    @pytest.mark.anyio
    async def test_thinking_level_high(self) -> None:
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="high", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 24576,
        }

    @pytest.mark.anyio
    async def test_thinking_level_xhigh(self) -> None:
        """xhigh folds to high → same budget as 'high'."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="xhigh", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 24576,
        }

    @pytest.mark.anyio
    async def test_thinking_level_none_omits_config(self) -> None:
        """reasoning_effort=None → no thinkingConfig in payload."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort=None, client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert "thinkingConfig" not in payload.get("generationConfig", {})

    # -- Additional thinking-level coverage paths --

    @pytest.mark.anyio
    async def test_thinking_level_none_gemini3_pro(self) -> None:
        """reasoning_effort='none' with Gemini 3 Pro → thinkingLevel LOW."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="none", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-3-pro-v1",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "thinkingLevel": "LOW",
        }

    @pytest.mark.anyio
    async def test_thinking_level_none_gemini3_flash(self) -> None:
        """reasoning_effort='none' with Gemini 3 Flash → thinkingLevel MINIMAL."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="none", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-3-flash-v1",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "thinkingLevel": "MINIMAL",
        }

    @pytest.mark.anyio
    async def test_thinking_level_none_other_model(self) -> None:
        """reasoning_effort='none' with non-Gemini-3/Gemma model → budget 0."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="none", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "thinkingBudget": 0,
        }

    @pytest.mark.anyio
    async def test_thinking_level_uppercase_high(self) -> None:
        """Uppercase 'HIGH' → direct thinkingLevel, bypasses budget/level."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="HIGH", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingLevel": "HIGH",
        }

    @pytest.mark.anyio
    async def test_thinking_level_unknown_effort(self) -> None:
        """Unknown reasoning_effort → goes to _google_level, defaults to HIGH."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="unknown", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingLevel": "HIGH",
        }

    @pytest.mark.anyio
    async def test_thinking_level_low_gemini3_pro(self) -> None:
        """Gemini 3 Pro with low effort → budget returns None → level LOW."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="low", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-3-pro-v1",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingLevel": "LOW",
        }

    @pytest.mark.anyio
    async def test_thinking_level_low_gemma4(self) -> None:
        """Gemma 4 with low effort → budget returns None → level MINIMAL."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="low", client=client)
            await _collect(
                provider.stream_response(
                    model="gemma-4-9b",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingLevel": "MINIMAL",
        }

    @pytest.mark.anyio
    async def test_thinking_level_budget_25_pro(self) -> None:
        """2.5-pro with high effort → correct budget."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="high", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-pro-exp-03-25",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 32768,
        }

    @pytest.mark.anyio
    async def test_thinking_level_budget_25_flash_lite(self) -> None:
        """2.5-flash-lite with high effort → correct budget."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="high", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash-lite-001",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": 24576,
        }

    @pytest.mark.anyio
    async def test_thinking_level_budget_unknown_model(self) -> None:
        """Unknown model with high effort → budget returns -1."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="high", client=client)
            await _collect(
                provider.stream_response(
                    model="unknown-model-42",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True,
            "thinkingBudget": -1,
        }


# ---------------------------------------------------------------------------
# Group 4 — SSE streaming tests
# ---------------------------------------------------------------------------

class TestSseStreaming:
    """Full event streaming via httpx.MockTransport."""

    @pytest.mark.anyio
    async def test_thinking_delta_emitted(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"reasoning...",'
            '"thought":true}]},"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        thinking_events = [e for e in events if isinstance(e, ProviderThinkingDeltaEvent)]
        assert len(thinking_events) == 1
        assert thinking_events[0].delta == "reasoning..."

    @pytest.mark.anyio
    async def test_text_delta_emitted(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}'
            ',"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        text_events = [e for e in events if isinstance(e, ProviderTextDeltaEvent)]
        assert len(text_events) == 1
        assert text_events[0].delta == "Hello"

    @pytest.mark.anyio
    async def test_mixed_thinking_and_text(self) -> None:
        """Interleaved thought/text parts produce correct event sequence."""
        text = (
            'data: {"candidates":[{"content":{"parts":['
            '{"text":"think...","thought":true},'
            '{"text":"output"}'
            ']},"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert [e.type for e in events] == [
            "response_start",
            "thinking_delta",
            "text_delta",
            "response_end",
        ]

    @pytest.mark.anyio
    async def test_tool_call_event(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"functionCall":{'
            '"id":"call-1","name":"read","args":{"path":"README.md"}}}'
            ']},"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ProviderToolCallEvent)]
        assert len(tool_call_events) == 1
        tc = tool_call_events[0].tool_call
        assert tc.id == "call-1"
        assert tc.name == "read"
        assert tc.arguments == {"path": "README.md"}
        assert tc.thought_signature is None

    @pytest.mark.anyio
    async def test_tool_call_with_thought_signature(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"functionCall":{'
            '"id":"call-1","name":"read","args":{},'
            '"thoughtSignature":"sig123"}}]},'
            '"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ProviderToolCallEvent)]
        assert len(tool_call_events) == 1
        assert tool_call_events[0].tool_call.thought_signature == "sig123"

    @pytest.mark.anyio
    async def test_tool_call_no_id(self) -> None:
        """functionCall without id → default id 'tool-call-N'."""
        text = (
            'data: {"candidates":[{"content":{"parts":[{"functionCall":{'
            '"name":"read","args":{}}}'
            ']},"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ProviderToolCallEvent)]
        assert len(tool_call_events) == 1
        assert tool_call_events[0].tool_call.id == "tool-call-0"

    @pytest.mark.anyio
    async def test_multiple_tool_calls(self) -> None:
        """Multiple functionCall parts → multiple ToolCallEvents."""
        text = (
            'data: {"candidates":[{"content":{"parts":['
            '{"functionCall":{"id":"fc-1","name":"read","args":{"path":"README.md"}}},'
            '{"functionCall":{"id":"fc-2","name":"search","args":{"query":"test"}}}'
            ']},"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        tool_call_events = [e for e in events if isinstance(e, ProviderToolCallEvent)]
        assert len(tool_call_events) == 2
        assert tool_call_events[0].tool_call.name == "read"
        assert tool_call_events[1].tool_call.name == "search"

    @pytest.mark.anyio
    async def test_thinking_text_in_final_message(self) -> None:
        """AssistantMessage.thinking_text accumulates thinking parts."""
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"step1"'
            ',"thought":true}]},"finishReason":"STOP"}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"step2"'
            ',"thought":true}]},"finishReason":"STOP"}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"output"}]}'
            ',"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert isinstance(events[-1], ProviderResponseEndEvent)
        assert events[-1].message.thinking_text == "step1step2"
        assert events[-1].message.content == "output"

    @pytest.mark.anyio
    async def test_finish_reason_stop(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}'
            ',"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert isinstance(events[-1], ProviderResponseEndEvent)
        assert events[-1].finish_reason == "stop"

    @pytest.mark.anyio
    async def test_finish_reason_max_tokens(self) -> None:
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}'
            ',"finishReason":"MAX_TOKENS"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert isinstance(events[-1], ProviderResponseEndEvent)
        assert events[-1].finish_reason == "length"

    @pytest.mark.anyio
    async def test_system_instruction_at_top_level(self) -> None:
        """systemInstruction must be at payload root, not inside generationConfig."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(reasoning_effort="low", client=client)
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="You are Tau.",
                    messages=[UserMessage(content="Say ok")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["systemInstruction"] == {"parts": [{"text": "You are Tau."}]}
        assert "systemInstruction" not in payload.get("generationConfig", {})

    @pytest.mark.anyio
    async def test_no_thinking_text_when_none_streamed(self) -> None:
        """No thinking parts → thinking_text stays empty string."""
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text='data: {"candidates":[{"content":{"parts":[{"text":"hello"}]},'
                '"finishReason":"STOP"}]}\n\n',
                headers={"content-type": "text/event-stream"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert isinstance(events[-1], ProviderResponseEndEvent)
        assert events[-1].message.thinking_text == ""

    # -- Message conversion tests (_message_to_google coverage) --

    @pytest.mark.anyio
    async def test_message_conversion_assistant_with_content_and_tool_calls(self) -> None:
        """_message_to_google: AssistantMessage with content + tool_calls."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(client=client)
            await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[
                        UserMessage(content="weather?"),
                        AssistantMessage(
                            content="Let me check",
                            tool_calls=[
                                ToolCall(id="call-1", name="get_weather", arguments={"city": "Paris"})
                            ],
                        ),
                    ],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        contents = payload["contents"]
        assert contents[1]["parts"] == [
            {"text": "Let me check"},
            {"functionCall": {"id": "call-1", "name": "get_weather", "args": {"city": "Paris"}}},
        ]

    @pytest.mark.anyio
    async def test_message_conversion_assistant_with_thought_signature_echo(self) -> None:
        """_message_to_google: echoes thoughtSignature when set."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(client=client)
            await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[
                        UserMessage(content="weather?"),
                        AssistantMessage(
                            tool_calls=[
                                ToolCall(
                                    id="call-1",
                                    name="get_weather",
                                    arguments={"city": "Paris"},
                                    thought_signature="sig123",
                                )
                            ],
                        ),
                    ],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        fc = payload["contents"][1]["parts"][0]["functionCall"]
        assert fc["id"] == "call-1"
        assert fc["thoughtSignature"] == "sig123"

    @pytest.mark.anyio
    async def test_message_conversion_tool_result(self) -> None:
        """_message_to_google: ToolResultMessage → functionResponse."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(client=client)
            await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[
                        UserMessage(content="weather?"),
                        AssistantMessage(
                            tool_calls=[
                                ToolCall(id="call-1", name="get_weather", arguments={"city": "Paris"})
                            ],
                        ),
                        AgentToolResult(
                            tool_call_id="call-1",
                            name="get_weather",
                            ok=True,
                            content='{"temp_c": 19}',
                        ),
                    ],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        fr = payload["contents"][2]["parts"][0]["functionResponse"]
        assert fr["name"] == "get_weather"
        assert fr["response"]["output"] == '{"temp_c": 19}'

    @pytest.mark.anyio
    async def test_message_conversion_tool_result_error(self) -> None:
        """_message_to_google: ToolResultMessage with ok=False → 'error' key."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(client=client)
            await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[
                        UserMessage(content="weather?"),
                        AssistantMessage(
                            tool_calls=[
                                ToolCall(id="call-1", name="get_weather", arguments={"city": "Unknown"})
                            ],
                        ),
                        AgentToolResult(
                            tool_call_id="call-1",
                            name="get_weather",
                            ok=False,
                            content="City not found",
                        ),
                    ],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        fr = payload["contents"][2]["parts"][0]["functionResponse"]
        assert fr["response"]["error"] == "City not found"

    # -- max_tokens and tools in payload coverage --

    @pytest.mark.anyio
    async def test_max_tokens_in_payload(self) -> None:
        """Config max_tokens → maxOutputTokens in generationConfig."""
        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = GoogleGenerativeAIProvider(
                OpenAICompatibleConfig(
                    api_key="test-key",
                    base_url="https://generativelanguage.googleapis.com/v1beta",
                    max_tokens=100,
                    max_retries=0,
                ),
                client=client,
            )
            await _collect(
                provider.stream_response(
                    model="gemini-2.5-flash",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        payload = loads(requests[0].content)
        assert payload["generationConfig"]["maxOutputTokens"] == 100

    @pytest.mark.anyio
    async def test_tools_in_payload(self) -> None:
        """Tools param → functionDeclarations in payload with sanitized schema."""
        async def executor(
            arguments: Mapping[str, JSONValue],
            signal: object | None = None,
        ) -> AgentToolResult:
            del signal
            return AgentToolResult(
                tool_call_id="call-1", name="get_weather", ok=True, content=str(arguments)
            )

        tool = AgentTool(
            name="get_weather",
            description="Get current weather",
            input_schema={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "additionalProperties": False,
            },
            executor=executor,
        )

        requests: list[httpx.Request] = []

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_ok_handler(requests))
        ) as client:
            provider = _make_provider(client=client)
            await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="weather?")],
                    tools=[tool],
                )
            )

        payload = loads(requests[0].content)
        decls = payload["tools"][0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "get_weather"
        assert decls[0]["description"] == "Get current weather"
        assert "additionalProperties" not in decls[0]["parameters"]

    # -- Parser edge cases --

    @pytest.mark.anyio
    async def test_sse_parser_edge_cases(self) -> None:
        """Feed handles invalid/missing/non-Mapping candidates, content, parts."""
        text = (
            'data: {invalid}\n\n'
            'data: {"candidates":"not_a_list"}\n\n'
            'data: {"candidates":[42]}\n\n'
            'data: {"candidates":[{"no_content":true}]}\n\n'
            'data: {"candidates":[{"content":{"not_parts":[]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[42,{"text":"done"}]}}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        # The only valid content is "done" at the end
        text_events = [e for e in events if isinstance(e, ProviderTextDeltaEvent)]
        assert len(text_events) == 1
        assert text_events[0].delta == "done"
        assert isinstance(events[-1], ProviderResponseEndEvent)

    @pytest.mark.anyio
    async def test_sse_parser_malformed_json_produces_error_event(self) -> None:
        """Invalid JSON in SSE line → silently skipped, valid lines still work."""
        text = (
            'data: {broken\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"works"}]}'
            ',"finishReason":"STOP"}]}\n\n'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events = await _collect(
                provider.stream_response(
                    model="test",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        text_events = [e for e in events if isinstance(e, ProviderTextDeltaEvent)]
        assert len(text_events) == 1
        assert text_events[0].delta == "works"

    @pytest.mark.anyio
    async def test_cancellation_during_sse_streaming(self) -> None:
        """Cancel signal during SSE processing → stops after current event."""
        text = (
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}'
            ',"finishReason":"STOP"}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"World"}]}'
            ',"finishReason":"STOP"}]}\n\n'
        )

        signal = SimpleCancellationToken()

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(client=client)
            events: list[object] = []
            async for event in provider.stream_response(
                model="test",
                system="",
                messages=[UserMessage(content="hi")],
                tools=[],
                signal=signal,
            ):
                events.append(event)
                if isinstance(event, ProviderTextDeltaEvent):
                    signal.cancel()

        assert [e.type for e in events] == [
            "response_start",
            "text_delta",
        ]
        assert isinstance(events[0], ProviderResponseStartEvent)
        assert isinstance(events[1], ProviderTextDeltaEvent)
        assert events[1].delta == "Hello"


# ---------------------------------------------------------------------------
# Group 5 — Error / retry tests
# ---------------------------------------------------------------------------

class TestErrorRetry:
    """HTTP error handling, retries, cancellation."""

    @pytest.mark.anyio
    async def test_http_400_no_retry(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(400, text="bad request")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=3, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert len(requests) == 1
        assert isinstance(events[-1], ProviderErrorEvent)
        assert "400" in events[-1].message

    @pytest.mark.anyio
    async def test_http_429_retry_then_success(self) -> None:
        """First request 429 → retry → second request 200."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, text="rate limited")
            return httpx.Response(
                200,
                text=_OK_SSE,
                headers={"content-type": "text/event-stream"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=1, max_retry_delay_seconds=0, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert len(requests) == 2
        assert isinstance(events[0], ProviderRetryEvent)
        # max_retries=1 → max_attempts=2, first retry at attempt=0 → next_attempt=2
        assert events[0].attempt == 2
        assert events[0].max_attempts == 2
        assert events[0].delay_seconds == 0
        assert events[0].data == {"status_code": 429, "body": "rate limited"}
        assert [e.type for e in events] == [
            "retry",
            "response_start",
            "text_delta",
            "response_end",
        ]

    @pytest.mark.anyio
    async def test_http_429_all_retries_exhausted(self) -> None:
        """All retries on 429 exhausted → final ProviderErrorEvent."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(429, text="rate limited")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=2, max_retry_delay_seconds=0, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        # max_retries=2 → max_attempts=3
        # attempt=0 → retry (2/3), attempt=1 → retry (3/3), attempt=2 → error
        assert len(requests) == 3
        retry_events = [e for e in events if isinstance(e, ProviderRetryEvent)]
        assert len(retry_events) == 2
        assert retry_events[0].attempt == 2
        assert retry_events[0].max_attempts == 3
        assert retry_events[1].attempt == 3
        assert retry_events[1].max_attempts == 3
        assert isinstance(events[-1], ProviderErrorEvent)
        assert "429" in events[-1].message

    @pytest.mark.anyio
    async def test_http_429_all_retries_exhausted_error_data(self) -> None:
        """Verify ProviderErrorEvent data format on exhausted retries."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(429, text="rate limited")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=1, max_retry_delay_seconds=0, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert isinstance(events[-1], ProviderErrorEvent)
        assert events[-1].data == {
            "status_code": 429,
            "body": "rate limited",
        }

    @pytest.mark.anyio
    async def test_network_error_retry(self) -> None:
        """Network error on first attempt → retry → second attempt succeeds."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                raise httpx.ReadError("connection reset")
            return httpx.Response(
                200,
                text=_OK_SSE,
                headers={"content-type": "text/event-stream"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=1, max_retry_delay_seconds=0, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        assert len(requests) == 2
        assert isinstance(events[0], ProviderRetryEvent)
        assert events[0].data == {
            "error": "connection reset",
            "error_type": "ReadError",
        }
        assert [e.type for e in events] == [
            "retry",
            "response_start",
            "text_delta",
            "response_end",
        ]

    @pytest.mark.anyio
    async def test_network_error_after_content(self) -> None:
        """Error after content emitted → no retry, immediate error."""

        class _FailingAfterContent(httpx.Response):
            """Yields one SSE line then fails with a network error."""

            async def aiter_lines(self) -> AsyncIterator[str]:
                yield (
                    'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}'
                    ',"finishReason":"STOP"}]}\n\n'
                )
                raise httpx.ReadError("connection lost during streaming")

        def handler(_request: httpx.Request) -> httpx.Response:
            return _FailingAfterContent(
                200,
                headers={"content-type": "text/event-stream"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(max_retries=3, client=client)
            events = await _collect(
                provider.stream_response(
                    model="test-model",
                    system="",
                    messages=[UserMessage(content="hi")],
                    tools=[],
                )
            )

        # Content was emitted (parser.emitted_content=True), so no retry
        assert isinstance(events[-1], ProviderErrorEvent)
        assert "connection lost" in events[-1].message or "ReadError" in events[-1].message
        # Should have seen the text delta before the error
        text_events = [e for e in events if isinstance(e, ProviderTextDeltaEvent)]
        assert len(text_events) == 1
        assert text_events[0].delta == "Hello"

    @pytest.mark.anyio
    async def test_cancellation_during_retry(self) -> None:
        """CancellationToken cancels during retry wait → stops immediately."""
        requests: list[httpx.Request] = []
        signal = SimpleCancellationToken()

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(429, text="rate limited")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(
                max_retries=2, max_retry_delay_seconds=1, client=client
            )
            events: list[object] = []
            async for event in provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="hi")],
                tools=[],
                signal=signal,
            ):
                events.append(event)
                if isinstance(event, ProviderRetryEvent):
                    signal.cancel()

        assert len(requests) == 1
        assert [e.type for e in events] == ["retry"]

    @pytest.mark.anyio
    async def test_network_error_cancellation_during_retry(self) -> None:
        """Network error retry cancelled → stops immediately (covers line 142)."""
        requests: list[httpx.Request] = []
        signal = SimpleCancellationToken()

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            raise httpx.ReadError("connection reset")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _make_provider(
                max_retries=2, max_retry_delay_seconds=1, client=client
            )
            events: list[object] = []
            async for event in provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="hi")],
                tools=[],
                signal=signal,
            ):
                events.append(event)
                if isinstance(event, ProviderRetryEvent):
                    signal.cancel()

        assert len(requests) == 1
        assert [e.type for e in events] == ["retry"]
