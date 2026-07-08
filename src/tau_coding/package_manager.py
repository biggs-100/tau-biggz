"""Tau package manager — install, remove, and list packages.

A package is a directory with any of these subdirectories:

- ``extensions/`` — ``.py`` files loaded as Tau extensions
- ``skills/`` — markdown skill files (``SKILL.md`` or ``.md``)
- ``prompts/`` — ``.md`` files loaded as prompt templates
- ``themes/`` — ``.json`` theme files

Sources:

- ``git:github.com/user/repo[@ref]`` — clone from git
- ``https://...`` / ``http://...`` — clone from URL
- Local path (absolute or relative) — copy to packages dir
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


PACKAGES_DIR_NAME = "packages"
PACKAGES_REGISTRY_NAME = "tau_packages.json"


# ── data model ──────────────────────────────────────────────────────────


@dataclass
class InstalledPackage:
    """One installed package entry."""

    name: str
    source: str
    source_type: Literal["git", "local"]
    path: str  # absolute path to the package directory


@dataclass
class PackageResult:
    """Result of a package operation."""

    success: bool
    message: str
    package: InstalledPackage | None = None


# ── paths ───────────────────────────────────────────────────────────────


def _packages_dir() -> Path:
    return Path.home() / ".tau" / PACKAGES_DIR_NAME


def _registry_path() -> Path:
    return Path.home() / ".tau" / PACKAGES_REGISTRY_NAME


# ── registry I/O ────────────────────────────────────────────────────────


def _load_registry() -> list[InstalledPackage]:
    """Load installed packages from the registry file."""
    path = _registry_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [InstalledPackage(**entry) for entry in raw]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def _save_registry(packages: list[InstalledPackage]) -> None:
    """Persist installed packages to the registry file."""
    raw = [
        {
            "name": p.name,
            "source": p.source,
            "source_type": p.source_type,
            "path": p.path,
        }
        for p in packages
    ]
    _registry_path().write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ── source parsing ──────────────────────────────────────────────────────


def _parse_source(source: str) -> tuple[Literal["git", "local"], str, str]:
    """Parse a package source string into (type, url/name, name).

    Returns ``(type, resolved_source, package_name)``.
    """
    if source.startswith("git:") or source.startswith("https://") or source.startswith("http://"):
        # Strip git: prefix for actual git operations
        git_url = source.removeprefix("git:")
        # Derive package name from URL: user/repo, last path component
        name = git_url.rstrip("/").rsplit("/", 1)[-1]
        # Remove .git suffix and @ref
        name = name.removesuffix(".git").split("@")[0]
        return ("git", git_url, name)

    # Local path
    resolved = Path(source).expanduser().resolve()
    name = resolved.name
    return ("local", str(resolved), name)


# ── install ─────────────────────────────────────────────────────────────


def _install_git(source: str, dest: Path) -> str:
    """Clone a git repository to *dest*. Returns a status message."""
    if dest.exists():
        return f"Package already exists at {dest}. Remove it first with `tau package remove`."

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", source, str(dest)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            # Clean up partial clone on failure
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            return f"Git clone failed: {error}"
    except FileNotFoundError:
        return "Git is not installed or not in PATH."
    except subprocess.TimeoutExpired:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return "Git clone timed out."

    return ""


def _install_local(source: str, dest: Path) -> str:
    """Copy a local directory to *dest*. Returns a status message."""
    src = Path(source)
    if not src.exists():
        return f"Source path does not exist: {source}"
    if not src.is_dir():
        return f"Source path is not a directory: {source}"

    if dest.exists():
        return f"Package already exists at {dest}. Remove it first."

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(src, dest, symlinks=True)
    except OSError as exc:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return f"Failed to copy package: {exc}"

    return ""


def _symlink_resources(pkg_dir: Path, *, dry_run: bool = False) -> tuple[list[str], list[str]]:
    """Symlink package resources into Tau's user directories.

    Returns (linked, skipped) lists of resource paths.
    """
    linked: list[str] = []
    skipped: list[str] = []

    resource_dirs = {
        "extensions": Path.home() / ".tau" / "extensions",
        "skills": Path.home() / ".tau" / "skills",
        "prompts": Path.home() / ".tau" / "prompts",
        "themes": Path.home() / ".tau" / "themes",
    }

    for resource_name, target_dir in resource_dirs.items():
        src_dir = pkg_dir / resource_name
        if not src_dir.is_dir():
            continue

        target_dir.mkdir(parents=True, exist_ok=True)

        for item in sorted(src_dir.iterdir()):
            if item.name.startswith(".") or item.name.startswith("_"):
                continue

            link_path = target_dir / item.name
            if link_path.exists() or link_path.is_symlink():
                skipped.append(f"{resource_name}/{item.name}")
                continue

            if not dry_run:
                try:
                    # Use symlinks on Unix, copy on Windows
                    if sys.platform == "win32":
                        if item.is_dir():
                            shutil.copytree(item, link_path, dirs_exist_ok=False)
                        else:
                            shutil.copy2(item, link_path)
                    else:
                        link_path.symlink_to(item)
                except OSError as exc:
                    skipped.append(f"{resource_name}/{item.name} ({exc})")
                    continue

            linked.append(f"{resource_name}/{item.name}")

    return linked, skipped


def install_package(source: str) -> PackageResult:
    """Install a package from *source*.

    Supports ``git:`` URLs and local paths.
    """
    source_type, resolved_source, name = _parse_source(source)
    registry = _load_registry()

    # Check for duplicate name
    if any(p.name == name for p in registry):
        return PackageResult(False, f"Package '{name}' is already installed. Remove it first.")

    dest = _packages_dir() / name

    # Step 1: download / copy
    if source_type == "git":
        error = _install_git(resolved_source, dest)
    else:
        error = _install_local(resolved_source, dest)

    if error:
        return PackageResult(False, error)

    # Step 2: symlink resources
    linked, skipped = _symlink_resources(dest)

    # Step 3: register
    pkg = InstalledPackage(
        name=name,
        source=source,
        source_type=source_type,
        path=str(dest),
    )
    registry.append(pkg)
    _save_registry(registry)

    parts = [f"Installed package '{name}'."]
    if linked:
        parts.append(f" Linked {len(linked)} resources.")
    if skipped:
        parts.append(f" Skipped {len(skipped)} (already exist).")

    return PackageResult(True, " ".join(parts), package=pkg)


# ── remove ──────────────────────────────────────────────────────────────


def remove_package(name: str) -> PackageResult:
    """Remove an installed package by name."""
    registry = _load_registry()
    pkg = next((p for p in registry if p.name == name), None)
    if pkg is None:
        return PackageResult(False, f"Package '{name}' is not installed.")

    pkg_dir = Path(pkg.path)

    # Remove symlinked resources
    if pkg_dir.is_dir():
        resource_dirs = ["extensions", "skills", "prompts", "themes"]
        for resource_name in resource_dirs:
            src_dir = pkg_dir / resource_name
            if not src_dir.is_dir():
                continue

            target_dir = Path.home() / ".tau" / resource_name
            for item in src_dir.iterdir():
                if item.name.startswith("."):
                    continue
                link_path = target_dir / item.name
                if link_path.exists():
                    try:
                        if link_path.is_symlink() or link_path.is_file():
                            link_path.unlink()
                        elif link_path.is_dir():
                            shutil.rmtree(link_path, ignore_errors=True)
                    except OSError:
                        pass

        # Remove package directory
        shutil.rmtree(pkg_dir, ignore_errors=True)

    # Remove from registry
    registry = [p for p in registry if p.name != name]
    _save_registry(registry)

    return PackageResult(True, f"Removed package '{name}'.")


# ── list ────────────────────────────────────────────────────────────────


def list_packages() -> list[InstalledPackage]:
    """Return all installed packages."""
    return _load_registry()


# ── CLI command ─────────────────────────────────────────────────────────


def package_command(args: list[str]) -> None:
    """Handle ``tau package <subcommand> [args]``."""
    if not args:
        _print_usage()
        return

    sub = args[0]

    if sub == "install" and len(args) >= 2:
        result = install_package(args[1])
        _print_result(result)
    elif sub == "remove" and len(args) >= 2:
        result = remove_package(args[1])
        _print_result(result)
    elif sub == "list":
        packages = list_packages()
        if not packages:
            print("No packages installed.")
            return
        print("Installed packages:")
        for pkg in packages:
            print(f"  {pkg.name:30s} {pkg.source}")
    else:
        _print_usage()


def _print_usage() -> None:
    print("Usage: tau package <command> [args]")
    print()
    print("Commands:")
    print("  install <source>    Install a package (git:url or local path)")
    print("  remove <name>       Remove an installed package")
    print("  list                List installed packages")


def _print_result(result: PackageResult) -> None:
    if result.success:
        print(result.message)
    else:
        print(f"Error: {result.message}", file=sys.stderr)
        sys.exit(1)
