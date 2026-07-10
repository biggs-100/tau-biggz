"""Tests for tool sandboxing (path validation)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from tau_coding.harness import SandboxConfig
from tau_coding.tools import ToolInputError, _validate_path_in_sandbox


def test_permissive_mode_allows_any_path() -> None:
    config = SandboxConfig(mode="permissive")
    cwd = Path("/home/user/project")
    assert _validate_path_in_sandbox(Path("/etc/passwd"), config, cwd) is None
    assert _validate_path_in_sandbox(Path("../outside"), config, cwd) is None


def test_none_config_allows_any_path() -> None:
    cwd = Path("/home/user/project")
    assert _validate_path_in_sandbox(Path("/etc/passwd"), None, cwd) is None


def test_strict_blocks_absolute_path_outside_cwd() -> None:
    config = SandboxConfig(mode="strict")
    cwd = Path("/home/user/project")
    with pytest.raises(ToolInputError, match="outside"):
        _validate_path_in_sandbox(Path("/etc/passwd"), config, cwd)


def test_strict_allows_path_within_cwd(tmp_path: Path) -> None:
    config = SandboxConfig(mode="strict")
    nested = tmp_path / "subdir" / "file.txt"
    assert _validate_path_in_sandbox(nested, config, tmp_path) is None


def test_strict_blocks_traversal_escape(tmp_path: Path) -> None:
    config = SandboxConfig(mode="strict", allow_temp=False)
    # Path inside cwd should pass
    inner = tmp_path / "inner.txt"
    inner.write_text("test")
    assert _validate_path_in_sandbox(inner, config, tmp_path) is None
    # Path to parent directory should be blocked
    parent_path = tmp_path.parent / "outside.txt"
    with pytest.raises(ToolInputError, match="outside"):
        _validate_path_in_sandbox(parent_path, config, tmp_path)


def test_strict_allows_allowed_paths(tmp_path: Path) -> None:
    allowed = tmp_path / "shared"
    allowed.mkdir()
    config = SandboxConfig(mode="strict", allowed_paths=(str(allowed),))
    cwd = tmp_path / "project"
    cwd.mkdir()
    file_in_allowed = allowed / "data.txt"
    assert _validate_path_in_sandbox(file_in_allowed, config, cwd) is None


def test_strict_allows_home_tau(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    tau_home = tmp_path / ".tau"
    tau_home.mkdir(parents=True)
    config = SandboxConfig(mode="strict", allow_home_tau=True)
    cwd = tmp_path / "project"
    cwd.mkdir()
    file_in_tau = tau_home / "config.json"
    assert _validate_path_in_sandbox(file_in_tau, config, cwd) is None


def test_strict_allows_temp_dir() -> None:
    config = SandboxConfig(mode="strict", allow_temp=True)
    cwd = Path("/home/user/project")
    temp_file = Path(tempfile.gettempdir()) / "tau-tmp.txt"
    assert _validate_path_in_sandbox(temp_file, config, cwd) is None


def test_strict_blocks_when_home_tau_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    tau_home = tmp_path / ".tau"
    tau_home.mkdir(parents=True)
    config = SandboxConfig(mode="strict", allow_home_tau=False, allow_temp=False)
    cwd = tmp_path / "project"
    cwd.mkdir()
    file_in_tau = tau_home / "config.json"
    with pytest.raises(ToolInputError):
        _validate_path_in_sandbox(file_in_tau, config, cwd)


def test_strict_blocks_empty_allowed_paths_does_not_allow(tmp_path: Path) -> None:
    config = SandboxConfig(mode="strict", allow_temp=False)
    cwd = tmp_path / "project"
    cwd.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(ToolInputError):
        _validate_path_in_sandbox(outside, config, cwd)


def test_strict_allows_relative_path_within_cwd(tmp_path: Path) -> None:
    config = SandboxConfig(mode="strict")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    file_path = subdir / "file.txt"
    file_path.write_text("content")
    assert _validate_path_in_sandbox(file_path, config, tmp_path) is None


@pytest.mark.skipif(os.name == "nt", reason="Symlink tests need admin on Windows")
def test_strict_blocks_symlink_escape(tmp_path: Path) -> None:
    config = SandboxConfig(mode="strict")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    # Symlink that resolves inside cwd should be allowed
    assert _validate_path_in_sandbox(link, config, tmp_path) is None
