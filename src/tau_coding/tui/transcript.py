"""Transcript widgets for Tau's TUI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from rich.console import Group, RenderableType
from rich.style import Style
from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.content import Style as TextualStyle  # type: ignore[attr-defined]
from textual.events import Resize
from textual.geometry import Offset
from textual.selection import Selection
from textual.widget import Widget
from textual.widgets import Markdown as TextualMarkdown
from textual.widgets import Static
from textual.widgets.markdown import MarkdownBlock, MarkdownStream

from tau_coding.tui.chat_item import (
    _chat_item_role_style,
    _render_patch_body,
    _split_tool_invocation,
    _tool_accent_style,
    _visible_chat_text,
)
from tau_coding.tui.config import TAU_DARK_THEME, TuiTheme
from tau_coding.tui.state import ChatItem, TuiState


@dataclass(frozen=True, slots=True)
class TranscriptLine:
    """Plain transcript line used by compatibility inspection helpers."""

    text: str


class TauMarkdownBlock(MarkdownBlock):
    """Markdown block that applies Tau's themed inline link color."""

    @property
    def allow_select(self) -> bool:
        """Only allow native selection once Textual has mounted the block.

        Textual may hit freshly-created Markdown blocks during a mouse-down before
        they have a parent. Its selection startup path assumes selected content
        widgets have a parent container, so an unmounted selectable Markdown block
        can crash with ``container is None``.
        """
        return self.parent is not None and super().allow_select

    def _token_to_content(self, token: Any) -> Any:
        content = super()._token_to_content(token)
        markdown = self._markdown
        if not isinstance(markdown, ThemedMarkdownWidget):
            return content
        link_style = TextualStyle.parse(markdown.tau_link_style)
        spans = []
        for span in content.spans:
            style = span.style
            if isinstance(style, TextualStyle) and "@click" in style.meta:
                style = link_style + style
            spans.append(type(span)(span.start, span.end, style))
        return type(content)(content.plain, spans=spans)


class ThemedMarkdownWidget(TextualMarkdown):
    """Textual Markdown widget reserved for Tau transcript streaming."""

    BLOCKS = {**TextualMarkdown.BLOCKS, "paragraph_open": TauMarkdownBlock}

    DEFAULT_CSS = """
    ThemedMarkdownWidget MarkdownH1,
    ThemedMarkdownWidget MarkdownH2,
    ThemedMarkdownWidget MarkdownH3,
    ThemedMarkdownWidget MarkdownH4,
    ThemedMarkdownWidget MarkdownH5,
    ThemedMarkdownWidget MarkdownH6 {
        color: $tau-markdown-highlight;
        content-align: left middle;
        text-style: bold;
    }

    ThemedMarkdownWidget MarkdownBlock > .code_inline {
        color: $tau-markdown-inline-code !important;
        background: transparent !important;
    }

    ThemedMarkdownWidget MarkdownBullet {
        color: $tau-markdown-bullet;
    }

    ThemedMarkdownWidget MarkdownFence {
        background: $tau-markdown-code-block-background;
        overflow-x: auto;
        scrollbar-size-horizontal: 1;
    }

    ThemedMarkdownWidget MarkdownTableContent {
        keyline: thin $tau-markdown-table-border;
    }

    ThemedMarkdownWidget MarkdownTableContent > .header {
        color: $tau-markdown-table-header;
        text-style: bold;
    }
    """

    def __init__(
        self,
        markdown: str | None = None,
        *,
        theme: TuiTheme,
        classes: str | None = None,
    ) -> None:
        self.tau_link_style = theme.markdown_link
        super().__init__(markdown, classes=classes)


# Roles rendered as free-flowing text with no left accent or role background,
# matching how they appear while streaming.
_BORDERLESS_TRANSCRIPT_ROLES = frozenset({"assistant", "thinking"})
_HIDDEN_THINKING_PLACEHOLDER = "Thinking… Press Ctrl+T to show thinking tokens."


