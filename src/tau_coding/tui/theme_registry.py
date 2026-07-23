"""Theme registry — discover, validate, and resolve themes for the Tau TUI."""

from __future__ import annotations

import json
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
            import logging

            logging.getLogger("tau").warning(
                "Skipping invalid theme file %s: %s", path.name, exc
            )
    return themes


def load_themes() -> dict[str, ThemeData]:
    """Load and cache all built-in themes."""
    global _theme_cache
    if _theme_cache is not None:
        return _theme_cache
    _theme_cache = _load_from_dir(_BUILTIN_THEME_DIR)
    return _theme_cache


def get_theme(name: str) -> ThemeData | None:
    """Get a theme by name, returning None if not found."""
    return load_themes().get(name)


def available_theme_names() -> list[str]:
    """Return sorted list of available theme names."""
    return sorted(load_themes().keys())


def reset_cache() -> None:
    """Reset theme cache (useful for testing)."""
    global _theme_cache
    _theme_cache = None
