"""Sidebar and compact session-info widgets for Tau's TUI."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from subprocess import TimeoutExpired, run
from typing import Protocol

from rich.align import Align
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from tau_agent.tools import AgentTool
from tau_coding.extensions import get_default_registry
from tau_coding.prompt_templates import PromptTemplate
from tau_coding.skills import Skill
from tau_coding.system_prompt import ProjectContextFile
from tau_coding.tui.config import TAU_DARK_THEME, TuiTheme

TAU_SIDEBAR_LOGO = "τ = 2π"


class SessionSummarySource(Protocol):
    """Session attributes displayed by the sidebar."""

    @property
    def cwd(self) -> Path: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def tools(self) -> Sequence[AgentTool]: ...

    @property
    def skills(self) -> Sequence[Skill]: ...

    @property
    def prompt_templates(self) -> Sequence[PromptTemplate]: ...

    @property
    def context_files(self) -> Sequence[ProjectContextFile]: ...

    @property
    def context_token_estimate(self) -> int: ...

    @property
    def auto_compact_token_threshold(self) -> int | None: ...

    @property
    def context_window_tokens(self) -> int: ...

    @property
    def thinking_level(self) -> str: ...


class SessionSidebar(Static):
    """Compact sidebar with current session metadata."""

    def update_from_session(
        self,
        session: SessionSummarySource,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
    ) -> None:
        """Redraw the sidebar from current session metadata."""
        self.update(render_session_sidebar(session, theme=theme))


class CompactSessionInfo(Static):
    """Single-line session metadata for narrow TUI layouts."""

    def update_from_session(
        self,
        session: SessionSummarySource,
        *,
        theme: TuiTheme = TAU_DARK_THEME,
    ) -> None:
        """Redraw compact session metadata."""
        self.update(render_compact_session_info(session, theme=theme))


def render_session_sidebar(
    session: SessionSummarySource,
    *,
    theme: TuiTheme = TAU_DARK_THEME,
) -> RenderableType:
    """Render a dark, minimalist summary of the active coding session."""
    metadata = Table.grid(padding=(0, 1))
    metadata.add_column(style=theme.completion_description, no_wrap=True)
    metadata.add_column(style=theme.prompt_text)
    metadata.add_row("provider", session.provider_name)
    metadata.add_row("model", session.model)
    metadata.add_row("thinking", _thinking_level(session))
    metadata.add_row("tools", str(len(session.tools)))
    metadata.add_row("skills", str(len(session.skills)))

    tools = _bullet_list([tool.name for tool in session.tools], empty="No tools", theme=theme)
    skills = _bullet_list(
        [skill.name for skill in session.skills],
        empty="No skills loaded yet",
        theme=theme,
    )
    prompts = _bullet_list(
        [template.name for template in session.prompt_templates],
        empty="No prompt templates",
        theme=theme,
    )
    context = _bullet_list(
        _context_file_labels(session.context_files, cwd=session.cwd),
        empty="No context files",
        theme=theme,
    )
    equation = Text(TAU_SIDEBAR_LOGO, style=f"bold {theme.prompt_text}")

    return Group(
        Padding(Align.center(equation), (0, 0, 1, 0)),
        _sidebar_section("session", metadata, theme=theme),
        _sidebar_separator(theme=theme),
        _sidebar_section("context", context, theme=theme),
        _sidebar_separator(theme=theme),
        _sidebar_section("tools", tools, theme=theme),
        _sidebar_separator(theme=theme),
        _sidebar_section("skills", skills, theme=theme),
        _sidebar_separator(theme=theme),
        _sidebar_section("prompts", prompts, theme=theme),
    )


def _sidebar_section(
    title: str,
    body: RenderableType,
    *,
    theme: TuiTheme,
) -> RenderableType:
    """Render one sidebar section without a surrounding border."""
    header = Text(title, style=f"bold {theme.accent}")
    return Group(Padding(header, (0, 0, 0, 1)), Padding(body, (0, 0, 1, 1)))


def _sidebar_separator(*, theme: TuiTheme) -> RenderableType:
    """Render a subtle divider between sidebar sections."""
    return Padding(Rule(style=theme.border), (0, 0, 1, 0))


def render_compact_session_info(
    session: SessionSummarySource,
    *,
    theme: TuiTheme = TAU_DARK_THEME,
) -> RenderableType:
    """Render the session facts below the prompt."""
    left = Text(
        f"{_short_path(session.cwd)} ({_git_branch(session.cwd)})",
        style=theme.prompt_text,
        overflow="fold",
        no_wrap=False,
    )
    right = Text(style=theme.muted_text, overflow="fold", no_wrap=False, justify="right")
    right.append(_context_usage(session), style=theme.completion_description)
    right.append("  ")
    right.append(f"{session.provider_name}:{session.model}", style=theme.prompt_text)
    right.append(" ")
    right.append(f"({_thinking_level(session)})", style=theme.completion_description)

    # Extension UI widgets
    try:
        ui_widgets = get_default_registry().get_ui_widgets(zone="status-bar")
        if ui_widgets:
            parts = []
            for w in ui_widgets:
                try:
                    widget_text = w.text_fn()
                    if widget_text:
                        parts.append(widget_text)
                except Exception:
                    pass
            if parts:
                widget_part = Text(" | ".join(parts), style=theme.completion_description)
                left.append("  ")
                left.append(widget_part)
    except Exception:
        pass

    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=1, justify="right")
    table.add_row(left, right)
    return table


def _context_usage(session: SessionSummarySource) -> str:
    threshold = session.auto_compact_token_threshold
    if threshold is None or threshold <= 0:
        return (
            f"{_compact_token_count(session.context_token_estimate)}"
            f"/{_compact_token_count(session.context_window_tokens)} context"
        )
    return (
        f"{_compact_token_count(session.context_token_estimate)}"
        f"/{_compact_token_count(threshold)} context"
    )


def _compact_token_count(value: int) -> str:
    if value <= 0:
        return "0k"
    if value < 1000:
        return "<1k"
    return f"{(value + 500) // 1000}k"


def _context_file_labels(
    context_files: Sequence[ProjectContextFile],
    *,
    cwd: Path,
) -> list[str]:
    return [_context_file_label(Path(context_file.path), cwd=cwd) for context_file in context_files]


def _context_file_label(path: Path, *, cwd: Path) -> str:
    expanded_path = path.expanduser()
    if not expanded_path.is_absolute():
        expanded_path = cwd / expanded_path
    try:
        return str(expanded_path.resolve().relative_to(cwd.expanduser().resolve()))
    except (OSError, ValueError):
        return _short_path(expanded_path)


def _thinking_level(session: SessionSummarySource) -> str:
    available = getattr(session, "available_thinking_levels", None)
    if available == ():
        return "unavailable"
    explicit_level = getattr(session, "thinking_level", None)
    if explicit_level:
        return str(explicit_level)
    state = getattr(session, "state", None)
    thinking_level = getattr(state, "thinking_level", None)
    return str(thinking_level) if thinking_level else "--"


def _git_branch(cwd: Path) -> str:
    try:
        result = run(
            ["git", "-C", str(cwd), "branch", "--show-current"],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        )
    except OSError:
        return "--"
    except TimeoutExpired:
        return "--"
    branch = result.stdout.strip()
    if branch:
        return branch
    return "--"


def _bullet_list(
    items: Sequence[str],
    *,
    empty: str,
    theme: TuiTheme,
) -> Text:
    text = Text()
    if not items:
        text.append(empty, style=theme.completion_description)
        return text

    for index, item in enumerate(items):
        if index:
            text.append("\n")
        text.append("• ", style=theme.completion_description)
        text.append(item, style=theme.prompt_text)
    return text


def _short_path(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)
