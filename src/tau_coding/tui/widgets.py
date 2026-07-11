"""Small Textual widgets for Tau's interactive TUI.

Re-exports symbols from focused sub-modules for backward compatibility.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from tau_coding.tui.autocomplete import CompletionState
from tau_coding.tui.chat_item import (
    render_chat_item,
)
from tau_coding.tui.config import TAU_DARK_THEME, TuiTheme
from tau_coding.tui.markdown import (
    LeftAlignedMarkdownHeading,
    ThemedCodeBlock,
    ThemedMarkdown,
    _syntax_language,  # noqa: F401 — re-exported for tests
)
from tau_coding.tui.sidebar import (
    CompactSessionInfo,
    SessionSidebar,
    _compact_token_count,  # noqa: F401 — re-exported for tests
    render_compact_session_info,
    render_session_sidebar,
)
from tau_coding.tui.transcript import (
    StreamingTranscriptMessageWidget,
    TauMarkdownBlock,
    ThemedMarkdownWidget,
    TranscriptLine,
    TranscriptMessageWidget,
    TranscriptView,
    _split_rich_style_colors,  # noqa: F401 — re-exported for tests
    _transcript_plain_body_text,  # noqa: F401 — re-exported for tests
    transcript_item_selection_text,
)

__all__ = [
    # Classes
    "CompactSessionInfo",
    "LeftAlignedMarkdownHeading",
    "SessionSidebar",
    "StreamingTranscriptMessageWidget",
    "TauMarkdownBlock",
    "ThemedCodeBlock",
    "ThemedMarkdown",
    "ThemedMarkdownWidget",
    "TranscriptLine",
    "TranscriptMessageWidget",
    "TranscriptView",
    # Public functions
    "render_chat_item",
    "render_compact_session_info",
    "render_completion_suggestions",
    "render_session_sidebar",
    "transcript_item_selection_text",
]


def render_completion_suggestions(
    state: CompletionState,
    *,
    theme: TuiTheme = TAU_DARK_THEME,
) -> RenderableType:
    """Render prompt completion suggestions in aligned command/description columns."""
    table = Table.grid(expand=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)

    previous_category: str | None = None
    for index, item in enumerate(state.items):
        if item.category != previous_category:
            if index:
                table.add_row(Text(""), Text(""))
            if item.category:
                table.add_row(Text(item.category, style=theme.completion_description), Text(""))
            previous_category = item.category

        selected = index == state.selected_index
        prefix = "› " if selected else "  "
        style = theme.completion_selected if selected else theme.prompt_text
        description_style = (
            theme.completion_selected_description if selected else theme.completion_description
        )
        command = Text(prefix, style=style)
        command.append(item.display, style=style)
        command.append("  ", style=style)
        table.add_row(command, Text(item.description or "", style=description_style))
    return table
