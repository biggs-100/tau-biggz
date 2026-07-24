"""Pure provider/tool agent loop — Pi event protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from inspect import isawaitable

from tau_agent.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    ErrorEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from tau_agent.messages import (
    AgentMessage,
    AssistantContent,
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolResultMessage,
    UserMessage,
)
from tau_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallDeltaEvent,
)
from tau_agent.tools import AgentTool, AgentToolResult, ToolCall
from tau_ai.provider import CancellationToken, ModelProvider


async def run_agent_loop(
    *,
    provider: ModelProvider,
    model: str,
    system: str,
    messages: list[AgentMessage],
    tools: list[AgentTool],
    max_turns: int | None = None,
    signal: CancellationToken | None = None,
    get_steering_messages: Callable[[], Sequence[AgentMessage]] | None = None,
    get_follow_up_messages: Callable[[], Sequence[AgentMessage]] | None = None,
    prompt_message: UserMessage | None = None,
    before_tool_call: Callable[[ToolCall], Awaitable[None] | None] | None = None,
    after_tool_call: Callable[[ToolCall, AgentToolResult], Awaitable[None] | None] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run the pure agent loop and stream Pi-compatible agent events.

    The passed ``messages`` list is the transcript owned by the caller. The loop
    appends assistant messages and tool result messages to it as the run
    progresses. This keeps the loop stateless while allowing a future harness to
    own transcript state.
    """
    yield AgentStartEvent()

    if max_turns is not None and max_turns < 1:
        yield AgentEndEvent(messages=list(messages))
        return

    tool_by_name = {tool.name: tool for tool in tools}
    turn = 1

    while max_turns is None or turn <= max_turns:
        if signal is not None and signal.is_cancelled():
            break

        yield TurnStartEvent()

        if prompt_message is not None:
            yield MessageStartEvent(message=prompt_message)
            yield MessageEndEvent(message=prompt_message)
            prompt_message = None

        assistant_box: list[AssistantMessage | None] = [None]
        async for agent_event in _assistant_events(
            provider.stream_response(  # type: ignore[arg-type]
                model=model,
                system=system,
                messages=messages,
                tools=tools,
                signal=signal,
            ),
            out=assistant_box,
        ):
            yield agent_event
        assistant_message = assistant_box[0]

        if assistant_message is None:
            break

        messages.append(assistant_message)
        tool_results: list[AgentToolResult] = []

        if not assistant_message.tool_calls:
            yield TurnEndEvent(message=assistant_message, tool_results=[])
            queue_events = _inject_queued_messages(messages, get_steering_messages)
            if queue_events:
                for queue_event in queue_events:
                    yield queue_event
                turn += 1
                continue
            queue_events = _inject_queued_messages(messages, get_follow_up_messages)
            if queue_events:
                for queue_event in queue_events:
                    yield queue_event
                turn += 1
                continue
            break

        async for tool_event in _execute_tool_calls(
            assistant_message.tool_calls,
            tool_by_name,
            messages,
            signal,
            before_tool_call=before_tool_call,
            after_tool_call=after_tool_call,
        ):
            if isinstance(tool_event, ToolExecutionEndEvent) and tool_event.result is not None:
                tool_results.append(tool_event.result)
            yield tool_event

        yield TurnEndEvent(message=assistant_message, tool_results=tool_results)
        for queue_event in _inject_queued_messages(messages, get_steering_messages):
            yield queue_event
        turn += 1

    yield AgentEndEvent(messages=list(messages))


