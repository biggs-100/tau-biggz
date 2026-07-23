"""Durable Textual TUI configuration for Tau."""

from __future__ import annotations

from dataclasses import dataclass, field
from json import dumps, loads
from pathlib import Path
from typing import Any

from tau_coding.paths import TauPaths


class TuiConfigError(ValueError):
    """Raised when Tau TUI configuration is invalid."""


@dataclass(frozen=True, slots=True)
class TuiKeybindings:
    """Configurable keys for Tau's built-in Textual frontend."""

    cancel: str = "escape"
    command_palette: str = "ctrl+k"
    session_picker: str = "ctrl+r"
    queue_follow_up: str = "alt+enter"
    accept_completion: str = "tab"
    completion_next: str = "down"
    completion_previous: str = "up"
    thinking_cycle: str = "shift+tab"
    model_cycle: str = "ctrl+p"
    toggle_thinking: str = "ctrl+t"
    toggle_tool_results: str = "ctrl+o"
    copy_message: str = "ctrl+c"
    quit: str = "ctrl+d"

    def to_json(self) -> dict[str, str]:
        """Serialize these keybindings to JSON-compatible data."""
        return {
            "cancel": self.cancel,
            "command_palette": self.command_palette,
            "session_picker": self.session_picker,
            "queue_follow_up": self.queue_follow_up,
            "accept_completion": self.accept_completion,
            "completion_next": self.completion_next,
            "completion_previous": self.completion_previous,
            "thinking_cycle": self.thinking_cycle,
            "model_cycle": self.model_cycle,
            "toggle_thinking": self.toggle_thinking,
            "toggle_tool_results": self.toggle_tool_results,
            "copy_message": self.copy_message,
            "quit": self.quit,
        }


type TuiThemeName = str


@dataclass(frozen=True, slots=True)
class TuiRoleStyle:
    """Colors for one transcript role block."""

    border: str
    body: str


@dataclass(frozen=True, slots=True)
class TuiTheme:
    """Resolved visual theme for Tau's built-in Textual frontend."""

    name: str
    screen_background: str
    screen_text: str
    chrome_background: str
    chrome_text: str
    muted_text: str
    sidebar_background: str
    border: str
    transcript_background: str
    prompt_background: str
    prompt_text: str
    prompt_border: str
    autocomplete_background: str
    accent: str
    highlight_background: str
    highlight_text: str
    markdown_heading: str
    markdown_table_header: str
    markdown_table_border: str
    markdown_inline_code: str
    markdown_code_block_background: str
    markdown_link: str
    markdown_bullet: str
    completion_selected: str
    completion_selected_description: str
    completion_description: str
    syntax_theme: str
    role_styles: dict[str, TuiRoleStyle]
    # New fields for Phase 2
    success: str = ""
    error: str = ""
    tool_success_text: str = ""
    tool_error_text: str = ""
    dark: bool = True


