"""Tests for Rich Markdown rendering helpers in tau_coding.tui.markdown."""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.text import Text

from tau_coding.tui.markdown import (
    _append_plain,
    _fence_language,
    _has_unclosed_fence,
    _plain_text,
    _render_fenced_body,
    _syntax_language,
)

# ---------------------------------------------------------------------------
# _plain_text
# ---------------------------------------------------------------------------


def test_plain_text_applies_body_style() -> None:
    result = _plain_text("hello", body_style="bold red")
    assert isinstance(result, Text)
    assert result.plain == "hello"
    assert str(result.style) == "bold red"


def test_plain_text_has_fold_overflow() -> None:
    result = _plain_text("long content", body_style="#cbd5e1")
    assert result.overflow == "fold"
    assert result.no_wrap is False


# ---------------------------------------------------------------------------
# _append_plain
# ---------------------------------------------------------------------------


def test_append_plain_empty_text_does_nothing() -> None:
    renderables: list = []
    _append_plain(renderables, "", body_style="default")
    assert renderables == []


def test_append_plain_appends_text_to_renderables() -> None:
    renderables: list = []
    _append_plain(renderables, "content", body_style="default")
    assert len(renderables) == 1
    assert isinstance(renderables[0], Text)
    assert renderables[0].plain == "content"


def test_append_plain_strips_trailing_newline() -> None:
    renderables: list = []
    _append_plain(renderables, "line\n", body_style="default")
    assert renderables[0].plain == "line"


# ---------------------------------------------------------------------------
# _fence_language
# ---------------------------------------------------------------------------


def test_fence_language_extracts_word() -> None:
    assert _fence_language("python") == "python"


def test_fence_language_ignores_extra_tokens() -> None:
    assert _fence_language("python 3.12") == "python"


def test_fence_language_strips_whitespace() -> None:
    assert _fence_language("  python  ") == "python"


def test_fence_language_empty_returns_text() -> None:
    assert _fence_language("") == "text"


def test_fence_language_whitespace_only_returns_text() -> None:
    assert _fence_language("   ") == "text"


# ---------------------------------------------------------------------------
# _syntax_language
# ---------------------------------------------------------------------------


def test_syntax_language_valid_lexer() -> None:
    assert _syntax_language("python") == "python"


def test_syntax_language_another_valid_lexer() -> None:
    assert _syntax_language("javascript") == "javascript"


def test_syntax_language_invalid_falls_back_to_text() -> None:
    assert _syntax_language("definitely-not-a-lexer") == "text"


def test_syntax_language_empty_returns_text() -> None:
    assert _syntax_language("") == "text"


def test_syntax_language_text_returns_immediately_no_pygments_call() -> None:
    """The 'text' path hits the early return before get_lexer_by_name."""
    assert _syntax_language("text") == "text"


# ---------------------------------------------------------------------------
# _has_unclosed_fence
# ---------------------------------------------------------------------------


def test_has_unclosed_fence_no_fences() -> None:
    assert _has_unclosed_fence("plain text") is False


def test_has_unclosed_fence_one_fence_is_unclosed() -> None:
    assert _has_unclosed_fence("```python") is True


def test_has_unclosed_fence_two_fences_is_closed() -> None:
    assert _has_unclosed_fence("```python\ncode\n```") is False


def test_has_unclosed_fence_three_fences_is_unclosed() -> None:
    assert _has_unclosed_fence("```\na\n```\nb\n```") is True


def test_has_unclosed_fence_even_count_is_closed() -> None:
    assert _has_unclosed_fence("```\n```\n```\n```") is False


# ---------------------------------------------------------------------------
# _render_fenced_body
# ---------------------------------------------------------------------------


def test_render_fenced_body_no_fences_returns_none() -> None:
    result = _render_fenced_body(
        "plain text without fences",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is None


def test_render_fenced_body_single_backtick_returns_none() -> None:
    """Triple-backtick check means inline backtick code passes through."""
    result = _render_fenced_body(
        "use `code` here",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is None


def test_render_fenced_body_well_formed_fence() -> None:
    result = _render_fenced_body(
        "```python\nprint('hi')\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80, color_system="truecolor")
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "print" in output
    assert "hi" in output
    assert "```" not in output


def test_render_fenced_body_leading_text_before_fence() -> None:
    result = _render_fenced_body(
        "intro text\n```python\nx = 1\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "intro text" in output
    assert "x = 1" in output
    assert "```" not in output


def test_render_fenced_body_unclosed_fence_returns_none() -> None:
    result = _render_fenced_body(
        "```python\nprint('hi')",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is None


def test_render_fenced_body_fence_not_at_line_start_returns_none() -> None:
    """If ``` does not start at column 0, the fence is malformed."""
    result = _render_fenced_body(
        "text```python\ncode\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is None


def test_render_fenced_body_fence_without_newline_after_returns_none() -> None:
    """A bare ``` with no newline after it is not a valid fence."""
    result = _render_fenced_body(
        "```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is None


def test_render_fenced_body_no_closing_newline_before_closing_fence() -> None:
    """Closing ``` at end of string (no trailing newline) is valid."""
    result = _render_fenced_body(
        "```python\ndef f(): pass\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None
    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]
    assert "def f(): pass" in output


def test_render_fenced_body_multiple_fences() -> None:
    result = _render_fenced_body(
        "a\n```python\nx=1\n```\nb\n```js\ny=2\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "a" in output
    assert "b" in output
    assert "x=1" in output
    assert "y=2" in output
    assert "```" not in output


def test_render_fenced_body_invalid_language_falls_back() -> None:
    result = _render_fenced_body(
        "```not-a-real-lexer\ncontent\n```",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "content" in output


def test_render_fenced_body_only_plain_text_after_fence_scan() -> None:
    """When text has ``` but no valid fence, plain text fallback."""
    result = _render_fenced_body(
        "text\n```\ncode\n```\nmore text",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "text" in output
    assert "more text" in output
    assert "code" in output
    assert "```" not in output


def test_render_fenced_body_with_trailing_content_after_last_fence() -> None:
    result = _render_fenced_body(
        "```python\nprint('hi')\n```\ntrailing",
        body_style="default",
        syntax_theme="monokai",
        code_block_background="#1e1e2e",
    )
    assert result is not None

    console = Console(file=StringIO(), width=80)
    console.print(result)
    output = console.file.getvalue()  # type: ignore[union-attr]

    assert "trailing" in output
