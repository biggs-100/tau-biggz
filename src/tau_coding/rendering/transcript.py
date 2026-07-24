"""Human-readable streaming transcript renderer."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.text import Text

from tau_agent import (
    AgentEndEvent,
    AgentEvent,
    ErrorEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    RetryEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)

from tau_agent.messages import TextContent
from tau_agent.tools import ToolCall
from tau_coding.tui.state import format_tool_call_block


def _result_text(content: list | str) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.text for b in content if isinstance(b, TextContent))


class TranscriptRenderer:
    """Render assistant deltas live and tool activity to stderr."""

    def __init__(self) -> None:
        self._assistant_started = False
        self._assistant_ended = False
        self._failed = False
        self._console = Console(stderr=True, highlight=False)

    def render(self, event: AgentEvent) -> None:
        """Render one agent event."""
        if isinstance(event, MessageStartEvent):
            self._assistant_started = False
            self._assistant_ended = False
            return

        if isinstance(event, (MessageDeltaEvent, MessageUpdateEvent)):
            self._assistant_started = True
            if hasattr(event, "assistant_message_event") and event.assistant_message_event is not None:
                delta = getattr(event.assistant_message_event, "delta", "")
            else:
                delta = getattr(event, "delta", "")
            typer.echo(delta, nl=False)
            return

        if isinstance(event, ToolExecutionStartEvent):
            self._ensure_assistant_newline()
            tc = ToolCall(id=event.tool_call_id, name=event.tool_name, arguments=dict(event.args))
            self._console.print(Text(format_tool_call_block(tc), style="cyan"))
            return

        if isinstance(event, ToolExecutionUpdateEvent):
            self._ensure_assistant_newline()
            msg = _result_text(event.partial_result.content) if event.partial_result and event.partial_result.content else ""
            self._console.print(Text(f"… {msg}", style="bright_black"))
            return

        if isinstance(event, RetryEvent):
            self._ensure_assistant_newline()
            self._console.print(Text(f"… {event.message}", style="bright_black"))
            return

        if isinstance(event, ToolExecutionEndEvent):
            if event.result is None:
                return
            status = "✓" if event.result.ok else "✗"
            style = "green" if event.result.ok else "red"
            self._print_tool_line(status, event.result.name or event.tool_name, style=style)
            if event.result.content:
                text = _result_text(event.result.content)
                self._print_tool_content(text)
            return

        if isinstance(event, ErrorEvent):
            if not event.recoverable:
                self._failed = True
            self._ensure_assistant_newline()
            self._console.print(Text(f"Error: {event.message}", style="red"))
            return

        if isinstance(event, MessageEndEvent | AgentEndEvent):
            self._ensure_assistant_newline(final=True)

    def finish(self) -> bool:
        """Return whether the rendered run succeeded."""
        return not self._failed

    def _ensure_assistant_newline(self, *, final: bool = False) -> None:
        if self._assistant_started and not self._assistant_ended:
            typer.echo()
            self._assistant_ended = True
        elif final and not self._assistant_started:
            self._assistant_ended = True

    def _print_tool_line(
        self,
        marker: str,
        name: str,
        detail: str | None = None,
        *,
        style: str,
    ) -> None:
        line = Text()
        line.append(marker, style=style)
        line.append(f" {name}", style=style)
        if detail:
            line.append(f" {detail}", style="bright_black")
        self._console.print(line)

    def _print_tool_content(self, content: str) -> None:
        for line in content.splitlines() or [""]:
            self._console.print(Text(f"  {line}", style="white"))