class TranscriptMessageWidget(Horizontal):
    """One selectable transcript message rendered as a full-height role block."""

    DEFAULT_CSS = """
    TranscriptMessageWidget {
        width: 1fr;
        height: auto;
        margin: 1 1 2 0;
    }

    TranscriptMessageWidget > .transcript-message-body {
        width: 1fr;
        height: auto;
        padding: 0 1 0 1;
    }

    TranscriptMessageWidget > .transcript-markdown-body > MarkdownParagraph {
        margin: 0 0 1 0;
    }

    """

    def __init__(
        self,
        item: ChatItem,
        *,
        theme: TuiTheme,
        show_tool_results: bool,
    ) -> None:
        self.item = item
        self.selection_text = transcript_item_selection_text(
            item,
            show_tool_results=show_tool_results,
        )
        self._markdown_text = _transcript_item_markdown(
            item,
            show_tool_results=show_tool_results,
        )
        self._theme = theme
        self._role_style = _chat_item_role_style(item, theme)
        super().__init__(classes="transcript-message")
        foreground, background = _split_rich_style_colors(self._role_style.body)
        self._body_foreground = foreground
        if item.role in _BORDERLESS_TRANSCRIPT_ROLES:
            self._body_background = None
        else:
            self._body_background = background
            self.styles.border_left = ("tall", self._role_style.border)
            if background:
                self.styles.background = background

    def compose(self) -> Any:
        yield self._body_widget()

    def _body_widget(self) -> Static | ThemedMarkdownWidget:
        body: Static | ThemedMarkdownWidget
        if _use_plain_transcript_body(self.item):
            body = Static(
                _transcript_plain_body_text(
                    self.item,
                    text=self.selection_text,
                    body_style=self._role_style.body,
                    theme=self._theme,
                ),
                expand=True,
                shrink=True,
                markup=False,
                classes="transcript-message-body transcript-plain-body",
            )
        else:
            body = ThemedMarkdownWidget(
                self._markdown_text,
                theme=self._theme,
                classes="transcript-message-body transcript-markdown-body",
            )
        if self._body_foreground:
            body.styles.color = self._body_foreground
        if self._body_background:
            body.styles.background = self._body_background
        return body

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Return selected plain text from this message, not rendered Markdown markup."""
        selected_text = _extract_text_selection(self.selection_text, selection)
        if not selected_text:
            return None
        return selected_text, "\n"


class StreamingTranscriptMessageWidget(ThemedMarkdownWidget):
    """One assistant or thinking Markdown block that accepts streamed fragments."""

    DEFAULT_CSS = """
    StreamingTranscriptMessageWidget {
        width: 1fr;
        height: auto;
        margin: 1 1 2 1;
        padding: 0 1 0 0;
    }

    StreamingTranscriptMessageWidget > MarkdownParagraph {
        margin: 0 0 1 0;
    }

    StreamingTranscriptMessageWidget.-streaming MarkdownFence {
        overflow-x: hidden;
        scrollbar-size-horizontal: 0;
    }

    StreamingTranscriptMessageWidget.-finalized MarkdownFence {
        overflow-x: auto;
        scrollbar-size-horizontal: 1;
    }
    """

    def __init__(self, item: ChatItem, *, theme: TuiTheme) -> None:
        if item.role not in {"assistant", "thinking"}:
            raise ValueError("Streaming transcript widgets only support assistant/thinking items")
        self.item = item
        self.selection_text = item.text
        self._stream: MarkdownStream | None = None
        self._is_streaming = True
        super().__init__(item.text, theme=theme)
        self.add_class("transcript-message")
        self.add_class("-streaming")
        # Apply the role foreground so streamed text matches the finalized block
        # (e.g. dimmed thinking) instead of shifting color on the next redraw.
        foreground, _ = _split_rich_style_colors(_chat_item_role_style(item, theme).body)
        if foreground:
            self.styles.color = foreground

    @property
    def stream(self) -> MarkdownStream:
        if self._stream is None:
            self._stream = self.get_stream(self)
        return self._stream

    async def append_fragment(self, fragment: str) -> None:
        """Append streamed markdown without reparsing the full accumulated message."""
        if not fragment:
            return
        self.item.text += fragment
        self.selection_text += fragment
        await self.stream.write(fragment)

    async def _stop_stream(self) -> None:
        """Stop the Textual markdown stream, flushing pending fragments first."""
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        await stream.stop()

    async def replace_text(self, text: str) -> None:
        """Replace the current markdown text, usually with corrected final content."""
        await self._stop_stream()
        self.item.text = text
        self.selection_text = text
        await self.update(text)

    async def finalize(self, text: str | None = None) -> None:
        """Mark the streamed message complete and restore finalized Markdown chrome."""
        if text is not None and text != self.selection_text:
            await self.replace_text(text)
        else:
            if text is not None:
                self.item.text = text
                self.selection_text = text
            await self._stop_stream()
        self._is_streaming = False
        self.remove_class("-streaming")
        self.add_class("-finalized")

    async def on_unmount(self) -> None:
        """Cancel the markdown stream task if the widget is removed mid-stream."""
        await self._stop_stream()

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Return selected text from this streamed message block."""
        selected_text = _extract_text_selection(self.selection_text, selection)
        if not selected_text:
            return None
        return selected_text, "\n"


