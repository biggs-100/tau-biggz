from pathlib import Path

from tau_agent.events import (
    AgentEndEvent,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
)
from tau_agent.messages import AssistantMessage, TextContent, ThinkingContent, UserMessage
from tau_agent.provider_events import TextDeltaEvent, ThinkingDeltaEvent
from tau_agent.tools import AgentToolResult, ToolCall
from tau_coding.skills import Skill, format_skill_invocation
from tau_coding.tui import TuiEventAdapter, TuiState
from tau_coding.tui.state import format_tool_call_block, format_tool_result_block


def test_tui_adapter_tracks_running_state() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(AgentStartEvent())
    assert state.running is True

    adapter.apply(AgentEndEvent())
    assert state.running is False


def test_tui_adapter_builds_assistant_items_from_streamed_messages() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(MessageStartEvent(message=AssistantMessage(content=[])))
    adapter.apply(MessageUpdateEvent(
        message=AssistantMessage(content=[TextContent(text="Hel")]),
        assistant_message_event=TextDeltaEvent(content_index=0, delta="Hel"),
    ))
    adapter.apply(MessageUpdateEvent(
        message=AssistantMessage(content=[TextContent(text="Hello")]),
        assistant_message_event=TextDeltaEvent(content_index=0, delta="lo"),
    ))
    assert state.assistant_buffer == "Hello"
    assert state.items == []

    adapter.apply(MessageEndEvent(message=AssistantMessage(content="Hello")))

    assert state.assistant_buffer == ""
    assert [(item.role, item.text) for item in state.items] == [("assistant", "Hello")]


def test_tui_adapter_builds_user_items_from_streamed_messages() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(MessageStartEvent(message=UserMessage(content="Hello Tau")))
    adapter.apply(MessageEndEvent(message=UserMessage(content="Hello Tau")))

    assert state.assistant_buffer == ""
    assert [(item.role, item.text) for item in state.items] == [("user", "Hello Tau")]


def test_tui_adapter_compacts_streamed_skill_invocations() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)
    skill = Skill(
        name="review",
        path=Path("/workspace/.tau/skills/review.md"),
        content="# Review\nFull noisy instructions.",
        description="Review code",
    )

    adapter.apply(
        MessageEndEvent(
            message=UserMessage(content=format_skill_invocation(skill, "check the auth flow"))
        )
    )

    assert [(item.role, item.text) for item in state.items] == [
        ("skill", "Using skill: review"),
        ("user", "check the auth flow"),
    ]


def test_tui_adapter_groups_thinking_deltas_separately() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(MessageUpdateEvent(
        message=AssistantMessage(content=[ThinkingContent(thinking="hidden ")]),
        assistant_message_event=ThinkingDeltaEvent(content_index=0, delta="hidden "),
    ))
    adapter.apply(MessageUpdateEvent(
        message=AssistantMessage(content=[ThinkingContent(thinking="hidden reasoning")]),
        assistant_message_event=ThinkingDeltaEvent(content_index=0, delta="reasoning"),
    ))

    assert [(item.role, item.text) for item in state.items] == [("thinking", "hidden reasoning")]
    assert state.show_thinking is False


def test_tui_adapter_flushes_assistant_buffer_before_tool_events() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(MessageUpdateEvent(
        message=AssistantMessage(content=[TextContent(text="Before tool")]),
        assistant_message_event=TextDeltaEvent(content_index=0, delta="Before tool"),
    ))
    adapter.apply(
        ToolExecutionStartEvent(
            tool_call_id="call-1",
            tool_name="read",
            args={"path": "README.md"},
        )
    )

    assert state.assistant_buffer == ""
    assert state.items[0].role == "assistant"
    assert state.items[0].text == "Before tool"
    assert state.items[1].role == "tool"
    assert "→ read" in state.items[1].text


