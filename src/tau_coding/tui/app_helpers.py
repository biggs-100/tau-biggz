"""Pure helper functions extracted from app.py for Tau TUI."""

from __future__ import annotations

from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Literal

from rich.console import Console, Group
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from tau_agent import AgentEvent, MessageEndEvent
from tau_agent.messages import UserMessage
from tau_coding.commands import CommandRegistry, create_default_command_registry
from tau_coding.credentials import FileCredentialStore
from tau_coding.provider_catalog import ProviderCatalogEntry
from tau_coding.session import CodingSession
from tau_coding.tui.autocomplete import CompletionItem, CompletionOption, CompletionState
from tau_coding.tui.config import TAU_DARK_THEME, TuiKeybindings, TuiTheme
from tau_coding.tui.input import SessionCompletionRecord, _terminal_command_prefix_span
from tau_coding.tui.screens import _named_session_title
from tau_coding.tui.state import TuiState
from tau_coding.tui.widgets import render_completion_suggestions

SIDEBAR_MIN_WIDTH = 96
SIDEBAR_MIN_HEIGHT = 24
ACTIVITY_TICK_SECONDS = 0.15
ACTIVITY_COLOR_FADE_STEPS = 24
ACTIVITY_INDICATOR_HEIGHT = 3
COMPLETION_MAX_VISIBLE_LINES = 16
COMPLETION_INITIAL_TERMINAL_FRACTION = 3
COMPLETION_MIN_TRANSCRIPT_LINES = 4
COMPLETION_WIDGET_CHROME_LINES = 3
NO_STORED_CREDENTIALS_MESSAGE = (
    "No stored credentials to remove. /logout only removes credentials saved by /login; "
    "environment variables and providers.json config are unchanged."
)


def _activity_prompt_border_color(
    theme: TuiTheme,
    *,
    frame: int,
    running: bool,
    shell_mode: bool,
) -> str:
    """Return the prompt border color for the current activity animation frame."""
    del frame, running
    if shell_mode:
        return theme.accent
    return theme.prompt_border


def _render_activity_indicator(theme: TuiTheme, *, frame: int, running: bool) -> Text:
    """Render the prompt prefix, turning Tau into a moving square while running."""
    if not running:
        return Text("τ", style=f"bold {theme.accent}")

    cycle_length = (ACTIVITY_INDICATOR_HEIGHT - 1) * 2
    cycle_position = frame % cycle_length
    active_row = (
        cycle_position
        if cycle_position < ACTIVITY_INDICATOR_HEIGHT
        else cycle_length - cycle_position
    )
    direction = 1 if cycle_position < ACTIVITY_INDICATOR_HEIGHT else -1
    trail_rows = {
        active_row: theme.accent,
        active_row - direction: _blend_hex_colors(
            theme.accent,
            theme.screen_background,
            fraction=0.35,
        ),
        active_row - (direction * 2): _blend_hex_colors(
            theme.accent,
            theme.screen_background,
            fraction=0.65,
        ),
    }

    rendered = Text()
    for row in range(ACTIVITY_INDICATOR_HEIGHT):
        color = trail_rows.get(row)
        if color is None:
            rendered.append(" ")
        else:
            rendered.append("■", style=color)
        if row < ACTIVITY_INDICATOR_HEIGHT - 1:
            rendered.append("\n")
    return rendered


def _is_terminal_command_prompt(text: str) -> bool:
    """Return whether the prompt is currently in terminal-command mode."""
    return _terminal_command_prefix_span(text) is not None


def _should_optimistically_render_prompt(text: str) -> bool:
    """Return whether submitted text can be safely shown before session expansion."""
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("/")


def _is_user_message_end_event(event: AgentEvent) -> bool:
    """Return whether an agent event closes a user message."""
    return isinstance(event, MessageEndEvent) and isinstance(event.message, UserMessage)


def _blend_hex_colors(start: str, end: str, *, fraction: float) -> str:
    """Blend two ``#rrggbb`` colors by ``fraction``."""
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    blended = tuple(
        round(start_channel + (end_channel - start_channel) * fraction)
        for start_channel, end_channel in zip(start_rgb, end_rgb, strict=True)
    )
    return f"#{blended[0]:02x}{blended[1]:02x}{blended[2]:02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected #rrggbb color, got {color!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _completion_visible_line_limit(suggestions: Static) -> int:
    """Return the number of completion render lines that fit in the widget body."""
    if suggestions.size.height > 0:
        return max(min(COMPLETION_MAX_VISIBLE_LINES, suggestions.size.height), 1)
    return COMPLETION_MAX_VISIBLE_LINES


