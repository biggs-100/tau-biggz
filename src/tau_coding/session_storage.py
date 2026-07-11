"""Storage-path helpers and synchronous storage convenience."""

from __future__ import annotations

from pathlib import Path

from tau_agent.session import JsonlSessionStorage, SessionStorage
from tau_agent.session.entries import SessionEntry
from tau_agent.session.jsonl import entry_to_json_line
from tau_coding.paths import TauPaths


def default_session_path(cwd: Path) -> Path:
    """Return Tau's default user-home session path for a project cwd."""
    return TauPaths().default_session_path(cwd)


def jsonl_session_storage(path: str | Path) -> JsonlSessionStorage:
    """Convenience factory for local JSONL coding-session storage."""
    return JsonlSessionStorage(path)


def _append_session_entry_sync(storage: SessionStorage, entry: SessionEntry) -> None:
    """Append an entry synchronously for slash commands that cannot await storage."""
    if isinstance(storage, JsonlSessionStorage):
        storage.path.parent.mkdir(parents=True, exist_ok=True)
        with storage.path.open("a", encoding="utf-8") as file:
            file.write(entry_to_json_line(entry))
        return

    raise RuntimeError("Session storage does not support synchronous initialization")
