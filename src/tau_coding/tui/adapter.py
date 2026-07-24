"""Translate agent events into Textual TUI display state."""

from __future__ import annotations

from tau_agent.events import (
    AgentEndEvent,
    AgentEvent,
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
from tau_agent.provider_events import TextDeltaEvent, ThinkingDeltaEvent, ToolCallDeltaEvent
from tau_coding.tui.state import TuiState


class TuiEventAdapter:
    """Apply portable agent events to mutable TUI display state."""

    def __init__(self, state: TuiState) -> None:
        self.state = state
        self._assistant_start_item_index: int | None = None

    def apply(self, event: AgentEvent) -> None:
        """Apply one agent event to the display state."""
        if isinstance(event, AgentStartEvent):
            self.state.running = True
            self.state.error = None
            self._assistant_start_item_index = None
            return

        if isinstance(event, AgentEndEvent):
            self._flush_assistant_buffer()
            self.state.running = False
            return

        if isinstance(event, MessageStartEvent):
            msg = event.message
            if msg is None:
                return
            if msg.role == "assistant":
                self.state.assistant_buffer = ""
                self._assistant_start_item_index = len(self.state.items)
            return

        if isinstance(event, MessageUpdateEvent):
            ae = event.assistant_message_event
            if isinstance(ae, TextDeltaEvent):
                self.state.assistant_buffer += ae.delta
            elif isinstance(ae, ThinkingDeltaEvent):
                self.state.add_thinking_delta(ae.delta)
            elif isinstance(ae, ToolCallDeltaEvent):
                self._flush_assistant_buffer()
                self.state.add_tool_call(ae.partial)
            return

        if isinstance(event, MessageEndEvent):
            msg = event.message
            if msg is None:
                return
            if isinstance(msg, UserMessage):
                text = msg.text if hasattr(msg, "text") else str(msg.content)
                self.state.add_user_message(text)
                return
            if msg.role == "toolResult":
                return
            if isinstance(msg, AssistantMessage):
                # Clear provisional streaming items before inserting final message
                if self._assistant_start_item_index is not None:
                    del self.state.items[self._assistant_start_item_index:]
                    self._assistant_start_item_index = None
                text = msg.text if hasattr(msg, "text") else ""
                if not text:
                    text = self.state.assistant_buffer
                if text:
                    self.state.add_item("assistant", text)
                self.state.assistant_buffer = ""
                return
            # Fallback for other message types
            text = str(msg.content) if hasattr(msg, "content") else ""
            if text:
                self.state.add_item("assistant", text)
            return

        if isinstance(event, ToolExecutionStartEvent):
            self._flush_assistant_buffer()
            from tau_agent.messages import ToolCall
            tc = ToolCall(id=event.tool_call_id, name=event.tool_name, arguments=event.args)
            self.state.add_tool_call(tc)
            return

        if isinstance(event, ToolExecutionUpdateEvent):
            self.state.add_item("tool", f"… {event.tool_name}")
            return

        if isinstance(event, ToolExecutionEndEvent):
            result = event.result
            if result and result.content:
                text = "".join(
                    c.text if isinstance(c, TextContent) else str(c)
                    for c in result.content
                )
                self.state.add_item("tool", text)
            elif event.is_error:
                self.state.add_item("error", f"Tool error: {event.tool_name}")
            return

        if isinstance(event, TurnEndEvent):
            self._flush_assistant_buffer()
            return

    def _flush_assistant_buffer(self) -> None:
        if self.state.assistant_buffer:
            self.state.add_item("assistant", self.state.assistant_buffer)
            self.state.assistant_buffer = ""
