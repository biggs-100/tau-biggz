"""Persistent tool-trust store for Tau's approval chain.

The ``TrustStore`` persists tool trust decisions to ``~/.tau/trust.json``.
When a harness approval policy resolves to ``"ask"``, the system checks
this store before blocking execution. Untrusted tools return a structured
denial message that guides the user to trust the tool with ``/trust add``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tau_agent.types import JSONValue
from tau_coding.paths import TauPaths


@dataclass
class TrustStore:
    """Persistent store of trusted tool names.

    Tools in ``trusted_tools`` are automatically allowed when the harness
    approval policy resolves to ``"ask"``.
    """

    version: int = 1
    trusted_tools: set[str] = field(default_factory=set)
    data_dir: Path | None = field(default=None, repr=False)

    # ── path resolution ────────────────────────────────────────────────────

    @staticmethod
    def _default_data_dir() -> Path:
        return TauPaths().home

    def _path(self) -> Path:
        base = self.data_dir if self.data_dir is not None else self._default_data_dir()
        return base / "trust.json"

    # ── load / save ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, data_dir: Path | None = None) -> TrustStore:
        """Load the trust store from disk.

        Returns an empty ``TrustStore`` if the file is missing, corrupt, or
        has an unexpected structure. Never raises.
        """
        store = cls(data_dir=data_dir)
        path = store._path()
        if not path.exists():
            return store

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, TypeError):
            return store

        if not isinstance(raw, dict):
            return store

        tools_raw = raw.get("trusted_tools", [])
        if isinstance(tools_raw, list):
            store.trusted_tools = {str(t) for t in tools_raw if isinstance(t, str)}

        return store

    def save(self) -> None:
        """Write the trust store to disk as canonical JSON.

        Creates the parent directory if it does not exist.
        """
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "version": self.version,
            "trusted_tools": sorted(self.trusted_tools),
        }
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # ── query / mutate ─────────────────────────────────────────────────────

    def is_trusted(self, tool_name: str) -> bool:
        """Return ``True`` if *tool_name* is in the trusted set."""
        return tool_name in self.trusted_tools

    def add(self, tool_name: str) -> bool:
        """Add *tool_name* to the trusted set and persist.

        Returns ``True`` if the tool was newly added, ``False`` if it was
        already trusted.
        """
        if tool_name in self.trusted_tools:
            return False
        self.trusted_tools.add(tool_name)
        self.save()
        return True

    def remove(self, tool_name: str) -> bool:
        """Remove *tool_name* from the trusted set and persist.

        Returns ``True`` if the tool was removed, ``False`` if it was not
        in the trusted set.
        """
        if tool_name not in self.trusted_tools:
            return False
        self.trusted_tools.discard(tool_name)
        self.save()
        return True

    def list_trusted(self) -> set[str]:
        """Return the current set of trusted tool names."""
        return self.trusted_tools.copy()


# ── ask-message formatting ─────────────────────────────────────────────────


def format_ask_message(
    tool_name: str,
    arguments: Mapping[str, JSONValue] | None = None,
) -> str:
    """Format a structured denial message for an untrusted tool.

    The message includes the tool name, up to three argument key-value pairs
    (with values > 60 chars truncated), and guidance for trusting the tool.
    """
    parts: list[str] = [f"Tool '{tool_name}' requires your approval."]

    if arguments:
        items = list(arguments.items())[:3]
        arg_parts: list[str] = []
        for key, value in items:
            val_str = str(value)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            arg_parts.append(f"{key}={val_str}")
        if arg_parts:
            parts.append(f"Args: {', '.join(arg_parts)}.")

    parts.append(f"Use /trust add {tool_name} to trust it.")
    return " ".join(parts)