def test_tui_adapter_renders_skill_file_reads_with_skill_style() -> None:
    skill = Skill(
        name="review",
        path=Path("/workspace/.tau/skills/review.md"),
        content="# Review",
        description="Review code",
    )
    state = TuiState(skills=(skill,))
    adapter = TuiEventAdapter(state)

    adapter.apply(
        ToolExecutionStartEvent(
            tool_call_id="call-1",
            tool_name="read",
            args={"path": "/workspace/.tau/skills/review.md"},
        )
    )
    adapter.apply(
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="read",
            result=AgentToolResult(
                tool_call_id="call-1",
                name="read",
                content=[TextContent(text="# Review\nFull instructions.")],
            ),
            is_error=False,
        )
    )

    assert [(item.role, item.text, item.tool_result_text) for item in state.items] == [
        ("skill", "Loading skill: review", None),
        ("tool", "# Review\nFull instructions.", None),
    ]


def test_tui_adapter_leaves_ordinary_reads_as_tool_items() -> None:
    skill = Skill(
        name="review",
        path=Path("/workspace/.tau/skills/review.md"),
        content="# Review",
        description="Review code",
    )
    state = TuiState(skills=(skill,))
    adapter = TuiEventAdapter(state)

    adapter.apply(
        ToolExecutionStartEvent(
            tool_call_id="call-1",
            tool_name="read",
            args={"path": "/workspace/README.md"},
        )
    )

    assert [(item.role, item.text) for item in state.items] == [
        ("tool", "→ read /workspace/README.md")
    ]


def test_tool_call_blocks_use_human_readable_invocations() -> None:
    assert (
        format_tool_call_block(
            ToolCall(
                id="call-1",
                name="read",
                arguments={"path": "tests/test_tui_app.py", "offset": 1, "limit": 80},
            )
        )
        == "→ read tests/test_tui_app.py:1-80"
    )
    assert (
        format_tool_call_block(
            ToolCall(id="call-2", name="edit", arguments={"path": "src/tau_coding/tui/app.py"})
        )
        == "→ edit src/tau_coding/tui/app.py"
    )
    assert (
        format_tool_call_block(
            ToolCall(
                id="call-3",
                name="bash",
                arguments={
                    "command": "git log --oneline --decorate --graph --max-count=8",
                    "timeout": 30,
                },
            )
        )
        == "$ git log --oneline --decorate --graph --max-count=8 (timeout 30s)"
    )


def test_tui_adapter_records_tool_updates_and_results() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(ToolExecutionUpdateEvent(
        tool_call_id="call-1",
        tool_name="read",
        args={},
        partial_result=AgentToolResult(content=[TextContent(text="reading")]),
    ))
    adapter.apply(
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="read",
            result=AgentToolResult(
                content=[TextContent(text="done")],
                tool_call_id="call-1",
                name="read",
            ),
            is_error=False,
        )
    )
    adapter.apply(
        ToolExecutionEndEvent(
            tool_call_id="call-2",
            tool_name="bash",
            result=AgentToolResult(
                content=[TextContent(text="failed")],
                tool_call_id="call-2",
                name="bash",
            ),
            is_error=True,
        )
    )

    assert [(item.role, item.text, item.tool_result_text) for item in state.items] == [
        ("tool", "… read", None),
        ("tool", "done", None),
        ("tool", "failed", None),
    ]


def test_tool_result_blocks_preview_long_content() -> None:
    content = "\n".join(f"line {index}" for index in range(1, 12))

    block = format_tool_result_block(name="read", ok=True, content=content)

    assert "line 1" in block
    assert "line 8" in block
    assert "line 9" not in block
    assert "3 more lines" in block


def test_tui_adapter_renders_live_edit_patch() -> None:
    state = TuiState()
    adapter = TuiEventAdapter(state)

    adapter.apply(
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="edit",
            result=AgentToolResult(
                tool_call_id="call-1",
                name="edit",
                content=[TextContent(text="Successfully replaced 1 block.")],
            ),
            is_error=False,
        )
    )

    assert [(item.role, item.text, item.tool_result_text) for item in state.items] == [
        ("tool", "Successfully replaced 1 block.", None),
    ]


def test_tui_adapter_flushes_buffer_on_turn_end() -> None:
    state = TuiState(running=True, assistant_buffer="partial")
    adapter = TuiEventAdapter(state)

    adapter.apply(TurnEndEvent())

    assert state.assistant_buffer == ""
    assert [(item.role, item.text) for item in state.items] == [("assistant", "partial")]
