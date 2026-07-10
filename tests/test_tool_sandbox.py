"""Tests for Tool Sandboxing — SandboxConfig and _validate_path_in_sandbox."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tau_coding.harness import SandboxConfig
from tau_coding.tools import ToolInputError, _validate_path_in_sandbox


# ── SandboxConfig tests ─────────────────────────────────────────────


class TestSandboxConfig:
    """SandboxConfig dataclass construction and defaults."""

    def test_defaults_are_permissive(self) -> None:
        """Default construction yields permissive mode with safe defaults."""
        cfg = SandboxConfig()
        assert cfg.mode == "permissive"
        assert cfg.allowed_paths == ()
        assert cfg.allow_home_tau is True
        assert cfg.allow_temp is True

    def test_custom_values(self) -> None:
        """Custom mode and allowed_paths are reflected."""
        cfg = SandboxConfig(
            mode="strict",
            allowed_paths=("/data", "/shared"),
            allow_home_tau=False,
            allow_temp=False,
        )
        assert cfg.mode == "strict"
        assert cfg.allowed_paths == ("/data", "/shared")
        assert cfg.allow_home_tau is False
        assert cfg.allow_temp is False

    def test_allowed_paths_is_immutable_tuple(self) -> None:
        """allowed_paths should be a tuple (immutable)."""
        cfg = SandboxConfig(allowed_paths=("/data",))
        assert isinstance(cfg.allowed_paths, tuple)


# ── _validate_path_in_sandbox tests ────────────────────────────────


class TestValidatePathInSandbox:
    """_validate_path_in_sandbox path validation behavior."""

    def test_permissive_mode_skips_validation(self, tmp_path: Path) -> None:
        """Permissive mode allows any path."""
        config = SandboxConfig(mode="permissive")
        assert _validate_path_in_sandbox(tmp_path / "foo.txt", config, tmp_path) is None
        assert _validate_path_in_sandbox(Path("/etc/passwd"), config, tmp_path) is None

    def test_sandbox_none_skips_validation(self, tmp_path: Path) -> None:
        """None config skips all validation."""
        assert _validate_path_in_sandbox(tmp_path / "foo.txt", None, tmp_path) is None

    def test_path_within_cwd_passes(self, tmp_path: Path) -> None:
        """Path inside cwd passes in strict mode."""
        config = SandboxConfig(mode="strict")
        file_path = tmp_path / "subdir" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("hello")
        assert _validate_path_in_sandbox(file_path, config, tmp_path) is None

    def test_path_outside_cwd_fails(self, tmp_path: Path) -> None:
        """Absolute path outside cwd raises ToolInputError."""
        config = SandboxConfig(mode="strict")
        with pytest.raises(ToolInputError) as exc:
            _validate_path_in_sandbox(Path("/etc/passwd"), config, tmp_path)
        msg = str(exc.value)
        assert "outside" in msg.lower() or "working directory" in msg.lower()

    def test_relative_traversal_blocked(self, tmp_path: Path) -> None:
        """Relative traversal outside cwd raises ToolInputError."""
        config = SandboxConfig(
            mode="strict",
            allow_temp=False,
            allow_home_tau=False,
        )
        malicious = (tmp_path / "../../etc/passwd").resolve()
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(malicious, config, tmp_path)

    def test_symlink_escape_blocked(self, tmp_path: Path) -> None:
        """Symlink inside cwd pointing outside is blocked."""
        try:
            link = tmp_path / "_sym_test_"
            link.symlink_to(tmp_path / "_dummy_")
            link.unlink()
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks on this platform")

        config = SandboxConfig(
            mode="strict",
            allow_temp=False,
            allow_home_tau=False,
        )
        link_path = tmp_path / "link_to_etc"
        link_path.symlink_to("/etc")
        escaped = (link_path / "hostname").resolve()
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(escaped, config, tmp_path)

    def test_temp_dir_allowed_by_default(self, tmp_path: Path) -> None:
        """System temp directory path passes with allow_temp=True."""
        config = SandboxConfig(mode="strict", allow_temp=True)
        temp_path = Path(tempfile.gettempdir()) / "tau-tmp" / "output.txt"
        assert _validate_path_in_sandbox(temp_path, config, tmp_path) is None

    def test_temp_dir_blocked_when_disabled(self, tmp_path: Path) -> None:
        """allow_temp=False blocks system temp directory."""
        config = SandboxConfig(mode="strict", allow_temp=False)
        temp_path = Path(tempfile.gettempdir()) / "foo.txt"
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(temp_path, config, tmp_path)

    def test_home_tau_allowed_by_default(self, tmp_path: Path) -> None:
        """~/.tau path passes with allow_home_tau=True."""
        config = SandboxConfig(mode="strict", allow_home_tau=True)
        tau_path = Path.home() / ".tau" / "config.toml"
        assert _validate_path_in_sandbox(tau_path, config, tmp_path) is None

    def test_home_tau_blocked_when_disabled(self, tmp_path: Path) -> None:
        """allow_home_tau=False blocks ~/.tau path."""
        config = SandboxConfig(mode="strict", allow_home_tau=False)
        tau_path = Path.home() / ".tau" / "config.toml"
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(tau_path, config, tmp_path)

    def test_allowed_paths_overrides_boundary(self, tmp_path: Path) -> None:
        """Explicit allowed_paths passes paths outside cwd."""
        config = SandboxConfig(
            mode="strict",
            allowed_paths=("/data",),
        )
        data_path = Path("/data") / "global" / "shared.json"
        assert _validate_path_in_sandbox(data_path, config, tmp_path) is None

    def test_allowed_paths_relative_to_cwd(self, tmp_path: Path) -> None:
        """allowed_paths entries are resolved relative to cwd."""
        sibling = tmp_path.parent / "other-project" / "shared"
        sibling.mkdir(parents=True, exist_ok=True)
        config = SandboxConfig(
            mode="strict",
            allowed_paths=("../other-project/shared",),
        )
        file = sibling / "data.txt"
        file.write_text("data")
        assert _validate_path_in_sandbox(file, config, tmp_path) is None

    def test_error_message_format(self, tmp_path: Path) -> None:
        """Error message is user-facing with remediation hints."""
        config = SandboxConfig(mode="strict")
        with pytest.raises(ToolInputError) as exc:
            _validate_path_in_sandbox(Path("/etc/passwd"), config, tmp_path)
        msg = str(exc.value)
        assert "allowed_paths" in msg
        assert "--unsafe" in msg

    def test_root_dir_as_sandbox_root(self) -> None:
        """Root directory as cwd allows all paths (extreme case)."""
        config = SandboxConfig(mode="strict")
        root = Path("/")
        assert _validate_path_in_sandbox(Path("/etc/passwd"), config, root) is None

    def test_empty_allowed_paths_no_extra_allowance(self, tmp_path: Path) -> None:
        """Empty tuple does not add any extra allowance."""
        config = SandboxConfig(mode="strict", allowed_paths=())
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(Path("/etc/passwd"), config, tmp_path)

    def test_windows_drive_letter_mismatch(self, tmp_path: Path) -> None:
        """Cross-drive path is blocked (platform-aware)."""
        config = SandboxConfig(mode="strict")
        external = Path("/different-mount") / "file.txt"
        if external.resolve() == tmp_path.resolve():
            pytest.skip("Paths resolve to same location")
        with pytest.raises(ToolInputError):
            _validate_path_in_sandbox(external, config, tmp_path)
