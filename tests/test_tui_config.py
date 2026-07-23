from pathlib import Path

import pytest

from tau_coding.paths import TauPaths
from tau_coding.tui.config import (
    TuiConfigError,
    TuiKeybindings,
    TuiSettings,
    get_tui_theme,
    load_tui_settings,
    save_tui_settings,
    tui_settings_from_json,
    tui_settings_path,
)


def test_tui_settings_path_uses_tau_home(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")

    assert tui_settings_path(paths) == tmp_path / ".tau" / "tui.json"


def test_load_tui_settings_returns_defaults_when_file_is_missing(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")

    assert load_tui_settings(paths) == TuiSettings()
    assert load_tui_settings(paths).keybindings.quit == "ctrl+d"


def test_load_tui_settings_reads_keybindings(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")
    path = tui_settings_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text(
        """
        {
          "keybindings": {
            "command_palette": "ctrl+j",
            "session_picker": "ctrl+y",
            "queue_follow_up": "f5",
            "accept_completion": "f2",
            "thinking_cycle": "f3",
            "model_cycle": "f6",
            "toggle_thinking": "f4",
            "copy_message": "ctrl+b"
          },
          "theme": "high-contrast"
        }
        """,
        encoding="utf-8",
    )

    settings = load_tui_settings(paths)

    assert settings.keybindings.command_palette == "ctrl+j"
    assert settings.keybindings.session_picker == "ctrl+y"
    assert settings.keybindings.queue_follow_up == "f5"
    assert settings.keybindings.toggle_tool_results == "ctrl+o"
    assert settings.keybindings.toggle_thinking == "f4"
    assert settings.keybindings.accept_completion == "f2"
    assert settings.keybindings.thinking_cycle == "f3"
    assert settings.keybindings.model_cycle == "f6"
    assert settings.keybindings.copy_message == "ctrl+b"
    assert settings.keybindings.cancel == "escape"
    assert settings.theme == "high-contrast"
    high_contrast = get_tui_theme("high-contrast")
    assert high_contrast is not None
    assert settings.resolved_theme == high_contrast


def test_save_tui_settings_writes_json(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")

    path = save_tui_settings(TuiSettings(theme="tau-light"), paths)

    assert path == tmp_path / ".tau" / "tui.json"
    assert load_tui_settings(paths).theme == "tau-light"


def test_tui_settings_ignores_removed_message_selection_keybindings() -> None:
    settings = tui_settings_from_json(
        {
            "keybindings": {
                "message_previous": "alt+up",
                "message_next": "alt+down",
            }
        }
    )

    assert settings == TuiSettings()


def test_tui_settings_reject_unknown_fields() -> None:
    with pytest.raises(TuiConfigError, match="Unknown TUI settings field"):
        tui_settings_from_json({"palette": {}})


def test_tui_keybindings_reject_duplicate_keys() -> None:
    with pytest.raises(TuiConfigError, match="assigned to both"):
        tui_settings_from_json(
            {
                "keybindings": {
                    "cancel": "escape",
                    "command_palette": "escape",
                }
            }
        )


def test_tui_settings_accept_any_theme_string() -> None:
    """Theme name validation is deferred to get_tui_theme(); any string is accepted."""
    settings = tui_settings_from_json({"theme": "solarized"})
    assert settings.theme == "solarized"
    assert get_tui_theme("solarized") is None  # unknown, returns None


def test_tui_settings_accept_light_theme() -> None:
    settings = tui_settings_from_json({"theme": "tau-light"})

    assert settings.theme == "tau-light"
    assert settings.resolved_theme.screen_background == "#ffffff"
    assert settings.resolved_theme.syntax_theme == "ansi_light"


def test_tui_settings_load_auto_copy_selection() -> None:
    settings = tui_settings_from_json({"auto_copy_selection": True})

    assert settings.auto_copy_selection is True
    assert settings.to_json()["auto_copy_selection"] is True


def test_tui_settings_reject_invalid_auto_copy_selection() -> None:
    with pytest.raises(TuiConfigError, match="auto_copy_selection"):
        tui_settings_from_json({"auto_copy_selection": "yes"})


def test_tui_keybindings_serialize_to_json() -> None:
    settings = TuiSettings(
        keybindings=TuiKeybindings(
            command_palette="ctrl+j",
            session_picker="ctrl+y",
            queue_follow_up="f5",
            accept_completion="f2",
            thinking_cycle="f3",
            model_cycle="f6",
            toggle_thinking="f4",
            copy_message="ctrl+b",
        ),
        theme="high-contrast",
    )

    assert settings.to_json()["keybindings"]["command_palette"] == "ctrl+j"
    assert settings.to_json()["keybindings"]["session_picker"] == "ctrl+y"
    assert settings.to_json()["keybindings"]["queue_follow_up"] == "f5"
    assert settings.to_json()["keybindings"]["toggle_tool_results"] == "ctrl+o"
    assert settings.to_json()["keybindings"]["toggle_thinking"] == "f4"
    assert settings.to_json()["keybindings"]["accept_completion"] == "f2"
    assert settings.to_json()["keybindings"]["thinking_cycle"] == "f3"
    assert settings.to_json()["keybindings"]["model_cycle"] == "f6"
    assert settings.to_json()["keybindings"]["copy_message"] == "ctrl+b"
    assert settings.to_json()["theme"] == "high-contrast"
    assert settings.to_json()["auto_copy_selection"] is False


def test_get_tui_theme_returns_builtin_theme() -> None:
    high_contrast = get_tui_theme("high-contrast")
    assert high_contrast is not None
    assert high_contrast.prompt_border == "#00ff66"
    tau_light = get_tui_theme("tau-light")
    assert tau_light is not None
    assert tau_light.prompt_border == "#2563eb"
    tau_dark = get_tui_theme("tau-dark")
    assert tau_dark is not None
    assert tau_dark.screen_background == "#000000"


# ── Custom theme discovery ─────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_theme_cache() -> None:
    """Reset the module-level theme cache before and after each test."""
    from tau_coding.tui.theme_registry import reset_cache

    reset_cache()
    yield
    reset_cache()


def _write_theme(directory: Path, name: str, **overrides: object) -> None:
    """Write a minimal valid theme JSON file into *directory*."""
    data = {
        "name": name,
        "dark": True,
        "syntax_theme": "ansi_dark",
        "colors": {
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
            "accent": "#db945a",
            "highlight_background": "#a7f3f0",
            "highlight_text": "#061a1a",
            "markdown_heading": "#db945a",
            "markdown_table_header": "#7b7b7b",
            "markdown_table_border": "#7b7b7b",
            "markdown_inline_code": "#759e95",
            "markdown_code_block_background": "#161b21",
            "markdown_link": "#93c5fd",
            "markdown_bullet": "#db945a",
            "completion_selected": "bold #061a1a on #a7f3f0",
            "completion_selected_description": "#123333 on #a7f3f0",
            "completion_description": "#667085",
            "success": "#4ade80",
            "error": "#ff4f4f",
            "tool_success_text": "#4ade80",
            "tool_error_text": "#ff4f4f",
        },
        "roles": {
            "user": {"border": "#7c8ea6", "body": "#d8dee9 on #000000"},
            "assistant": {"border": "#6ea6a0", "body": "#d8dee9 on #000000"},
            "tool": {"border": "#8a7a52", "body": "#cbd5e1 on #000000"},
            "error": {"border": "#ff4f4f", "body": "#ffb4b4 on #000000"},
            "status": {"border": "#526070", "body": "#aab4c2 on #000000"},
            "thinking": {"border": "#4b5563", "body": "#9ca3af on #000000"},
            "skill": {"border": "#b48ead", "body": "#e5d4ef on #000000"},
            "custom": {"border": "#7c8ea6", "body": "#d8dee9 on #000000"},
            "branch_summary": {"border": "#c084fc", "body": "#e9d5ff on #000000"},
            "compaction_summary": {"border": "#c084fc", "body": "#e9d5ff on #000000"},
        },
    }
    data.update(overrides)
    import json

    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def test_custom_user_theme_appears_in_available(tmp_path: Path) -> None:
    """A valid theme in the user dir appears in the loaded theme dict."""
    from tau_coding.tui.theme_registry import available_theme_names, load_themes

    user_dir = tmp_path / ".tau" / "themes"
    _write_theme(user_dir, "seafoam", dark=False)

    themes = load_themes(user_dir=user_dir)
    assert "seafoam" in themes
    assert themes["seafoam"].dark is False
    assert "seafoam" in available_theme_names()


def test_custom_theme_cannot_shadow_builtin(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A custom theme with a built-in name is silently skipped."""
    from tau_coding.tui.theme_registry import load_themes

    user_dir = tmp_path / ".tau" / "themes"
    _write_theme(user_dir, "tau-dark", colors={"screen_background": "#ffffff", **{k: "#000000" for k in (
        "screen_text", "chrome_background", "chrome_text", "muted_text", "sidebar_background",
        "border", "transcript_background", "prompt_background", "prompt_text", "prompt_border",
        "autocomplete_background", "accent", "highlight_background", "highlight_text",
        "markdown_heading", "markdown_table_header", "markdown_table_border", "markdown_inline_code",
        "markdown_code_block_background", "markdown_link", "markdown_bullet",
        "completion_selected", "completion_selected_description", "completion_description",
        "success", "error", "tool_success_text", "tool_error_text",
    )}})

    caplog.set_level("WARNING")
    themes = load_themes(user_dir=user_dir)

    # tau-dark is still the built-in definition with black background
    assert themes["tau-dark"].colors["screen_background"] == "#000000"
    assert "shadows built-in" in caplog.text


def test_project_theme_overrides_user_theme(tmp_path: Path) -> None:
    """When a custom name appears in user and project, project wins."""
    from tau_coding.tui.theme_registry import load_themes

    user_dir = tmp_path / "user"
    proj_dir = tmp_path / "project"
    _write_theme(user_dir, "custom-blue", colors={"screen_background": "#0000ff", **{k: "#000000" for k in (
        "screen_text", "chrome_background", "chrome_text", "muted_text", "sidebar_background",
        "border", "transcript_background", "prompt_background", "prompt_text", "prompt_border",
        "autocomplete_background", "accent", "highlight_background", "highlight_text",
        "markdown_heading", "markdown_table_header", "markdown_table_border", "markdown_inline_code",
        "markdown_code_block_background", "markdown_link", "markdown_bullet",
        "completion_selected", "completion_selected_description", "completion_description",
        "success", "error", "tool_success_text", "tool_error_text",
    )}})
    _write_theme(proj_dir, "custom-blue", colors={"screen_background": "#00ff00", **{k: "#000000" for k in (
        "screen_text", "chrome_background", "chrome_text", "muted_text", "sidebar_background",
        "border", "transcript_background", "prompt_background", "prompt_text", "prompt_border",
        "autocomplete_background", "accent", "highlight_background", "highlight_text",
        "markdown_heading", "markdown_table_header", "markdown_table_border", "markdown_inline_code",
        "markdown_code_block_background", "markdown_link", "markdown_bullet",
        "completion_selected", "completion_selected_description", "completion_description",
        "success", "error", "tool_success_text", "tool_error_text",
    )}})

    themes = load_themes(user_dir=user_dir, project_dir=proj_dir)
    assert themes["custom-blue"].colors["screen_background"] == "#00ff00"


def test_missing_theme_dirs_are_silent() -> None:
    """Non-existent user/project dirs don't raise or add bogus themes."""
    from tau_coding.tui.theme_registry import available_theme_names, load_themes

    themes = load_themes(user_dir=Path("/nonexistent/user/themes"), project_dir=Path("/nonexistent/project/themes"))
    assert len(themes) == 3  # only built-in
    assert available_theme_names() == ["high-contrast", "tau-dark", "tau-light"]


def test_unknown_theme_name_returns_none() -> None:
    """get_theme for an unknown name returns None."""
    from tau_coding.tui.theme_registry import get_theme

    assert get_theme("nonexistent") is None
