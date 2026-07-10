"""Small Textual widgets for Tau's interactive TUI.

Re-exports symbols from focused sub-modules for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from tau_coding.tui.autocomplete import CompletionState
from tau_coding.tui.chat_item import (
    _chat_item_role_style,
    _render_chat_body,
    _render_patch_body,
    _render_tool_chat_body,
    _render_tool_invocation,
    _split_tool_invocation,
    _tool_accent_style,
    _tool_error_style,
    _tool_success_color,
    _tool_success_style,
    _visible_chat_text,
    render_chat_item,
)
from tau_coding.tui.config import TAU_DARK_THEME, TuiTheme
from tau_coding.tui.markdown import (
    LeftAlignedMarkdownHeading,
    ThemedCodeBlock,
    ThemedMarkdown,
    _append_plain,
    _fence_language,
    _has_unclosed_fence,
    _markdown_highlight_style,
    _markdown_inline_code_style,
    _markdown_theme,
    _plain_text,
    _render_fenced_body,
    _syntax_language,
)
from tau_coding.tui.sidebar import (
    CompactSessionInfo,
    SessionSidebar,
    SessionSummarySource,
    TAU_SIDEBAR_LOGO,
    _bullet_list,
    _compact_token_count,
    _context_file_label,
    _context_file_labels,
    _context_usage,
    _git_branch,
    _short_path,
    _sidebar_section,
    _sidebar_separator,
    _thinking_level,
    render_compact_session_info,
    render_session_sidebar,
)
from tau_coding.tui.state import ChatItem, TuiState
from tau_coding.tui.transcript import (
    StreamingTranscriptMessageWidget,
    TauMarkdownBlock,
    ThemedMarkdownWidget,
    TranscriptLine,
    TranscriptMessageWidget,
    TranscriptView,
    _BORDERLESS_TRANSCRIPT_ROLES,
    _HIDDEN_THINKING_PLACEHOLDER,
    _clip_selection_offset,
    _clip_selection_to_text,
    _escape_plain_markdown_line,
    _extract_text_selection,
    _last_transcript_child_is_hidden_thinking_placeholder,
    _plain_markdown,
    _render_transcript_tool_invocation,
    _split_rich_style_colors,
    _transcript_item_markdown,
    _transcript_plain_body_text,
    _transcript_widget,
    _use_plain_transcript_body,
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