def _visible_completion_state(
    state: CompletionState,
    *,
    max_lines: int,
    width: int | None = None,
) -> CompletionState:
    """Return a completion-state window with the selected item visible."""
    if not state.items or max_lines <= 0:
        return CompletionState()

    selected_line_limit = max(max_lines - 1, 1)
    start = 0
    while start < state.selected_index:
        candidate = CompletionState(
            items=state.items[start:],
            selected_index=state.selected_index - start,
        )
        if _completion_selected_render_line(candidate, width=width) < selected_line_limit:
            break
        start += 1

    end = len(state.items)
    while end > state.selected_index + 1:
        candidate = CompletionState(
            items=state.items[start:end],
            selected_index=state.selected_index - start,
        )
        if _completion_render_line_count(candidate, width=width) <= max_lines:
            break
        end -= 1

    while start < state.selected_index:
        candidate = CompletionState(
            items=state.items[start:end],
            selected_index=state.selected_index - start,
        )
        if _completion_render_line_count(candidate, width=width) <= max_lines:
            break
        start += 1

    return CompletionState(
        items=state.items[start:end],
        selected_index=state.selected_index - start,
    )


def _completion_selected_render_line(state: CompletionState, *, width: int | None = None) -> int:
    """Return the rendered line number for the selected completion item."""
    line = 0
    has_rendered_text = False
    previous_category: str | None = None
    for index, item in enumerate(state.items):
        if item.category != previous_category:
            if has_rendered_text:
                line += 1
            if item.category:
                line += 1
                has_rendered_text = True
            previous_category = item.category
        elif has_rendered_text:
            line += 1
        if index == state.selected_index:
            return line
        line += _completion_item_extra_wrapped_lines(item, width=width)
        has_rendered_text = True
    return line


def _completion_render_line_count(state: CompletionState, *, width: int | None = None) -> int:
    """Return how many lines the completion state renders into."""
    if not state.items:
        return 0
    line_count = 0
    previous_category: str | None = None
    for index, item in enumerate(state.items):
        if item.category != previous_category:
            if index:
                line_count += 1
            if item.category:
                line_count += 1
            previous_category = item.category
        line_count += 1 + _completion_item_extra_wrapped_lines(item, width=width)
    return line_count


def _completion_item_extra_wrapped_lines(
    item: CompletionItem,
    *,
    width: int | None,
) -> int:
    """Return extra rendered lines used when a completion description wraps."""
    if width is None or width <= 0 or not item.description:
        return 0
    output = StringIO()
    console = Console(
        file=output,
        width=width,
        force_terminal=False,
        color_system=None,
        legacy_windows=False,
    )
    console.print(
        render_completion_suggestions(
            CompletionState(items=(item,), selected_index=0),
            theme=TAU_DARK_THEME,
        ),
        end="",
    )
    line_count = len(output.getvalue().splitlines())
    return max(line_count - 1, 0)


def _session_command_registry(session: CodingSession) -> CommandRegistry:
    registry = getattr(session, "command_registry", None)
    if isinstance(registry, CommandRegistry):
        return registry
    return create_default_command_registry()


def _session_options(session: CodingSession) -> tuple[CompletionOption, ...]:
    return tuple(_session_option(record) for record in _session_records(session))


def _session_records(session: CodingSession) -> tuple[SessionCompletionRecord, ...]:
    manager = getattr(session, "session_manager", None)
    if manager is None:
        return ()
    try:
        records = manager.list_sessions(session.cwd)
    except TypeError:
        records = manager.list_sessions()
    return tuple(records)


def _session_option(record: SessionCompletionRecord) -> CompletionOption:
    description_parts = [record.title if record.title else "Untitled session"]
    if record.model:
        description_parts.append(record.model)
    description_parts.append(_short_path(record.cwd))
    return CompletionOption(value=record.id, description=" - ".join(description_parts))