def _build_tui_theme_from_registry(name: str) -> TuiTheme:
    """Construct a TuiTheme from the registry by name.

    Raises TuiConfigError if the theme is not found.
    """
    from tau_coding.tui.theme_registry import get_theme as _get_registry_theme

    data = _get_registry_theme(name)
    if data is None:
        raise TuiConfigError(f"Unknown TUI theme: {name}")
    return TuiTheme(
        name=data.name,
        screen_background=data.colors.get("screen_background", ""),
        screen_text=data.colors.get("screen_text", ""),
        chrome_background=data.colors.get("chrome_background", ""),
        chrome_text=data.colors.get("chrome_text", ""),
        muted_text=data.colors.get("muted_text", ""),
        sidebar_background=data.colors.get("sidebar_background", ""),
        border=data.colors.get("border", ""),
        transcript_background=data.colors.get("transcript_background", ""),
        prompt_background=data.colors.get("prompt_background", ""),
        prompt_text=data.colors.get("prompt_text", ""),
        prompt_border=data.colors.get("prompt_border", ""),
        autocomplete_background=data.colors.get("autocomplete_background", ""),
        accent=data.colors.get("accent", ""),
        highlight_background=data.colors.get("highlight_background", ""),
        highlight_text=data.colors.get("highlight_text", ""),
        markdown_heading=data.colors.get("markdown_heading", ""),
        markdown_table_header=data.colors.get("markdown_table_header", ""),
        markdown_table_border=data.colors.get("markdown_table_border", ""),
        markdown_inline_code=data.colors.get("markdown_inline_code", ""),
        markdown_code_block_background=data.colors.get(
            "markdown_code_block_background", ""
        ),
        markdown_link=data.colors.get("markdown_link", ""),
        markdown_bullet=data.colors.get("markdown_bullet", ""),
        completion_selected=data.colors.get("completion_selected", ""),
        completion_selected_description=data.colors.get(
            "completion_selected_description", ""
        ),
        completion_description=data.colors.get("completion_description", ""),
        syntax_theme=data.syntax_theme,
        role_styles={
            role_name: TuiRoleStyle(
                border=role_data.border, body=role_data.body
            )
            for role_name, role_data in data.roles.items()
        },
        success=data.colors.get("success", ""),
        error=data.colors.get("error", ""),
        tool_success_text=data.colors.get("tool_success_text", ""),
        tool_error_text=data.colors.get("tool_error_text", ""),
        dark=data.dark,
    )


TAU_DARK_THEME = _build_tui_theme_from_registry("tau-dark")
TAU_LIGHT_THEME = _build_tui_theme_from_registry("tau-light")
HIGH_CONTRAST_THEME = _build_tui_theme_from_registry("high-contrast")
BUILTIN_TUI_THEME_NAMES: tuple[str, ...] = (
    "tau-dark",
    "tau-light",
    "high-contrast",
)


def get_tui_theme(name: str = "tau-dark") -> TuiTheme | None:
    """Get a TuiTheme by name, returning None if not found."""
    from tau_coding.tui.theme_registry import get_theme as _get_registry_theme

    data = _get_registry_theme(name)
    if data is None:
        return None
    return TuiTheme(
        name=data.name,
        screen_background=data.colors.get("screen_background", ""),
        screen_text=data.colors.get("screen_text", ""),
        chrome_background=data.colors.get("chrome_background", ""),
        chrome_text=data.colors.get("chrome_text", ""),
        muted_text=data.colors.get("muted_text", ""),
        sidebar_background=data.colors.get("sidebar_background", ""),
        border=data.colors.get("border", ""),
        transcript_background=data.colors.get("transcript_background", ""),
        prompt_background=data.colors.get("prompt_background", ""),
        prompt_text=data.colors.get("prompt_text", ""),
        prompt_border=data.colors.get("prompt_border", ""),
        autocomplete_background=data.colors.get("autocomplete_background", ""),
        accent=data.colors.get("accent", ""),
        highlight_background=data.colors.get("highlight_background", ""),
        highlight_text=data.colors.get("highlight_text", ""),
        markdown_heading=data.colors.get("markdown_heading", ""),
        markdown_table_header=data.colors.get("markdown_table_header", ""),
        markdown_table_border=data.colors.get("markdown_table_border", ""),
        markdown_inline_code=data.colors.get("markdown_inline_code", ""),
        markdown_code_block_background=data.colors.get(
            "markdown_code_block_background", ""
        ),
        markdown_link=data.colors.get("markdown_link", ""),
        markdown_bullet=data.colors.get("markdown_bullet", ""),
        completion_selected=data.colors.get("completion_selected", ""),
        completion_selected_description=data.colors.get(
            "completion_selected_description", ""
        ),
        completion_description=data.colors.get("completion_description", ""),
        syntax_theme=data.syntax_theme,
        role_styles={
            role_name: TuiRoleStyle(
                border=role_data.border, body=role_data.body
            )
            for role_name, role_data in data.roles.items()
        },
        success=data.colors.get("success", ""),
        error=data.colors.get("error", ""),
        tool_success_text=data.colors.get("tool_success_text", ""),
        tool_error_text=data.colors.get("tool_error_text", ""),
        dark=data.dark,
    )