class TranscriptView(VerticalScroll):
    """Scrollable transcript view backed by individual selectable message widgets."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for legacy_option in ("wrap", "highlight", "markup"):
            kwargs.pop(legacy_option, None)
        min_width = kwargs.pop("min_width", None)
        super().__init__(*args, **kwargs)
        self.min_width = min_width
        if min_width is not None:
            self.styles.min_width = min_width
        self._render_state: TuiState | None = None
        self._render_theme: TuiTheme = TAU_DARK_THEME
        self._last_render_width = 0
        self._active_assistant_widget: StreamingTranscriptMessageWidget | None = None
        self._active_thinking_widget: StreamingTranscriptMessageWidget | None = None
        self._hidden_thinking_placeholder_visible = False
        self._follow_output = True
        self._follow_scroll_pending = False

    def on_mount(self) -> None:
        """Follow new transcript content until the user scrolls away."""
        self.follow_output()

    def follow_output(self) -> None:
        """Return to follow mode for a user-driven turn or explicit jump to bottom."""
        self._follow_output = True
        self.anchor(True)
        self._request_follow_scroll(force=True)

    def _request_follow_scroll(self, *, force: bool = False) -> None:
        """Scroll to the bottom after layout if follow mode is still active."""
        if self._follow_scroll_pending and not force:
            return
        self._follow_scroll_pending = True

        def scroll_if_still_following() -> None:
            self._follow_scroll_pending = False
            if force or self._follow_output or self.is_vertical_scroll_end:
                self.scroll_end(animate=False, immediate=True)

        self.call_after_refresh(scroll_if_still_following)

    @property
    def _should_follow_output(self) -> bool:
        """Return whether new content should keep the viewport pinned to the bottom."""
        return self._follow_output or self.is_vertical_scroll_end

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Track whether user scrollback has opted out of transcript following."""
        super().watch_scroll_y(old_value, new_value)
        if new_value < old_value:
            self._follow_output = False
        elif new_value >= self.max_scroll_y:
            self._follow_output = True

    async def _finalize_active_thinking_message(self) -> None:
        """Stop streaming for a completed thinking block before another block starts."""
        widget = self._active_thinking_widget
        if widget is None:
            return
        await widget.finalize()
        self._active_thinking_widget = None

    async def _finalize_active_assistant_message(self) -> None:
        """Stop streaming for a completed assistant block before another block starts."""
        widget = self._active_assistant_widget
        if widget is None:
            return
        await widget.finalize()
        self._active_assistant_widget = None

    def update_from_state(
        self,
        state: TuiState,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
    ) -> None:
        """Redraw the transcript from display state."""
        self._render_state = state
        self._render_theme = theme
        self._redraw(scroll_end=self._should_follow_output)

    def update_thinking_visibility(
        self,
        state: TuiState,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
    ) -> None:
        """Update only thinking-token widgets after visibility changes."""
        self._render_state = state
        self._render_theme = theme
        should_follow = self._should_follow_output
        previous_scroll_y = self.scroll_y

        message_children = [
            child
            for child in self.children
            if isinstance(child, TranscriptMessageWidget | StreamingTranscriptMessageWidget)
        ]
        thinking_children = [child for child in message_children if child.item.role == "thinking"]
        if thinking_children:
            self.remove_children(thinking_children)

        non_thinking_children = [
            child for child in message_children if child.item.role != "thinking"
        ]
        non_thinking_index = 0
        pending_thinking: list[TranscriptMessageWidget] = []
        hidden_thinking_placeholder = False

        def flush_pending(
            *, before: TranscriptMessageWidget | StreamingTranscriptMessageWidget | None
        ) -> None:
            nonlocal pending_thinking
            for widget in pending_thinking:
                self.mount(widget, before=before)
            pending_thinking = []

        for item in state.items:
            if item.role == "thinking":
                if state.show_thinking:
                    pending_thinking.append(
                        TranscriptMessageWidget(
                            item,
                            theme=theme,
                            show_tool_results=state.show_tool_results,
                        )
                    )
                elif not hidden_thinking_placeholder:
                    pending_thinking.append(
                        TranscriptMessageWidget(
                            ChatItem(role="thinking", text=_HIDDEN_THINKING_PLACEHOLDER),
                            theme=theme,
                            show_tool_results=state.show_tool_results,
                        )
                    )
                    hidden_thinking_placeholder = True
                continue

            hidden_thinking_placeholder = False
            target = None
            while non_thinking_index < len(non_thinking_children):
                candidate = non_thinking_children[non_thinking_index]
                non_thinking_index += 1
                if candidate.item is item:
                    target = candidate
                    break
            if target is not None:
                flush_pending(before=target)

        tail_child = (
            non_thinking_children[non_thinking_index]
            if non_thinking_index < len(non_thinking_children)
            else None
        )
        flush_pending(before=tail_child)
        self._active_thinking_widget = None
        self._hidden_thinking_placeholder_visible = (
            _last_transcript_child_is_hidden_thinking_placeholder(self.children)
        )
        self._last_render_width = self.scrollable_content_region.width
        self.refresh(layout=True)
        if should_follow:
            self._request_follow_scroll()
        else:
            self.call_after_refresh(
                lambda: self.scroll_to(y=previous_scroll_y, animate=False, immediate=True)
            )

    def on_resize(self, event: Resize) -> None:
        """Re-render transcript entries when the terminal width changes."""
        del event
        if self._render_state is None:
            return
        width = self.scrollable_content_region.width
        if width <= 0 or width == self._last_render_width:
            return
        was_at_end = self.is_vertical_scroll_end
        self._redraw(scroll_end=was_at_end)
        self.scroll_to(x=0, animate=False, immediate=True)

    def _redraw(self, *, scroll_end: bool) -> None:
        state = self._render_state
        if state is None:
            return
        theme = self._render_theme
        self._last_render_width = self.scrollable_content_region.width
        self.remove_children(
            [
                child
                for child in self.children
                if isinstance(child, TranscriptMessageWidget | StreamingTranscriptMessageWidget)
            ]
        )
        self._active_assistant_widget = None
        self._active_thinking_widget = None
        self._hidden_thinking_placeholder_visible = False
        hidden_thinking_placeholder = False
        for item in state.items:
            if item.role == "thinking" and not state.show_thinking:
                if not hidden_thinking_placeholder:
                    self.mount(
                        TranscriptMessageWidget(
                            ChatItem(
                                role="thinking",
                                text=_HIDDEN_THINKING_PLACEHOLDER,
                            ),
                            theme=theme,
                            show_tool_results=state.show_tool_results,
                        )
                    )
                    hidden_thinking_placeholder = True
                continue
            hidden_thinking_placeholder = False
            self.mount(
                TranscriptMessageWidget(
                    item,
                    theme=theme,
                    show_tool_results=state.show_tool_results or item.always_show_tool_result,
                )
            )
        if state.assistant_buffer:
            self.mount(
                TranscriptMessageWidget(
                    ChatItem(role="assistant", text=state.assistant_buffer),
                    theme=theme,
                    show_tool_results=state.show_tool_results,
                )
            )
        self.refresh(layout=True)
        if scroll_end:
            self._request_follow_scroll()

    async def append_item(
        self,
        item: ChatItem,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
        show_tool_results: bool = False,
        scroll_end: bool = False,
    ) -> TranscriptMessageWidget | StreamingTranscriptMessageWidget:
        """Append one transcript item without rebuilding previous blocks."""
        should_follow = self._should_follow_output if not scroll_end else True
        await self._finalize_active_assistant_message()
        await self._finalize_active_thinking_message()
        self._render_theme = theme
        widget = _transcript_widget(
            item,
            theme=theme,
            show_tool_results=show_tool_results,
        )
        await self.mount(widget)
        self._active_assistant_widget = None
        self._active_thinking_widget = None
        self._hidden_thinking_placeholder_visible = False
        self._last_render_width = self.scrollable_content_region.width
        self.refresh(layout=True)
        if should_follow:
            self._request_follow_scroll(force=scroll_end)
        return widget

    async def start_assistant_message(
        self,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
        scroll_end: bool = False,
    ) -> StreamingTranscriptMessageWidget:
        """Create the active assistant message widget if needed."""
        if self._active_assistant_widget is not None:
            return self._active_assistant_widget
        await self._finalize_active_thinking_message()
        should_follow = self._should_follow_output if not scroll_end else True
        widget = StreamingTranscriptMessageWidget(
            ChatItem(role="assistant", text=""),
            theme=theme,
        )
        self._render_theme = theme
        await self.mount(widget)
        self._active_assistant_widget = widget
        self._last_render_width = self.scrollable_content_region.width
        if should_follow:
            self._request_follow_scroll(force=scroll_end)
        return widget

    async def append_assistant_delta(
        self,
        delta: str,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
        scroll_end: bool = False,
    ) -> None:
        """Append streamed assistant text to the active message widget."""
        should_follow = self._should_follow_output if not scroll_end else True
        widget = await self.start_assistant_message(theme=theme, scroll_end=scroll_end)
        await widget.append_fragment(delta)
        if should_follow:
            self._request_follow_scroll(force=scroll_end)

    async def append_thinking_delta(
        self,
        delta: str,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
        show_thinking: bool,
        scroll_end: bool = False,
    ) -> None:
        """Append streamed thinking text or one hidden-thinking placeholder."""
        should_follow = self._should_follow_output if not scroll_end else True
        if not show_thinking:
            if self._hidden_thinking_placeholder_visible:
                return
            widget = TranscriptMessageWidget(
                ChatItem(
                    role="thinking",
                    text=_HIDDEN_THINKING_PLACEHOLDER,
                ),
                theme=theme,
                show_tool_results=False,
            )
            await self.mount(widget, before=self._active_assistant_widget)
            self._active_thinking_widget = None
            self._hidden_thinking_placeholder_visible = True
            self._last_render_width = self.scrollable_content_region.width
            self.refresh(layout=True)
            if should_follow:
                self._request_follow_scroll(force=scroll_end)
            return
        self._hidden_thinking_placeholder_visible = False
        if self._active_thinking_widget is None:
            self._active_thinking_widget = StreamingTranscriptMessageWidget(
                ChatItem(role="thinking", text=""),
                theme=theme,
            )
            await self.mount(
                self._active_thinking_widget,
                before=self._active_assistant_widget,
            )
        await self._active_thinking_widget.append_fragment(delta)
        if should_follow:
            self._request_follow_scroll(force=scroll_end)

    async def finish_assistant_message(self, text: str | None = None) -> None:
        """Finalize the active assistant widget after the provider sends the full message."""
        widget = self._active_assistant_widget
        if widget is None:
            if text:
                await self.append_item(
                    ChatItem(role="assistant", text=text),
                    theme=self._render_theme,
                )
            return
        await widget.finalize(text)
        self._active_assistant_widget = None
        self._hidden_thinking_placeholder_visible = False

    @property
    def lines(self) -> tuple[TranscriptLine, ...]:
        """Compatibility text view for tests and lightweight transcript inspection."""
        messages = [
            child
            for child in self.children
            if isinstance(child, TranscriptMessageWidget | StreamingTranscriptMessageWidget)
        ]
        return tuple(
            TranscriptLine(line)
            for message in messages
            for line in message.selection_text.splitlines()
        )


