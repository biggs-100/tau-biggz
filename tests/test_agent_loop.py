from collections.abc import AsyncIterator, Mapping

import pytest

from tau_agent import (
    AgentEvent,
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    SimpleCancellationToken,
    TextContent,
    ToolCall,
    ToolExecutionEndEvent,
    ToolResultMessage,
    UserMessage,
)
from tau_agent.loop import run_agent_loop
from tau_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
)
from tau_agent.types import JSONValue
from tau_ai import CancellationToken, FakeProvider


async def _collect(stream: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in stream]


@pytest.mark.anyio
async def test_agent_loop_streams_text_and_appends_assistant_message() -> None:
    messages = [UserMessage(content="Say hello")]
    assistant = AssistantMessage(content=[TextContent(text="Hello")])
    provider = FakeProvider(
        [
            AssistantStartEvent(partial=AssistantMessage(content=[])),
            TextDeltaEvent(content_index=0, delta="Hel"),
            TextDeltaEvent(content_index=0, delta="lo"),
            AssistantDoneEvent(reason="end_turn", message=assistant),
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert messages == [UserMessage(content="Say hello"), assistant]


@pytest.mark.anyio
async def test_agent_loop_streams_thinking_deltas_without_recording_them() -> None:
    messages = [UserMessage(content="Think briefly")]
    assistant = AssistantMessage(content=[TextContent(text="Done")])
    provider = FakeProvider(
        [
            AssistantStartEvent(partial=AssistantMessage(content=[])),
            ThinkingDeltaEvent(content_index=0, delta="hidden "),
            ThinkingDeltaEvent(content_index=0, delta="reasoning"),
            TextDeltaEvent(content_index=1, delta="Done"),
            AssistantDoneEvent(reason="end_turn", message=assistant),
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
        )
    )

    thinking_events = [
        event.assistant_message_event
        for event in events
        if isinstance(event, AgentEvent) and getattr(event, "type", None) == "message_update"
        and event.assistant_message_event is not None
        and isinstance(event.assistant_message_event, ThinkingDeltaEvent)
    ]
    assert [event.delta for event in thinking_events] == ["hidden ", "reasoning"]
    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_update",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert messages == [UserMessage(content="Think briefly"), assistant]


@pytest.mark.anyio
async def test_agent_loop_executes_tools_and_continues_until_no_tool_calls() -> None:
    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: object | None = None,
    ) -> AgentToolResult:
        del signal
        return AgentToolResult(
            content=[TextContent(text=f"contents of {arguments['path']}")],
            details={"source": "fake"},
        )

    tool = AgentTool(
        name="read",
        description="Read a file.",
        input_schema={"type": "object"},
        executor=executor,
    )
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    first_assistant = AssistantMessage(content=[TextContent(text="I'll read it."), tool_call])
    final_assistant = AssistantMessage(content=[TextContent(text="README.md contains project documentation.")])
    messages = [UserMessage(content="Read README.md")]
    provider = FakeProvider(
        [
            [
                AssistantStartEvent(partial=AssistantMessage(content=[tool_call])),
                AssistantDoneEvent(reason="end_turn", message=first_assistant),
            ],
            [
                AssistantStartEvent(partial=AssistantMessage(content=[])),
                TextDeltaEvent(content_index=0, delta=final_assistant.text),
                AssistantDoneEvent(reason="end_turn", message=final_assistant),
            ],
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[tool],
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
        "turn_end",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert messages == [
        UserMessage(content="Read README.md"),
        first_assistant,
        ToolResultMessage(
            tool_call_id="call-1",
            tool_name="read",
            content=[TextContent(text="contents of README.md")],
            details={"source": "fake"},
        ),
        final_assistant,
    ]
    assert len(provider.calls) == 2
    assert provider.calls[1][2] == messages[:3]


@pytest.mark.anyio
async def test_agent_loop_passes_cancellation_signal_to_tools() -> None:
    observed: list[CancellationToken | None] = []

    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
    ) -> AgentToolResult:
        del arguments
        observed.append(signal)
        return AgentToolResult(content=[TextContent(text="ok")])

    tool = AgentTool(
        name="read",
        description="Read a file.",
        input_schema={"type": "object"},
        executor=executor,
    )
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    first_assistant = AssistantMessage(content=[TextContent(text="I'll read it."), tool_call])
    final_assistant = AssistantMessage(content=[TextContent(text="Done.")])
    provider = FakeProvider(
        [
            [
                AssistantStartEvent(partial=AssistantMessage(content=[tool_call])),
                AssistantDoneEvent(reason="end_turn", message=first_assistant),
            ],
            [
                AssistantStartEvent(partial=AssistantMessage(content=[])),
                AssistantDoneEvent(reason="end_turn", message=final_assistant),
            ],
        ]
    )
    signal = SimpleCancellationToken()

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=[UserMessage(content="Read README.md")],
            tools=[tool],
            signal=signal,
        )
    )

    assert observed
    assert observed[0] is signal


