"""Path-sandbox validation and argument-extraction helpers for Tau coding tools.

Extracted from tools.py to reduce module size.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

from tau_agent.types import JSONValue
from tau_coding.harness import SandboxConfig
from tau_coding.tools_types import ToolInputError


def _validate_path_in_sandbox(
    path: Path,
    sandbox: SandboxConfig | None,
    cwd: Path,
) -> None:
    """Validate a resolved path against the sandbox policy.

    In strict mode the path must resolve under the working directory *cwd*
    or under one of the explicitly allowed directories from the sandbox
    config.  Raises ``ToolInputError`` when the path is outside the sandbox.
    In permissive mode or when *sandbox* is ``None`` the function is a no-op.
    """
    if sandbox is None or sandbox.mode != "strict":
        return

    resolved = path.resolve()
    cwd_resolved = cwd.resolve()

    # 1. Check allowed_paths first
    for allowed in sandbox.allowed_paths:
        allowed_path = (cwd / allowed).resolve()
        try:
            resolved.relative_to(allowed_path)
            return
        except ValueError:
            continue

    # 2. Allow ~/.tau paths when flag is set
    if sandbox.allow_home_tau:
        tau_home = Path.home() / ".tau"
        try:
            resolved.relative_to(tau_home.resolve())
            return
        except ValueError:
            pass

    # 3. Allow system temp directory when flag is set
    if sandbox.allow_temp:
        temp_dir = Path(tempfile.gettempdir()).resolve()
        try:
            resolved.relative_to(temp_dir)
            return
        except ValueError:
            pass

    # 4. Check against the working directory
    try:
        resolved.relative_to(cwd_resolved)
        return
    except ValueError:
        pass

    raise ToolInputError(
        f"Path '{path}' resolves outside the working directory '{cwd}'.\n"
        "To allow it, add the path to [sandbox].allowed_paths in your harness config,\n"
        "or use --unsafe to disable sandboxing for this session."
    )


def _str_arg(arguments: Mapping[str, JSONValue], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ToolInputError(f"{name} must be a string")
    return value


def _path_arg(arguments: Mapping[str, JSONValue], name: str, *, cwd: Path) -> Path:
    value = _str_arg(arguments, name)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path


def _optional_int_arg(arguments: Mapping[str, JSONValue], name: str) -> int | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer")
    return value


def _optional_float_arg(arguments: Mapping[str, JSONValue], name: str) -> float | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ToolInputError(f"{name} must be a number")
    return float(value)