def _last_transcript_child_is_hidden_thinking_placeholder(children: Sequence[Widget]) -> bool:
    for child in reversed(children):
        if isinstance(child, TranscriptMessageWidget | StreamingTranscriptMessageWidget):
            return (
                child.item.role == "thinking"
                and child.selection_text == _HIDDEN_THINKING_PLACEHOLDER
            )
    return False


def _transcript_widget(
    item: ChatItem,
    *,
    theme: TuiTheme,
    show_tool_results: bool,
) -> TranscriptMessageWidget | StreamingTranscriptMessageWidget:
    if item.role in {"assistant", "thinking"}:
        return StreamingTranscriptMessageWidget(item, theme=theme)
    return TranscriptMessageWidget(
        item,
        theme=theme,
        show_tool_results=show_tool_results,
    )


def transcript_item_selection_text(
    item: ChatItem,
    *,
    show_tool_results: bool = False,
) -> str:
    """Return the plain text represented by a selectable transcript item."""
    return _visible_chat_text(item, show_tool_results=show_tool_results)


def _split_rich_style_colors(style: str) -> tuple[str | None, str | None]:
    """Split the foreground/background colors from a simple Rich style string."""
    text_style = Style.parse(style)
    foreground = text_style.color.name if text_style.color is not None else None
    background = text_style.bgcolor.name if text_style.bgcolor is not None else None
    return foreground, background


