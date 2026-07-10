"""Rich Markdown rendering helpers for Tau's TUI."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pygments.lexers import get_lexer_by_name  # type: ignore[import-untyped]
from pygments.util import ClassNotFound  # type: ignore[import-untyped]
from rich.console import Console, Group, RenderableType
from rich.markdown import CodeBlock, Heading, Markdown
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme

from tau_coding.tui.config import TuiTheme


class ThemedCodeBlock(CodeBlock):
    """Rich Markdown code block with Tau's themed background color."""

    @classmethod
    def create(cls, markdown: Markdown, token: Any) -> ThemedCodeBlock:
        node_info = token.info or ""
        lexer_name = node_info.partition(" ")[0]
        code_block_background = getattr(markdown, "code_block_background", "default")
        return cls(lexer_name or "text", markdown.code_theme, code_block_background)

    def __init__(self, lexer_name: str, theme: str, code_block_background: str) -> None:
        super().__init__(lexer_name, theme)
        self.code_block_background = code_block_background

    def __rich_console__(self, console: Console, options: Any) -> Any:
        code = str(self.text).rstrip()
        yield Syntax(
            code,
            self.lexer_name,
            theme=self.theme,
            word_wrap=True,
            padding=1,
            background_color=self.code_block_background,
        )


class LeftAlignedMarkdownHeading(Heading):
    """Rich Markdown heading that keeps all heading levels left-aligned."""

    LEVEL_ALIGN: ClassVar[dict[str, Literal["default", "left", "center", "right", "full"]]] = {
        "h1": "left",
        "h2": "left",
        "h3": "left",
        "h4": "left",
        "h5": "left",
        "h6": "left",
    }


class ThemedMarkdown(Markdown):
    """Markdown renderer with Tau's softer heading/accent colors."""

    elements = {
        **Markdown.elements,
        "heading_open": LeftAlignedMarkdownHeading,
        "fence": ThemedCodeBlock,
        "code_block": ThemedCodeBlock,
    }

    def __init__(
        self,
        markup: str,
        *,
        heading_style: str,
        inline_code_style: str,
        link_style: str,
        bullet_style: str,
        table_border_style: str,
        code_block_background: str,
        code_theme: str,
        inline_code_theme: str,
        style: str = "none",
    ) -> None:
        super().__init__(
            markup,
            style=style,
            code_theme=code_theme,
            inline_code_theme=inline_code_theme,
        )
        self.heading_style = heading_style
        self.inline_code_style = inline_code_style
        self.link_style = link_style
        self.bullet_style = bullet_style
        self.table_border_style = table_border_style
        self.code_block_background = code_block_background

    def __rich_console__(self, console: Console, options: Any) -> Any:
        with console.use_theme(
            _markdown_theme(
                self.heading_style,
                self.inline_code_style,
                self.link_style,
                self.bullet_style,
                self.table_border_style,
                self.code_block_background,
            )
        ):
            yield from super().__rich_console__(console, options)


def _markdown_highlight_style(theme: TuiTheme) -> str:
    return theme.markdown_heading


def _markdown_inline_code_style(theme: TuiTheme) -> str:
    return theme.markdown_inline_code


def _markdown_theme(
    heading_style: str,
    inline_code_style: str,
    link_style: str,
    bullet_style: str,
    table_border_style: str,
    code_block_background: str,
) -> Theme:
    highlight = Style.parse(heading_style)
    inline_code = Style.parse(inline_code_style)
    link = Style.parse(link_style)
    bullet = Style.parse(bullet_style)
    table_border = Style.parse(table_border_style)
    code_block = Style(bgcolor=code_block_background)
    return Theme(
        {
            "markdown.h1": highlight + Style(bold=True),
            "markdown.h2": highlight + Style(bold=True),
            "markdown.h3": highlight + Style(bold=True),
            "markdown.h4": highlight + Style(bold=True),
            "markdown.h5": highlight + Style(bold=True),
            "markdown.h6": highlight + Style(bold=True),
            "markdown.item.bullet": bullet,
            "markdown.item.number": bullet,
            "markdown.block_quote": highlight,
            "markdown.link": link,
            "markdown.link_url": link,
            "markdown.table.header": highlight + Style(bold=True),
            "markdown.table.border": table_border,
            "markdown.code": inline_code,
            "markdown.code_block": code_block,
        }
    )


def _render_fenced_body(
    text: str,
    *,
    body_style: str,
    syntax_theme: str,
    code_block_background: str,
) -> RenderableType | None:
    if "```" not in text:
        return None

    renderables: list[RenderableType] = []
    cursor = 0
    while cursor < len(text):
        fence_start = text.find("```", cursor)
        if fence_start == -1:
            _append_plain(renderables, text[cursor:], body_style=body_style)
            break

        line_start = text.rfind("\n", 0, fence_start) + 1
        if line_start != fence_start:
            return None

        fence_line_end = text.find("\n", fence_start)
        if fence_line_end == -1:
            return None
        closing_start = text.find("\n```", fence_line_end + 1)
        if closing_start == -1:
            return None

        _append_plain(renderables, text[cursor:fence_start], body_style=body_style)
        language = _syntax_language(text[fence_start + 3 : fence_line_end])
        code = text[fence_line_end + 1 : closing_start]
        renderables.append(
            Syntax(
                code.rstrip("\n"),
                language,
                theme=syntax_theme,
                word_wrap=True,
                background_color=code_block_background,
            )
        )
        closing_line_end = text.find("\n", closing_start + 1)
        cursor = len(text) if closing_line_end == -1 else closing_line_end + 1

    return Group(*renderables) if renderables else None


def _append_plain(
    renderables: list[RenderableType],
    text: str,
    *,
    body_style: str,
) -> None:
    if text:
        renderables.append(_plain_text(text.rstrip("\n"), body_style=body_style))


def _plain_text(text: str, *, body_style: str) -> Text:
    return Text(text, style=body_style, overflow="fold", no_wrap=False)


def _has_unclosed_fence(text: str) -> bool:
    fence_count = sum(1 for line in text.splitlines() if line.startswith("```"))
    return fence_count % 2 == 1


def _fence_language(raw: str) -> str:
    language = raw.strip().split(maxsplit=1)[0] if raw.strip() else ""
    return language or "text"


def _syntax_language(raw: str) -> str:
    language = _fence_language(raw)
    if language == "text":
        return language
    try:
        get_lexer_by_name(language)
    except ClassNotFound:
        return "text"
    return language