@dataclass(frozen=True, slots=True)
class TuiSettings:
    """Tau TUI settings loaded from Tau home."""

    keybindings: TuiKeybindings = field(default_factory=TuiKeybindings)
    theme: str = "tau-dark"
    auto_copy_selection: bool = True

    def to_json(self) -> dict[str, Any]:
        """Serialize these settings to JSON-compatible data."""
        return {
            "auto_copy_selection": self.auto_copy_selection,
            "keybindings": self.keybindings.to_json(),
            "theme": self.theme,
        }

    @property
    def resolved_theme(self) -> TuiTheme:
        """Return the selected theme, falling back to tau-dark."""
        theme = get_tui_theme(self.theme)
        if theme is None:
            theme = get_tui_theme("tau-dark")
            assert theme is not None
        return theme


def tui_settings_path(paths: TauPaths | None = None) -> Path:
    """Return the durable TUI settings path."""
    return (paths or TauPaths()).home / "tui.json"


def load_tui_settings(paths: TauPaths | None = None) -> TuiSettings:
    """Load durable TUI settings, falling back to built-in defaults."""
    path = tui_settings_path(paths)
    if not path.exists():
        return TuiSettings()
    raw = loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TuiConfigError("TUI settings must be a JSON object")
    return tui_settings_from_json(raw)


def save_tui_settings(settings: TuiSettings, paths: TauPaths | None = None) -> Path:
    """Persist durable TUI settings and return the written path."""
    path = tui_settings_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(settings.to_json(), indent=2) + "\n", encoding="utf-8")
    return path


def tui_settings_from_json(data: dict[str, Any]) -> TuiSettings:
    """Parse TUI settings from JSON-compatible data."""
    allowed_fields = {"auto_copy_selection", "keybindings", "theme"}
    unknown_fields = set(data) - allowed_fields
    if unknown_fields:
        raise TuiConfigError(f"Unknown TUI settings field: {sorted(unknown_fields)[0]}")

    keybindings_data = data.get("keybindings", {})
    if not isinstance(keybindings_data, dict):
        raise TuiConfigError("TUI keybindings must be a JSON object")
    return TuiSettings(
        keybindings=_keybindings_from_json(keybindings_data),
        theme=_theme_name(data.get("theme", "tau-dark")),
        auto_copy_selection=_bool_setting(
            data.get("auto_copy_selection", False),
            "auto_copy_selection",
        ),
    )


def _bool_setting(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise TuiConfigError(f"TUI setting must be a boolean: {field_name}")


def _keybindings_from_json(data: dict[str, Any]) -> TuiKeybindings:
    defaults = TuiKeybindings()
    allowed_fields = set(defaults.to_json())
    legacy_fields = {"message_previous", "message_next"}
    unknown_fields = set(data) - allowed_fields - legacy_fields
    if unknown_fields:
        raise TuiConfigError(f"Unknown TUI keybinding: {sorted(unknown_fields)[0]}")

    values = {
        field_name: _key_string(data.get(field_name, default_value), field_name)
        for field_name, default_value in defaults.to_json().items()
    }
    _reject_duplicate_keys(values)
    return TuiKeybindings(**values)


def _key_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TuiConfigError(f"TUI keybinding must be a non-empty string: {field_name}")
    return value.strip()


def _theme_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TuiConfigError("TUI theme must be a non-empty string")
    return value.strip()


def _reject_duplicate_keys(values: dict[str, str]) -> None:
    key_to_action: dict[str, str] = {}
    for action, key in values.items():
        previous_action = key_to_action.get(key)
        if previous_action is not None:
            raise TuiConfigError(
                f"TUI keybinding {key!r} is assigned to both {previous_action!r} and {action!r}"
            )
        key_to_action[key] = action
