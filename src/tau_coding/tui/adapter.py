"""Translate agent events into Textual TUI display state."""

from tau_agent import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    AgentToolResult,
    ErrorEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    MessageStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from tau_coding.tui.state import TuiState


class TuiEventAdapter:
    """Apply portable agent events to mutable TUI display state."""

    def __init__(self, state: TuiState) -> None:
        self.state = state

    def apply(self, event: AgentEvent) -> None:
        """Apply one agent event to the display state."""
        if isinstance(event, AgentStartEvent):
            self.state.running = True
            self.state.error = None
            return

        if isinstance(event, AgentEndEvent):
            self._flush_assistant_buffer()
            self.state.running = False
            return

        if isinstance(event, MessageStartEvent):
            self.state.assistant_buffer = ""
            return

        if isinstance(event, MessageDeltaEvent):
            self.state.assistant_buffer += event.delta
            return

        if isinstance(event, MessageEndEvent):
            text = event.message.content or self.state.assistant_buffer
            if text:
                self.state.add_item("assistant", text)
            self.state.assistant_buffer = ""
            return

        if isinstance(event, ToolExecutionStartEvent):
            self._flush_assistant_buffer()
            self.state.add_item(
                "tool",
                f"→ {event.tool_call.name} {event.tool_call.arguments}",
            )
            return

        if isinstance(event, ToolExecutionUpdateEvent):
            self.state.add_item("tool", f"… {event.message}")
            return

        if isinstance(event, ToolExecutionEndEvent):
            self.state.add_item("tool", _tool_result_text(event.result))
            return

        if isinstance(event, ErrorEvent):
            self._flush_assistant_buffer()
            self.state.error = event.message
            self.state.add_item("error", f"Error: {event.message}")
            if not event.recoverable:
                self.state.running = False

    def _flush_assistant_buffer(self) -> None:
        if self.state.assistant_buffer:
            self.state.add_item("assistant", self.state.assistant_buffer)
            self.state.assistant_buffer = ""


def _tool_result_text(result: AgentToolResult) -> str:
    status = "✓" if result.ok else "✗"
    lines = [f"{status} {result.name}"]
    if result.content:
        lines.append(result.content)
    patch = _result_patch(result)
    if patch:
        lines.extend(["", "Patch:", patch])
    return "\n".join(lines)


def _result_patch(result: AgentToolResult) -> str | None:
    if result.name != "edit" or not result.ok or result.data is None:
        return None
    patch = result.data.get("patch")
    return patch if isinstance(patch, str) and patch.strip() else None
