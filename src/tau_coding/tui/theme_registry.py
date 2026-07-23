"""Theme registry — discover, validate, and resolve themes for the Tau TUI."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, field_validator


# ── Theme Data Model ────────────────────────────────────────────


class ThemeRoleStyle(BaseModel):
    """Validated role style from a theme JSON file."""

    border: str
    body: str


class ThemeData(BaseModel):
    """Pydantic model for a theme JSON file."""

    name: str
    dark: bool = True
    syntax_theme: str = "ansi_dark"
    colors: dict[str, str]
    roles: dict[str, ThemeRoleStyle]

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Color '{key}' must be a non-empty string")
        return v


# ── Theme Registry (module-level singleton) ──────────────────────

_BUILTIN_THEME_DIR = Path(__file__).parent / "themes"
_theme_cache: dict[str, ThemeData] | None = None

_log = logging.getLogger("tau")

# Hardcoded fallback when the built-in tau-dark.json cannot be loaded.
_FALLBACK_THEME = ThemeData(
    name="tau-dark",
    dark=True,
    syntax_theme="ansi_dark",
    colors={
        "screen_background": "#000000",
        "screen_text": "#d8dee9",
        "chrome_background": "#000000",
        "chrome_text": "#d8dee9",
        "muted_text": "#667085",
        "sidebar_background": "#000000",
        "border": "#141922",
        "transcript_background": "#000000",
        "prompt_background": "#101419",
        "prompt_text": "#e5e7eb",
        "prompt_border": "#2d3748",
        "autocomplete_background": "#000000",
        "accent": "#a7f3f0",
        "success": "#4ade80",
        "error": "#ff4f4f",
        "tool_success_text": "#4ade80",
        "tool_error_text": "#ff4f4f",
        "highlight_background": "#a7f3f0",
        "highlight_text": "#061a1a",
        "markdown_heading": "#a7f3f0",
        "markdown_table_header": "#7b7b7b",
        "markdown_table_border": "#7b7b7b",
        "markdown_inline_code": "#759e95",
        "markdown_code_block_background": "#161b21",
        "markdown_link": "#93c5fd",
        "markdown_bullet": "#a7f3f0",
        "completion_selected": "bold #061a1a on #a7f3f0",
        "completion_selected_description": "#061a1a on #a7f3f0",
        "completion_description": "#667085",
    },
    roles={
        "user": ThemeRoleStyle(border="#7c8ea6", body="#d8dee9 on #101419"),
        "assistant": ThemeRoleStyle(border="#6ea6a0", body="#d8dee9 on #000000"),
        "tool": ThemeRoleStyle(border="#8a7a52", body="#cbd5e1 on #000000"),
        "error": ThemeRoleStyle(border="#ff4f4f", body="#ffb4b4 on #000000"),
        "status": ThemeRoleStyle(border="#526070", body="#aab4c2 on #000000"),
        "thinking": ThemeRoleStyle(border="#4b5563", body="#9ca3af on #000000"),
        "skill": ThemeRoleStyle(border="#b48ead", body="#e5d4ef on #000000"),
        "custom": ThemeRoleStyle(border="#6ea6a0", body="#d8dee9 on #000000"),
        "branch_summary": ThemeRoleStyle(border="#c084fc", body="#e9d5ff on #000000"),
        "compaction_summary": ThemeRoleStyle(border="#c084fc", body="#e9d5ff on #000000"),
    },
)


def _load_from_dir(directory: Path) -> dict[str, ThemeData]:
    """Load all .json theme files from a directory."""
    themes: dict[str, ThemeData] = {}
    if not directory.is_dir():
        return themes
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
            theme = ThemeData.model_validate(data)
            themes[theme.name] = theme
        except Exception as exc:
            _log.warning("Skipping invalid theme file %s: %s", path.name, exc)
    return themes


def _merge_custom(
    themes: dict[str, ThemeData],
    custom: dict[str, ThemeData],
    builtin_names: set[str],
    source: str,
    source_path: str,
) -> None:
    """Merge custom themes into *themes*, respecting shadow rules.

    Custom themes whose name matches a built-in are silently skipped.
    Identical names across user/project dirs: highest-precedence wins,
    with a warning logged for the overridden definition.
    """
    for name, data in custom.items():
        if name in builtin_names:
            _log.warning(
                "Custom theme '%s' from %s (%s) shadows built-in — skipping",
                name,
                source,
                source_path,
            )
            continue
        if name in themes:
            _log.warning(
                "Custom theme '%s' from %s (%s) overrides previous definition",
                name,
                source,
                source_path,
            )
        themes[name] = data


def load_themes(
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> dict[str, ThemeData]:
    """Load and cache themes from built-in, user, and project dirs.

    Precedence (lowest → highest):  built-in → user → project.
    Custom themes cannot shadow built-in names (silently skipped).

    When *user_dir* or *project_dir* is ``None`` the corresponding default
    is auto-detected:

    - user_dir  — ``~/.tau/themes/``
    - project_dir — ``{cwd}/.tau/themes/``
    """
    global _theme_cache
    if _theme_cache is not None:
        return _theme_cache

    themes: dict[str, ThemeData] = {}

    # 1. Built-in (lowest precedence)
    builtin = _load_from_dir(_BUILTIN_THEME_DIR)
    _log.info("Loaded %d built-in theme(s) from %s", len(builtin), _BUILTIN_THEME_DIR)
    _BUILTIN_NAMES = set(builtin.keys())
    themes.update(builtin)

    # 2. User themes (~/.tau/themes/)
    if user_dir is None:
        from tau_coding.paths import TauPaths

        user_dir = TauPaths().themes_dir
    if user_dir.is_dir():
        _log.info("Scanning user themes from %s", user_dir)
        _merge_custom(
            themes,
            _load_from_dir(user_dir),
            _BUILTIN_NAMES,
            "user",
            str(user_dir),
        )

    # 3. Project themes ({cwd}/.tau/themes/)
    if project_dir is None:
        from tau_coding.paths import TauPaths

        project_dir = TauPaths().project_themes_dir(Path.cwd())
    if project_dir.is_dir():
        _log.info("Scanning project themes from %s", project_dir)
        _merge_custom(
            themes,
            _load_from_dir(project_dir),
            _BUILTIN_NAMES,
            "project",
            str(project_dir),
        )

    _log.info("Total available themes: %d", len(themes))
    _theme_cache = themes
    return themes


def get_theme(name: str) -> ThemeData | None:
    """Get a theme by name, returning a hardcoded fallback for 'tau-dark' if not found."""
    themes = load_themes()
    if name in themes:
        return themes[name]
    if name == "tau-dark":
        _log.warning("Built-in tau-dark theme not found, using hardcoded fallback")
        return _FALLBACK_THEME
    return None


def available_theme_names() -> list[str]:
    """Return sorted list of available theme names."""
    return sorted(load_themes().keys())


def reset_cache() -> None:
    """Reset theme cache (useful for testing)."""
    global _theme_cache
    _theme_cache = None
