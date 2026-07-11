"""Chat item rendering for Tau's TUI transcript."""

from __future__ import annotations

from rich.align import Align
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from tau_coding.tui.config import TAU_DARK_THEME, TuiRoleStyle, TuiTheme
from tau_coding.tui.markdown import (
    ThemedMarkdown,
    _has_unclosed_fence,
    _markdown_highlight_style,
    _markdown_inline_code_style,
    _plain_text,
    _render_fenced_body,
)
from tau_coding.tui.state import ChatItem


def render_chat_item(
    item: ChatItem,
    *,
    theme: TuiTheme = TAU_DARK_THEME,
    show_tool_results: bool = False,
) -> RenderableType:
    """Render a chat item as a standalone Toad-inspired transcript block."""
    role_style = _chat_item_role_style(item, theme)
    body = (
        _render_tool_chat_body(
            item,
            body_style=theme.role_styles["tool"].body,
            accent_style=_tool_accent_style(item, theme=theme),
            show_tool_results=show_tool_results,
            syntax_theme=theme.syntax_theme,
            theme=theme,
        )
        if item.role == "tool"
        else _render_chat_body(
            _visible_chat_text(item, show_tool_results=show_tool_results),
            role=item.role,
            body_style=role_style.body,
            syntax_theme=theme.syntax_theme,
            theme=theme,
        )
    )
    table = Table.grid(expand=True)
    table.add_column(width=1, style=role_style.border)
    table.add_column(ratio=1, style=role_style.body)
    table.add_row(
        Align.left(Text("▌", style=role_style.border)),
        Padding(body, (0, 1, 0, 1), style=role_style.body),
    )
    return Padding(table, (1, 1, 1, 0), style=role_style.body)


def _chat_item_role_style(item: ChatItem, theme: TuiTheme) -> TuiRoleStyle:
    if item.role == "tool" and item.tool_result_text:
        if item.tool_result_text.startswith("✓"):
            return TuiRoleStyle(
                border=_tool_success_color(theme),
                body=theme.role_styles["tool"].body,
            )
        if item.tool_result_text.startswith("✗"):
            return TuiRoleStyle(border="#ff4f4f", body=theme.role_styles["tool"].body)
    return theme.role_styles[item.role]


def _tool_accent_style(item: ChatItem, *, theme: TuiTheme) -> str | None:
    if item.role != "tool" or not item.tool_result_text:
        return None
    if item.tool_result_text.startswith("✓"):
        return _tool_success_style(theme)
    if item.tool_result_text.startswith("✗"):
        return _tool_error_style(theme)
    return None


def _tool_success_color(theme: TuiTheme) -> str:
    if theme.name == "tau-light":
        return "#166534"
    return "#9cffb1"


def _tool_success_style(theme: TuiTheme) -> str:
    color = _tool_success_color(theme)
    if theme.name == "tau-light":
        return color
    return f"{color} on #000000"


def _tool_error_style(theme: TuiTheme) -> str:
    if theme.name == "tau-light":
        return theme.role_styles["error"].border
    return "#ff4f4f on #000000"


def _render_tool_chat_body(
    item: ChatItem,
    *,
    body_style: str,
    accent_style: str | None,
    show_tool_results: bool,
    syntax_theme: str,
    theme: TuiTheme,
) -> RenderableType:
    text = _render_tool_invocation(item.text, body_style=body_style, accent_style=accent_style)
    if not show_tool_results or not item.tool_result_text:
        return text

    result_body = _render_chat_body(
        item.tool_result_text,
        role=item.role,
        body_style=body_style,
        syntax_theme=syntax_theme,
        theme=theme,
    )
    return Group(text, Text(""), result_body)


def _render_tool_invocation(text: str, *, body_style: str, accent_style: str | None) -> Text:
    rendered = Text(style=body_style, overflow="fold", no_wrap=False)
    accent_style = accent_style or body_style
    prefix, name, remainder = _split_tool_invocation(text)
    rendered.append(prefix, style=body_style)
    rendered.append(name, style=body_style)
    rendered.append(remainder, style=accent_style)
    return rendered


def _split_tool_invocation(text: str) -> tuple[str, str, str]:
    if text.startswith("→ "):
        rest = text[2:]
        name, separator, remainder = rest.partition(" ")
        return "→ ", name, f"{separator}{remainder}" if separator else ""
    if text.startswith("$ "):
        return "$", "", text[1:]
    name, separator, remainder = text.partition(" ")
    return "", name, f"{separator}{remainder}" if separator else ""


def _visible_chat_text(item: ChatItem, *, show_tool_results: bool) -> str:
    if item.role == "branch_summary":
        if show_tool_results and item.tool_result_text:
            return f"**Branch Summary**\n\n{item.tool_result_text}"
        return item.text
    if item.role == "compaction_summary":
        if show_tool_results and item.tool_result_text:
            return f"**Compaction Summary**\n\n{item.tool_result_text}"
        return item.text
    if item.role not in {"tool", "skill"} or not show_tool_results or not item.tool_result_text:
        return item.text
    return f"{item.text}\n\n{item.tool_result_text}"


def _render_chat_body(
    text: str,
    *,
    role: str,
    body_style: str,
    syntax_theme: str,
    theme: TuiTheme,
) -> RenderableType:
    patch_body = _render_patch_body(
        text,
        body_style=body_style,
        syntax_theme=syntax_theme,
        code_block_background=theme.markdown_code_block_background,
    )
    if patch_body is not None:
        return patch_body
    if role in {"assistant", "thinking", "status"}:
        if _has_unclosed_fence(text):
            return _plain_text(text, body_style=body_style)
        return ThemedMarkdown(
            text,
            style=body_style,
            code_theme=syntax_theme,
            inline_code_theme=syntax_theme,
            heading_style=_markdown_highlight_style(theme),
            inline_code_style=_markdown_inline_code_style(theme),
            link_style=theme.markdown_link,
            bullet_style=theme.markdown_bullet,
            table_border_style=theme.markdown_table_border,
            code_block_background=theme.markdown_code_block_background,
        )
    fenced_body = _render_fenced_body(
        text,
        body_style=body_style,
        syntax_theme=syntax_theme,
        code_block_background=theme.markdown_code_block_background,
    )
    if fenced_body is not None:
        return fenced_body
    if "```" in text:
        return _plain_text(text, body_style=body_style)
    return _plain_text(text, body_style=body_style)


def _render_patch_body(
    text: str,
    *,
    body_style: str,
    syntax_theme: str,
    code_block_background: str,
) -> RenderableType | None:
    marker = "\nPatch:\n"
    if marker not in text:
        return None
    before_patch, patch = text.split(marker, 1)
    if not patch.strip():
        return None
    return Group(
        _plain_text(f"{before_patch}{marker.rstrip()}", body_style=body_style),
        Syntax(
            patch.rstrip("\n"),
            "diff",
            theme=syntax_theme,
            word_wrap=True,
            background_color=code_block_background,
        ),
    )