def _use_plain_transcript_body(item: ChatItem) -> bool:
    """Return whether a transcript item can use fast selectable plain text."""
    return item.role in {"user", "tool", "skill", "error"}


def _transcript_plain_body_text(
    item: ChatItem,
    *,
    text: str,
    body_style: str,
    theme: TuiTheme,
) -> RenderableType:
    """Return styled transcript text for selectable plain rows."""
    if item.role != "tool":
        return Text(text, style=body_style, overflow="fold", no_wrap=False)

    invocation, separator, result_text = text.partition("\n\n")
    invocation_text = _render_transcript_tool_invocation(
        invocation,
        body_style=body_style,
        accent_style=_tool_accent_style(item, theme=theme),
    )
    if not separator:
        return invocation_text

    patch_body = _render_patch_body(
        result_text,
        body_style=body_style,
        syntax_theme=theme.syntax_theme,
        code_block_background=theme.markdown_code_block_background,
    )
    if patch_body is not None:
        return Group(invocation_text, Text(""), patch_body)

    rendered = Text(style=body_style, overflow="fold", no_wrap=False)
    rendered.append(invocation_text)
    rendered.append(separator)
    rendered.append(result_text, style=body_style)
    return rendered


def _render_transcript_tool_invocation(
    text: str,
    *,
    body_style: str,
    accent_style: str | None,
) -> Text:
    """Render a selectable tool invocation with status color after the prefix."""
    rendered = Text(style=body_style, overflow="fold", no_wrap=False)
    accent_style = accent_style or body_style
    prefix, name, remainder = _split_tool_invocation(text)
    rendered.append(prefix, style=body_style)
    rendered.append(name, style=accent_style)
    rendered.append(remainder, style=accent_style)
    return rendered