@pytest.mark.anyio
async def test_agent_loop_records_cancelled_results_for_skipped_tool_calls() -> None:
    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: SimpleCancellationToken | None = None,
    ) -> AgentToolResult:
        del arguments
        if signal is not None:
            signal.cancel()
        return AgentToolResult(content=[TextContent(text="ok")])

    tool = AgentTool(
        name="read",
        description="Read a file.",
        input_schema={"type": "object"},
        executor=executor,
    )
    tool_calls = [
        ToolCall(id="call-1", name="read", arguments={"path": "README.md"}),
        ToolCall(id="call-2", name="read", arguments={"path": "pyproject.toml"}),
    ]
    assistant = AssistantMessage(content=[TextContent(text="I'll read both."), *tool_calls])
    messages = [UserMessage(content="Read project files")]
    provider = FakeProvider(
        [AssistantStartEvent(partial=AssistantMessage(content=[*tool_calls])), AssistantDoneEvent(reason="end_turn", message=assistant)]
    )
    signal = SimpleCancellationToken()

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[tool],
            signal=signal,
        )
    )

    assert messages == [
        UserMessage(content="Read project files"),
        assistant,
        ToolResultMessage(tool_call_id="call-1", tool_name="read", content=[TextContent(text="ok")]),
        ToolResultMessage(
            tool_call_id="call-2",
            tool_name="read",
            content=[TextContent(text="Tool call cancelled")],
            is_error=True,
        ),
    ]
    assert [event.type for event in events].count("tool_execution_end") == 2


@pytest.mark.anyio
async def test_agent_loop_injects_steering_after_tool_batch() -> None:
    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: object | None = None,
    ) -> AgentToolResult:
        del signal
        return AgentToolResult(
            content=[TextContent(text=f"contents of {arguments['path']}")],
        )

    tool = AgentTool(
        name="read",
        description="Read a file.",
        input_schema={"type": "object"},
        executor=executor,
    )
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    first_assistant = AssistantMessage(content=[TextContent(text="I'll read it."), tool_call])
    final_assistant = AssistantMessage(content=[TextContent(text="Updated plan.")])
    messages = [UserMessage(content="Read README.md")]
    steering_queue = [UserMessage(content="Also summarize it")]
    provider = FakeProvider(
        [
            [
                AssistantStartEvent(partial=AssistantMessage(content=[tool_call])),
                AssistantDoneEvent(reason="end_turn", message=first_assistant),
            ],
            [
                AssistantStartEvent(partial=AssistantMessage(content=[])),
                AssistantDoneEvent(reason="end_turn", message=final_assistant),
            ],
        ]
    )

    def get_steering_messages() -> tuple[UserMessage, ...]:
        if not steering_queue:
            return ()
        return (steering_queue.pop(0),)

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[tool],
            get_steering_messages=get_steering_messages,
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
        "turn_end",
        "message_start",
        "message_end",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert provider.calls[1][2] == messages[:4]
    assert messages == [
        UserMessage(content="Read README.md"),
        first_assistant,
        ToolResultMessage(
            tool_call_id="call-1",
            tool_name="read",
            content=[TextContent(text="contents of README.md")],
        ),
        UserMessage(content="Also summarize it"),
        final_assistant,
    ]


