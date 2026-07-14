from pathlib import Path

import pytest

from tau_coding import (
    ShellConfigError,
    ShellSettings,
    TauPaths,
    load_shell_settings,
    shell_settings_from_json,
    shell_settings_path,
)


def test_load_shell_settings_missing_file_uses_defaults(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")

    assert load_shell_settings(paths) == ShellSettings()


def test_load_shell_settings_accepts_pi_style_shell_command_prefix(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")
    path = shell_settings_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"shellCommandPrefix": "shopt -s expand_aliases\\nalias gs=\\"git status\\""}',
        encoding="utf-8",
    )

    settings = load_shell_settings(paths)

    assert settings.shell_command_prefix == 'shopt -s expand_aliases\nalias gs="git status"'
    assert settings.to_json() == {
        "shellCommandPrefix": 'shopt -s expand_aliases\nalias gs="git status"'
    }


def test_shell_settings_accepts_tau_style_shell_command_prefix() -> None:
    settings = shell_settings_from_json({"shell_command_prefix": " alias ll='ls -la' "})

    assert settings.shell_command_prefix == "alias ll='ls -la'"


def test_shell_settings_rejects_unknown_fields() -> None:
    with pytest.raises(ShellConfigError, match="Unknown shell settings field"):
        shell_settings_from_json({"shell": "bash"})


def test_shell_settings_to_json_when_no_prefix_returns_empty_dict() -> None:
    settings = ShellSettings()
    assert settings.to_json() == {}


def test_load_shell_settings_invalid_json_raises_error(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")
    path = shell_settings_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text("not valid json", encoding="utf-8")

    with pytest.raises(ShellConfigError, match="not valid JSON"):
        load_shell_settings(paths)


def test_load_shell_settings_non_dict_json_raises_error(tmp_path: Path) -> None:
    paths = TauPaths(home=tmp_path / ".tau", agents_home=tmp_path / ".agents")
    path = shell_settings_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text('["list", "not", "dict"]', encoding="utf-8")

    with pytest.raises(ShellConfigError, match="must be a JSON object"):
        load_shell_settings(paths)


def test_shell_settings_rejects_both_camel_and_snake_case() -> None:
    with pytest.raises(ShellConfigError, match="Use only one of"):
        shell_settings_from_json(
            {
                "shellCommandPrefix": "echo hello",
                "shell_command_prefix": "echo hello",
            }
        )


def test_shell_settings_without_prefix_returns_default() -> None:
    settings = shell_settings_from_json({})
    assert settings == ShellSettings()
    assert settings.to_json() == {}


def test_shell_settings_rejects_non_string_prefix() -> None:
    with pytest.raises(ShellConfigError, match="must be a string"):
        shell_settings_from_json({"shellCommandPrefix": 42})
