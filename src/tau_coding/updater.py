"""Upgrade Tau with the package manager that owns its environment."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Literal

from tau_coding.update_check import PYPI_PACKAGE_NAME, fetch_latest_pypi_version

InstallMethod = Literal["uv-tool", "pipx", "pip", "unknown"]


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Result of trying to upgrade Tau."""

    command: tuple[str, ...] | None = None
    stdout: str = ""
    stderr: str = ""
    failures: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.command is not None


def _detect_install_method() -> tuple[InstallMethod, str | None]:
    """Detect how Tau was installed by examining dist-info INSTALLER and paths."""
    try:
        dist = distribution(PYPI_PACKAGE_NAME)
    except PackageNotFoundError:
        return ("unknown", None)

    installer: str | None = None
    direct_url: str | None = None

    for direct_file in ("INSTALLER", "direct_url.json"):
        try:
            text = dist.read_text(direct_file)
            if text:
                content = text.strip()
                if direct_file == "INSTALLER":
                    installer = content
                else:
                    direct_url = content
        except Exception:
            pass

    if direct_url:
        return ("unknown", f"direct URL install detected: {direct_url[:80]}")

    if installer == "uv":
        return ("uv-tool", None)
    if installer == "pipx":
        return ("pipx", None)
    if installer in ("pip", "hatchling", "flit_core", "pdm"):
        return ("pip", None)

    if installer:
        return ("unknown", f"unrecognized installer: {installer}")

    return ("unknown", "no INSTALLER file found")


def update_tau(
    *,
    python_executable: str | None = None,
) -> UpdateResult:
    """Upgrade Tau by detecting the install method and running the appropriate command.

    Returns an UpdateResult describing what was attempted.
    """
    method, failure = _detect_install_method()
    if failure:
        return UpdateResult(failures=(failure,))

    python = python_executable or sys.executable

    if method == "uv-tool":
        cmd = ("uv", "tool", "upgrade", PYPI_PACKAGE_NAME)
    elif method == "pipx":
        cmd = ("pipx", "upgrade", PYPI_PACKAGE_NAME)
    elif method == "pip":
        cmd = (python, "-m", "pip", "install", "--upgrade", PYPI_PACKAGE_NAME)
    else:
        return UpdateResult(
            failures=(
                "Cannot determine how Tau was installed. "
                f"Try: uv tool upgrade {PYPI_PACKAGE_NAME}",
            )
        )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return UpdateResult(
            command=cmd,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except FileNotFoundError:
        return UpdateResult(
            failures=(f"'{cmd[0]}' not found. Try: uv tool upgrade {PYPI_PACKAGE_NAME}",)
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(failures=("Upgrade timed out after 120 seconds.",))
    except OSError as exc:
        return UpdateResult(failures=(f"Failed to run upgrade: {exc}",))


def format_update_result(result: UpdateResult) -> str:
    """Format an UpdateResult for display."""
    if result.succeeded:
        lines = [f"Ran: {' '.join(result.command)}"]
        if result.stdout:
            lines.append(result.stdout.strip())
        if result.stderr:
            lines.append(result.stderr.strip())
        return "\n".join(lines)
    if result.failures:
        return "\n".join(f"• {f}" for f in result.failures)
    return "No update method available."