async def _assistant_events(
    provider_stream: AsyncIterator[AssistantMessageEvent],
    *,
    out: list[AssistantMessage | None],
) -> AsyncIterator[AgentEvent]:
    """Consume a provider assistant event stream and yield agent Message events.

    Stores the final ``AssistantMessage`` in ``out[0]``, or ``None`` on error.
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_call_map: dict[int, ToolCall] = {}

    def _build_message() -> AssistantMessage:
        blocks: list[AssistantContent] = []
        if text_parts:
            blocks.append(TextContent(text="".join(text_parts)))
        if thinking_parts:
            blocks.append(ThinkingContent(thinking="".join(thinking_parts)))
        for idx in sorted(tool_call_map):
            blocks.append(tool_call_map[idx])
        return AssistantMessage(content=blocks)

    async for event in provider_stream:
        if isinstance(event, AssistantStartEvent):
            yield MessageStartEvent(message=event.partial)
        elif isinstance(event, TextDeltaEvent):
            text_parts.append(event.delta)
            yield MessageUpdateEvent(message=_build_message(), assistant_message_event=event)
        elif isinstance(event, ThinkingDeltaEvent):
            thinking_parts.append(event.delta)
            yield MessageUpdateEvent(message=_build_message(), assistant_message_event=event)
        elif isinstance(event, ToolCallDeltaEvent):
            tool_call_map[event.content_index] = event.partial
            yield MessageUpdateEvent(message=_build_message(), assistant_message_event=event)
        elif isinstance(event, AssistantDoneEvent):
            out[0] = event.message
            if event.message is not None:
                yield MessageEndEvent(message=event.message)
            return
        elif isinstance(event, AssistantErrorEvent):
            out[0] = None
            error_text = event.error.text if event.error else "Assistant error"
            yield ErrorEvent(message=error_text, recoverable=False)
            return


def _inject_queued_messages(
    messages: list[AgentMessage],
    get_messages: Callable[[], Sequence[AgentMessage]] | None,
) -> tuple[AgentEvent, ...]:
    if get_messages is None:
        return ()
    queued_messages = tuple(get_messages())
    if not queued_messages:
        return ()

    messages.extend(queued_messages)
    events: list[AgentEvent] = []
    for message in queued_messages:
        events.append(MessageStartEvent(message=message))
        events.append(MessageEndEvent(message=message))
    return tuple(events)


async def _execute_tool_calls(
    tool_calls: list[ToolCall],
    tool_by_name: Mapping[str, AgentTool],
    messages: list[AgentMessage],
    signal: CancellationToken | None,
    before_tool_call: Callable[[ToolCall], Awaitable[None] | None] | None = None,
    after_tool_call: Callable[[ToolCall, AgentToolResult], Awaitable[None] | None] | None = None,
) -> AsyncIterator[AgentEvent]:
    for index, tool_call in enumerate(tool_calls):
        if signal is not None and signal.is_cancelled():
            for cancelled_tool_call in tool_calls[index:]:
                result = _cancelled_tool_result(cancelled_tool_call)
                messages.append(
                    _tool_result_message(result, cancelled_tool_call.id, cancelled_tool_call.name, is_error=True)
                )
                yield ToolExecutionEndEvent(
                    tool_call_id=cancelled_tool_call.id,
                    tool_name=cancelled_tool_call.name,
                    result=result,
                    is_error=True,
                )
            return

        yield ToolExecutionStartEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
        )

        if before_tool_call is not None:
            hook_result = before_tool_call(tool_call)
            if isawaitable(hook_result):
                await hook_result

        tool = tool_by_name.get(tool_call.name)
        if tool is None:
            result = _unknown_tool_result(tool_call)
        else:
            result = await _execute_tool(tool, tool_call, signal)

        if after_tool_call is not None:
            hook_result = after_tool_call(tool_call, result)
            if isawaitable(hook_result):
                await hook_result

        is_error = tool is None
        messages.append(
            _tool_result_message(result, tool_call.id, tool_call.name, is_error=is_error)
        )
        yield ToolExecutionUpdateEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
            partial_result=result,
        )
        yield ToolExecutionEndEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
            is_error=is_error,
        )


async def _execute_tool(
    tool: AgentTool,
    tool_call: ToolCall,
    signal: CancellationToken | None,
) -> AgentToolResult:
    try:
        return await tool.execute(tool_call.arguments, signal=signal)
    except Exception as exc:  # noqa: BLE001 - tools are an isolation boundary
        return AgentToolResult(
            content=[TextContent(text=str(exc))],
        )


def _unknown_tool_result(tool_call: ToolCall) -> AgentToolResult:
    return AgentToolResult(
        content=[TextContent(text=f"Unknown tool: {tool_call.name}")],
    )


def _cancelled_tool_result(tool_call: ToolCall) -> AgentToolResult:
    return AgentToolResult(
        content=[TextContent(text="Tool call cancelled")],
    )


def _tool_result_message(
    result: AgentToolResult,
    tool_call_id: str,
    tool_name: str,
    *,
    is_error: bool = False,
) -> ToolResultMessage:
    content = result.content
    if isinstance(content, str):
        content = [TextContent(text=content)]

    return ToolResultMessage(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        content=content,
        is_error=is_error,
        details=result.details,
    )