def _transcript_item_markdown(
    item: ChatItem,
    *,
    show_tool_results: bool,
) -> str:
    """Return Markdown for a transcript item using native Textual Markdown blocks."""
    visible_text = _visible_chat_text(item, show_tool_results=show_tool_results)
    if item.role in {"assistant", "thinking", "status", "branch_summary", "compaction_summary"}:
        return visible_text
    return _plain_markdown(visible_text)


def _plain_markdown(text: str) -> str:
    """Represent arbitrary plain text as wrapping Markdown paragraphs."""
    if not text:
        return ""
    return "\n".join(_escape_plain_markdown_line(line) for line in text.splitlines())


def _escape_plain_markdown_line(line: str) -> str:
    """Escape Markdown syntax while preserving plain, wrapping text."""
    escaped = line.replace("\\", "\\\\")
    for character in "`*_{}[]()#+-.!|>":
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _extract_text_selection(text: str, selection: Selection) -> str:
    clipped_selection = _clip_selection_to_text(selection, text)
    return clipped_selection.extract(text)


def _clip_selection_to_text(selection: Selection, text: str) -> Selection:
    lines = text.splitlines()
    if not lines:
        return Selection(Offset(0, 0), Offset(0, 0))
    return Selection(
        _clip_selection_offset(selection.start, lines),
        _clip_selection_offset(selection.end, lines),
    )


def _clip_selection_offset(offset: Offset | None, lines: list[str]) -> Offset | None:
    if offset is None:
        return None
    line_index = min(max(offset.y, 0), len(lines) - 1)
    column = min(max(offset.x, 0), len(lines[line_index]))
    return Offset(column, line_index)
