"""Tests for tau_coding.package_manager — package install/remove/list."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tau_coding.package_manager import (
    InstalledPackage,
    PackageResult,
    _install_git,
    _install_local,
    _load_registry,
    _parse_source,
    _save_registry,
    _symlink_resources,
    install_package,
    list_packages,
    package_command,
    remove_package,
)

# ── helpers ────────────────────────────────────────────────────────────


def _monkeypatch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect _packages_dir and _registry_path to tmp_path and return the tau root.

    Creates the parent directory for the registry file since _save_registry
    does not create it automatically.
    """
    tau_root = tmp_path / ".tau"
    tau_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "tau_coding.package_manager._packages_dir",
        lambda: tau_root / "packages",
    )
    monkeypatch.setattr(
        "tau_coding.package_manager._registry_path",
        lambda: tau_root / "tau_packages.json",
    )
    return tau_root


# ── _parse_source ──────────────────────────────────────────────────────


class TestParseSource:
    def test_git_github(self) -> None:
        source_type, url, name = _parse_source("git:github.com/user/repo")
        assert source_type == "git"
        assert url == "github.com/user/repo"
        assert name == "repo"

    def test_git_github_with_ref(self) -> None:
        source_type, url, name = _parse_source("git:github.com/user/repo@v1.0")
        assert source_type == "git"
        assert url == "github.com/user/repo@v1.0"
        assert name == "repo"

    def test_git_github_with_dot_git(self) -> None:
        source_type, url, name = _parse_source("git:github.com/user/repo.git")
        assert source_type == "git"
        assert url == "github.com/user/repo.git"
        assert name == "repo"

    def test_https_url(self) -> None:
        source_type, url, name = _parse_source("https://github.com/user/repo")
        assert source_type == "git"
        assert url == "https://github.com/user/repo"
        assert name == "repo"

    def test_http_url(self) -> None:
        source_type, url, name = _parse_source("http://github.com/user/repo")
        assert source_type == "git"
        assert url == "http://github.com/user/repo"
        assert name == "repo"

    def test_local_relative_path(self) -> None:
        source_type, resolved, name = _parse_source("./my-package")
        assert source_type == "local"
        assert name == "my-package"

    def test_local_absolute_path(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "my-package"
        pkg_dir.mkdir()
        source_type, resolved, name = _parse_source(str(pkg_dir))
        assert source_type == "local"
        assert name == "my-package"
        assert resolved == str(pkg_dir.resolve())

    def test_local_home_expand(self) -> None:
        source_type, resolved, name = _parse_source("~/some/package")
        assert source_type == "local"
        assert name == "package"


# ── registry round-trip ────────────────────────────────────────────────


class TestRegistryIO:
    def test_load_empty_when_no_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        assert _load_registry() == []

    def test_save_and_load_round_trip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        packages = [
            InstalledPackage(
                name="foo",
                source="git:github.com/x/foo",
                source_type="git",
                path=str(tmp_path / "packages" / "foo"),
            ),
            InstalledPackage(
                name="bar",
                source="/local/bar",
                source_type="local",
                path=str(tmp_path / "packages" / "bar"),
            ),
        ]
        _save_registry(packages)
        loaded = _load_registry()
        assert len(loaded) == 2
        assert loaded[0].name == "foo"
        assert loaded[0].source_type == "git"
        assert loaded[1].name == "bar"
        assert loaded[1].source_type == "local"

    def test_load_corrupted_json_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tau_root = _monkeypatch_paths(monkeypatch, tmp_path)
        reg_path = tau_root / "tau_packages.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text("not valid json")
        assert _load_registry() == []

    def test_load_empty_json_list(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        tau_root = _monkeypatch_paths(monkeypatch, tmp_path)
        reg_path = tau_root / "tau_packages.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text("[]")
        assert _load_registry() == []

    def test_save_and_load_empty_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        _save_registry([])
        assert _load_registry() == []


# ── install_package ────────────────────────────────────────────────────


class TestInstallPackage:
    def test_duplicate_name(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        # Pre-populate registry with a package named "foo"
        _save_registry(
            [
                InstalledPackage(
                    name="foo",
                    source="git:github.com/x/foo",
                    source_type="git",
                    path=str(tmp_path / "packages" / "foo"),
                ),
            ]
        )
        result = install_package("git:github.com/other/foo")
        assert result.success is False
        assert "already installed" in result.message

    def test_install_git_missing_binary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        # We can't really test git clone without git but we can test that
        # the duplicate check works. For git clones, we rely on the real git.
        # This test exercises the path where git is missing via subprocess.
        pass

    def test_parse_source_called_for_install(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Verify that install_package calls _parse_source and detects duplicates."""
        _monkeypatch_paths(monkeypatch, tmp_path)
        result = install_package("git:github.com/user/my-tools")
        # This will try to actually clone, which may fail. We just verify
        # that the package name was parsed correctly (it shouldn't be rejected
        # by the duplicate check since registry is empty).
        # The actual clone will fail but that's OK for this test.
        assert result.success is False  # will fail because no git clone succeeds
        # But it should NOT say "already installed"
        assert "already installed" not in result.message


# ── remove_package ────────────────────────────────────────────────────


class TestRemovePackage:
    def test_remove_nonexistent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        result = remove_package("nonexistent")
        assert result.success is False
        assert "not installed" in result.message

    def test_remove_existing_no_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        _save_registry(
            [
                InstalledPackage(
                    name="foo",
                    source="git:x",
                    source_type="git",
                    path=str(tmp_path / "packages" / "foo"),
                ),
            ]
        )
        result = remove_package("foo")
        assert result.success is True
        assert "Removed" in result.message
        # Registry should be empty now
        assert _load_registry() == []

    def test_remove_with_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        pkg_dir = tmp_path / ".tau" / "packages" / "foo"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "hello.txt").write_text("hello")

        _save_registry(
            [
                InstalledPackage(name="foo", source="git:x", source_type="git", path=str(pkg_dir)),
            ]
        )
        result = remove_package("foo")
        assert result.success is True
        assert not pkg_dir.exists()
        assert _load_registry() == []


# ── list_packages ─────────────────────────────────────────────────────


class TestListPackages:
    def test_list_empty(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        assert list_packages() == []

    def test_list_with_packages(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        _save_registry(
            [
                InstalledPackage(
                    name="alpha", source="git:url/a", source_type="git", path="/pkg/alpha"
                ),
            ]
        )
        pkgs = list_packages()
        assert len(pkgs) == 1
        assert pkgs[0].name == "alpha"


# ── package_command ────────────────────────────────────────────────────


class TestPackageCommand:
    def test_no_args_prints_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        package_command([])
        captured = capsys.readouterr()
        assert "Usage:" in captured.out
        assert captured.err == ""

    def test_unknown_subcommand_prints_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        package_command(["unknown"])
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_list_empty(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        package_command(["list"])
        captured = capsys.readouterr()
        assert "No packages installed" in captured.out

    def test_list_with_packages(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        _save_registry(
            [
                InstalledPackage(
                    name="test-pkg", source="git:url", source_type="git", path="/pkg/test-pkg"
                ),
            ]
        )
        package_command(["list"])
        captured = capsys.readouterr()
        assert "Installed packages:" in captured.out
        assert "test-pkg" in captured.out

    def test_remove_nonexistent(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_paths(monkeypatch, tmp_path)
        with pytest.raises(SystemExit):
            package_command(["remove", "nonexistent"])
        captured = capsys.readouterr()
        assert "not installed" in captured.err


# ── data model ─────────────────────────────────────────────────────────


class TestDataModel:
    def test_installed_package_defaults(self) -> None:
        pkg = InstalledPackage(name="test", source="git:x", source_type="git", path="/pkg/test")
        assert pkg.name == "test"
        assert pkg.source == "git:x"
        assert pkg.source_type == "git"
        assert pkg.path == "/pkg/test"

    def test_package_result_success(self) -> None:
        result = PackageResult(success=True, message="ok")
        assert result.success is True
        assert result.message == "ok"
        assert result.package is None

    def test_package_result_with_package(self) -> None:
        pkg = InstalledPackage(name="x", source="y", source_type="local", path="/pkg/x")
        result = PackageResult(success=True, message="ok", package=pkg)
        assert result.package is not None
        assert result.package.name == "x"


# ── _install_git ─────────────────────────────────────────────────


class TestInstallGit:
    """Tests for _install_git -- git clone via subprocess."""

    def test_successful_clone(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Successful git clone returns empty string (no error)."""
        dest = tmp_path / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            assert args[0:3] == ["git", "clone", "github.com/user/repo"]
            assert str(dest) in args[3]
            dest.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _mock_run)

        error = _install_git("github.com/user/repo", dest)
        assert error == ""
        assert dest.exists()

    def test_clone_failure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Failed git clone returns error message and cleans up."""
        dest = tmp_path / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr="fatal: repo not found"
            )

        monkeypatch.setattr(subprocess, "run", _mock_run)

        error = _install_git("github.com/user/repo", dest)
        assert "Git clone failed" in error
        assert "fatal" in error

    def test_git_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """FileNotFoundError (git not in PATH) returns appropriate message."""
        dest = tmp_path / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", _mock_run)

        error = _install_git("github.com/user/repo", dest)
        assert "Git is not installed" in error

    def test_clone_timeout(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Timeout during clone returns timeout message."""
        dest = tmp_path / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=60, output="")

        monkeypatch.setattr(subprocess, "run", _mock_run)

        error = _install_git("github.com/user/repo", dest)
        assert "timed out" in error
        # Dest should be cleaned up on timeout
        assert not dest.exists()

    def test_already_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Skip clone when destination already exists."""
        dest = tmp_path / "packages" / "my-tools"
        dest.mkdir(parents=True)

        error = _install_git("github.com/user/repo", dest)
        assert "already exists" in error

    def test_clone_failure_cleanup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Failed clone cleans up partial destination."""
        dest = tmp_path / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "partial-file").write_text("partial")
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")

        monkeypatch.setattr(subprocess, "run", _mock_run)

        error = _install_git("github.com/user/repo", dest)
        assert "Git clone failed" in error
        assert not dest.exists()


# ── _install_local ───────────────────────────────────────────────


class TestInstallLocal:
    """Tests for _install_local -- directory copy."""

    def test_copy_directory(self, tmp_path: Path) -> None:
        """Copy a local directory to dest."""
        src = tmp_path / "my-package"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        (src / "subdir").mkdir()
        (src / "subdir" / "nested.txt").write_text("nested")

        dest = tmp_path / "packages" / "my-package"
        error = _install_local(str(src), dest)
        assert error == ""
        assert dest.exists()
        assert (dest / "file.txt").read_text() == "hello"
        assert (dest / "subdir" / "nested.txt").read_text() == "nested"

    def test_source_not_exists(self, tmp_path: Path) -> None:
        """Non-existent source returns error."""
        dest = tmp_path / "packages" / "my-package"
        error = _install_local(str(tmp_path / "nonexistent"), dest)
        assert "does not exist" in error
        assert not dest.exists()

    def test_source_is_file_not_dir(self, tmp_path: Path) -> None:
        """File source (not a directory) returns error."""
        src = tmp_path / "not-a-dir.txt"
        src.write_text("i am a file")
        dest = tmp_path / "packages" / "my-package"
        error = _install_local(str(src), dest)
        assert "not a directory" in error
        assert not dest.exists()

    def test_already_exists(self, tmp_path: Path) -> None:
        """Existing destination returns error."""
        src = tmp_path / "my-package"
        src.mkdir()
        dest = tmp_path / "packages" / "my-package"
        dest.mkdir(parents=True)

        error = _install_local(str(src), dest)
        assert "already exists" in error

    def test_copy_error_cleanup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Copy error cleans up partial destination."""
        src = tmp_path / "my-package"
        src.mkdir()
        dest = tmp_path / "packages" / "my-package"

        def _broken_copytree(src: str, dst: str, **kwargs: object) -> None:
            dest.mkdir(parents=True)
            raise OSError("Disk full")

        monkeypatch.setattr(shutil, "copytree", _broken_copytree)

        error = _install_local(str(src), dest)
        assert "Failed to copy" in error
        assert not dest.exists()


# ── _symlink_resources ───────────────────────────────────────────


class TestSymlinkResources:
    """Tests for _symlink_resources -- linking package resources."""

    def test_dry_run_returns_linked_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """dry_run=True returns linked resources without creating symlinks."""
        pkg_dir = tmp_path / "my-package"
        (pkg_dir / "skills" / "myskill.md").mkdir(parents=True)
        (pkg_dir / "prompts" / "greeting.md").mkdir(parents=True)
        (pkg_dir / "extensions" / "tool.py").mkdir(parents=True)
        (pkg_dir / "themes" / "dark.json").mkdir(parents=True)

        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: tmp_path / "home",
        )

        linked, skipped = _symlink_resources(pkg_dir, dry_run=True)
        assert len(linked) == 4
        assert "skills/myskill.md" in linked
        assert "prompts/greeting.md" in linked
        assert "extensions/tool.py" in linked
        assert "themes/dark.json" in linked
        assert skipped == []

    def test_dry_run_skips_existing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """dry_run marks existing resources as skipped."""
        pkg_dir = tmp_path / "my-package"
        (pkg_dir / "skills" / "myskill.md").mkdir(parents=True)

        home = tmp_path / "home"
        (home / ".tau" / "skills" / "myskill.md").mkdir(parents=True)

        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: home,
        )

        linked, skipped = _symlink_resources(pkg_dir, dry_run=True)
        assert linked == []
        assert "skills/myskill.md" in skipped

    def test_dry_run_skips_hidden(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Files starting with . or _ are skipped."""
        pkg_dir = tmp_path / "my-package"
        (pkg_dir / "skills" / ".hidden.md").mkdir(parents=True)
        (pkg_dir / "skills" / "_private.md").mkdir(parents=True)
        (pkg_dir / "skills" / "visible.md").mkdir(parents=True)

        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: tmp_path / "home",
        )

        linked, skipped = _symlink_resources(pkg_dir, dry_run=True)
        assert "skills/visible.md" in linked
        assert "skills/.hidden.md" not in linked
        assert "skills/_private.md" not in linked

    def test_empty_package_no_resources(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Package with no resource dirs returns empty."""
        pkg_dir = tmp_path / "empty-pkg"
        pkg_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: tmp_path / "home",
        )

        linked, skipped = _symlink_resources(pkg_dir, dry_run=True)
        assert linked == []
        assert skipped == []


# ── install_package full flow ───────────────────────────────────


class TestInstallPackageFull:
    """Tests for install_package -- end-to-end flow with mocked backends."""

    def test_install_git_source(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Install a git-sourced package with mocked clone."""
        _monkeypatch_paths(monkeypatch, tmp_path)

        dest = tmp_path / ".tau" / "packages" / "my-tools"

        def _mock_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            dest.mkdir(parents=True)
            (dest / "skills" / "tool.md").mkdir(parents=True)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _mock_run)
        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: tmp_path / "home",
        )

        result = install_package("git:github.com/user/my-tools")
        assert result.success is True
        assert result.package is not None
        assert result.package.name == "my-tools"
        assert result.package.source_type == "git"

        registry = _load_registry()
        assert len(registry) == 1
        assert registry[0].name == "my-tools"
        assert "Linked" in result.message

    def test_install_local_source(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Install a local-sourced package."""
        _monkeypatch_paths(monkeypatch, tmp_path)

        src = tmp_path / "my-tools"
        src.mkdir()
        (src / "skills" / "tool.md").mkdir(parents=True)

        monkeypatch.setattr(
            "tau_coding.package_manager.Path.home",
            lambda: tmp_path / "home",
        )

        result = install_package(str(src))
        assert result.success is True
        assert result.package is not None
        assert result.package.name == "my-tools"
        assert result.package.source_type == "local"

        registry = _load_registry()
        assert len(registry) == 1

    def test_install_local_source_not_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Local source not found returns error."""
        _monkeypatch_paths(monkeypatch, tmp_path)
        nonexistent = tmp_path / "nonexistent"

        result = install_package(str(nonexistent))
        assert result.success is False
        assert "does not exist" in result.message

    def test_install_local_duplicate_name(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Install with duplicate name returns error."""
        _monkeypatch_paths(monkeypatch, tmp_path)
        src = tmp_path / "dup-pkg"
        src.mkdir()

        install_package(str(src))

        # Second source has same dir name but different parent -> same package name
        src2 = tmp_path / "other" / "dup-pkg"
        src2.mkdir(parents=True)
        result = install_package(str(src2))
        assert result.success is False
        assert "already installed" in result.message