@pytest.mark.anyio
async def test_agent_loop_injects_follow_up_only_when_run_would_stop() -> None:
    first_assistant = AssistantMessage(content=[TextContent(text="Initial answer.")])
    final_assistant = AssistantMessage(content=[TextContent(text="Follow-up answer.")])
    messages = [UserMessage(content="Start")]
    follow_up_queue = [UserMessage(content="One more thing")]
    provider = FakeProvider(
        [
            [
                AssistantStartEvent(partial=AssistantMessage(content=[])),
                AssistantDoneEvent(reason="end_turn", message=first_assistant),
            ],
            [
                AssistantStartEvent(partial=AssistantMessage(content=[])),
                AssistantDoneEvent(reason="end_turn", message=final_assistant),
            ],
        ]
    )

    def get_follow_up_messages() -> tuple[UserMessage, ...]:
        if not follow_up_queue:
            return ()
        return (follow_up_queue.pop(0),)

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
            get_follow_up_messages=get_follow_up_messages,
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "message_start",
        "message_end",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert len(provider.calls) == 2
    assert provider.calls[1][2] == messages[:3]
    assert messages == [
        UserMessage(content="Start"),
        first_assistant,
        UserMessage(content="One more thing"),
        final_assistant,
    ]


@pytest.mark.anyio
async def test_agent_loop_records_unknown_tool_as_failed_tool_result() -> None:
    tool_call = ToolCall(id="call-1", name="missing", arguments={})
    assistant = AssistantMessage(content=[TextContent(text="I'll use a tool."), tool_call])
    messages = [UserMessage(content="Use a missing tool")]
    provider = FakeProvider(
        [AssistantStartEvent(partial=AssistantMessage(content=[tool_call])), AssistantDoneEvent(reason="end_turn", message=assistant)]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
            max_turns=1,
        )
    )

    tool_end_events = [event for event in events if isinstance(event, ToolExecutionEndEvent)]

    assert tool_end_events[0].is_error is True
    assert messages[-1] == ToolResultMessage(
        tool_call_id="call-1",
        tool_name="missing",
        content=[TextContent(text="Unknown tool: missing")],
        is_error=True,
    )


@pytest.mark.anyio
async def test_agent_loop_converts_assistant_error_to_loop_exit() -> None:
    messages = [UserMessage(content="hello")]
    provider = FakeProvider([AssistantErrorEvent(reason="error")])

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "error",
        "agent_end",
    ]
    assert messages == [UserMessage(content="hello")]


@pytest.mark.anyio
async def test_agent_loop_has_no_default_max_turn_limit() -> None:
    tool_call = ToolCall(id="call-1", name="missing", arguments={})
    looping_assistant = AssistantMessage(content=[TextContent(text="Again."), tool_call])
    final_assistant = AssistantMessage(content=[TextContent(text="Done.")])
    messages = [UserMessage(content="loop for a while")]
    provider = FakeProvider(
        [
            [AssistantStartEvent(partial=AssistantMessage(content=[tool_call])), AssistantDoneEvent(reason="end_turn", message=looping_assistant)]
            for _ in range(9)
        ]
        + [
            [AssistantStartEvent(partial=AssistantMessage(content=[])), AssistantDoneEvent(reason="end_turn", message=final_assistant)]
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
        )
    )

    assert len(provider.calls) == 10
    assert messages[-1] == final_assistant


@pytest.mark.anyio
async def test_agent_loop_stops_after_configured_max_turns() -> None:
    tool_call = ToolCall(id="call-1", name="missing", arguments={})
    assistant = AssistantMessage(content=[TextContent(text="Again."), tool_call])
    messages = [UserMessage(content="loop forever")]
    provider = FakeProvider(
        [
            [
                AssistantStartEvent(partial=AssistantMessage(content=[tool_call])),
                AssistantDoneEvent(reason="end_turn", message=assistant),
            ],
            [
                AssistantStartEvent(partial=AssistantMessage(content=[tool_call])),
                AssistantDoneEvent(reason="end_turn", message=assistant),
            ],
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Tau.",
            messages=messages,
            tools=[],
            max_turns=1,
        )
    )

    assert len(provider.calls) == 1