def _short_path(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def _session_header_sub_title(session: CodingSession) -> str:
    """Return the session label shown beside Tau in the TUI header."""
    title = _named_session_title(getattr(session, "session_title", None))
    return title or "Untitled session"


def _subscription_login_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    return tuple(provider for provider in providers if provider.kind == "openai-codex")


def _api_key_login_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    return tuple(provider for provider in providers if provider.kind != "openai-codex")


def _stored_credential_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    credential_store = FileCredentialStore()
    return tuple(
        provider
        for provider in providers
        if provider.credential_name is not None
        and _credential_store_has_entry(credential_store, provider.credential_name)
    )


def _credential_store_has_entry(
    credential_store: FileCredentialStore,
    credential_name: str,
) -> bool:
    return (
        credential_store.get(credential_name) is not None
        or credential_store.get_oauth(credential_name) is not None
    )


def _command_message_uses_transcript(command_text: str) -> bool:
    """Return whether slash-command output should appear inline in the transcript."""
    command_name = command_text.split(maxsplit=1)[0].casefold()
    return command_name in {"/reload", "/system"}


def _command_message_uses_notification(command_text: str, message: str) -> bool:
    """Return whether slash-command output should appear as a notification."""
    command_name = command_text.split(maxsplit=1)[0].casefold()
    return command_name == "/name" and message.startswith("Session renamed: ")


def _command_output_title(command_text: str) -> str:
    command_name = command_text.split(maxsplit=1)[0].removeprefix("/")
    return f"/{command_name or 'help'}"


def _theme_css_variables(theme: TuiTheme) -> dict[str, str]:
    return {
        "tau-screen-background": theme.screen_background,
        "tau-screen-text": theme.screen_text,
        "tau-chrome-background": theme.chrome_background,
        "tau-chrome-text": theme.chrome_text,
        "tau-muted-text": theme.muted_text,
        "tau-sidebar-background": theme.sidebar_background,
        "tau-border": theme.border,
        "tau-transcript-background": theme.transcript_background,
        "tau-prompt-background": theme.prompt_background,
        "tau-prompt-text": theme.prompt_text,
        "tau-prompt-border": theme.prompt_border,
        "tau-autocomplete-background": theme.autocomplete_background,
        "tau-accent": theme.accent,
        "tau-highlight-background": theme.highlight_background,
        "tau-highlight-text": theme.highlight_text,
        "tau-markdown-highlight": theme.markdown_heading,
        "tau-markdown-table-header": theme.markdown_table_header,
        "tau-markdown-table-border": theme.markdown_table_border,
        "tau-markdown-inline-code": theme.markdown_inline_code,
        "tau-markdown-code-block-background": theme.markdown_code_block_background,
        "tau-markdown-link": theme.markdown_link,
        "tau-markdown-bullet": theme.markdown_bullet,
        "footer-background": theme.chrome_background,
        "footer-foreground": theme.chrome_text,
        "footer-description-background": theme.chrome_background,
        "footer-description-foreground": theme.chrome_text,
        "footer-key-background": theme.chrome_background,
        "footer-key-foreground": theme.accent,
        "footer-item-background": theme.chrome_background,
    }


def _render_queued_messages(state: TuiState, *, theme: TuiTheme) -> Group:
    """Render queued prompts stacked above the prompt input."""
    rows: list[Text] = []
    for message in state.queued_steering:
        row = Text("↪ steering · queued: ", style=theme.muted_text)
        row.append(_queued_message_preview(message), style=theme.prompt_text)
        rows.append(row)
    for message in state.queued_follow_up:
        row = Text("↳ follow-up · queued: ", style=theme.muted_text)
        row.append(_queued_message_preview(message), style=theme.prompt_text)
        rows.append(row)
    return Group(*rows)


def _queued_message_preview(message: str) -> str:
    """Return the single-line preview shown above the prompt."""
    lines = message.splitlines()
    return lines[0] if lines else ""


def _prompt_footer_mode(
    state: TuiState,
    completion_state: CompletionState,
) -> Literal["normal", "completion", "running"]:
    if completion_state.items:
        return "completion"
    if state.running:
        return "running"
    return "normal"


def _app_bindings(keybindings: TuiKeybindings) -> list[Binding]:
    return [
        Binding(keybindings.cancel, "cancel", "Cancel"),
        Binding(keybindings.command_palette, "open_command_palette", "Commands"),
        Binding(keybindings.session_picker, "open_session_picker", "Sessions"),
        Binding(keybindings.thinking_cycle, "cycle_thinking", "Thinking"),
        Binding(keybindings.model_cycle, "cycle_model", "Model"),
        Binding(
            keybindings.accept_completion,
            "accept_completion",
            "Complete",
            priority=True,
        ),
        Binding(
            keybindings.queue_follow_up,
            "submit_follow_up",
            "Follow-up",
            priority=True,
        ),
        Binding(
            keybindings.completion_next,
            "completion_next",
            "Next completion",
            priority=True,
        ),
        Binding(
            keybindings.completion_previous,
            "completion_previous",
            "Previous completion",
            priority=True,
        ),
        Binding(keybindings.toggle_tool_results, "toggle_tool_results", "Tool results"),
        Binding(keybindings.toggle_thinking, "toggle_thinking", "Thinking tokens"),
        Binding(keybindings.copy_message, "clear_prompt", "Clear input"),
        Binding(keybindings.quit, "quit", "Quit"),
    ]


def _text_end_location(text: str) -> tuple[int, int]:
    """Return the TextArea cursor location at the end of text."""
    line, _, column_text = text.rpartition("\n")
    return (line.count("\n") + 1 if line else 0, len(column_text))


def _format_prompt_error(exc: BaseException, session: CodingSession) -> str:
    detail = str(exc) or type(exc).__name__
    message = f"Error: {detail}"
    log_path = getattr(session, "last_diagnostic_log_path", None)
    if isinstance(log_path, Path):
        return f"{message}\nLog: {log_path}"
    return message


def _attach_diagnostic_log_path_to_error(state: TuiState, session: CodingSession) -> None:
    log_path = getattr(session, "last_diagnostic_log_path", None)
    if not isinstance(log_path, Path) or state.error is None:
        return
    message = f"Error: {state.error}\nLog: {log_path}"
    state.error = message
    for item in reversed(state.items):
        if item.role == "error":
            item.text = message
            return
    state.add_item("error", message)
