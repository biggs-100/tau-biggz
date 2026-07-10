"""Persistence mixin for CodingSession."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tau_agent import AgentHarness, AgentHarnessConfig
from tau_agent.session import (
    LeafEntry,
    MessageEntry,
    SessionState,
)
from tau_agent.session.entries import SessionEntry

from tau_coding.session_storage import _append_session_entry_sync
from tau_coding.session_tree import _detach_missing_parents
from tau_coding.session_tool_repair import _interrupted_tool_repair_plan
from tau_coding.session_utils import _auto_session_name_from_text

if TYPE_CHECKING:
    from tau_coding.session import CodingSession


class _PersistenceMixin:
    """Persistence operations for CodingSession.

    Mixin — accesses ``self`` for CodingSession internals (``self._config``,
    ``self._state``, ``self._harness``, etc.) set in ``__init__``.
    """

    # -- session-name helpers --------------------------------------------------

    async def _auto_name_session(self, first_message: str) -> None:
        """Generate a short session title from the first user message."""
        if self.session_title is not None:
            return
        name = _auto_session_name_from_text(first_message)
        if name and self._config.session_id is not None and self._config.session_manager is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                title=name,
            )

    # -- state persistence -----------------------------------------------------

    async def _refresh_persisted_state(self, *, leaf_id: str | None) -> None:
        entries = await self._read_session_entries()
        self._state = SessionState.from_entries(entries, leaf_id=leaf_id)
        if self._config.session_id is not None and self._config.session_manager is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                model=self.model,
                provider_name=self.provider_name,
            )

    async def _read_session_entries(self) -> list[SessionEntry]:
        """Read stored entries, detaching roots imported from external history."""
        return _detach_missing_parents(await self._config.storage.read_all())

    async def _append_session_entry(self, entry: SessionEntry) -> None:
        """Append one durable entry after flushing deferred session metadata."""
        await self._ensure_session_initialized()
        await self._config.storage.append(entry)

    async def _ensure_session_initialized(self) -> None:
        if not self._pending_initial_entries:
            return
        await self._write_pending_initial_entries()
        if self._config.index_on_first_persist:
            self._index_current_session()

    async def _write_pending_initial_entries(self) -> None:
        for entry in self._pending_initial_entries:
            await self._config.storage.append(entry)
        self._pending_initial_entries = ()

    def _ensure_session_file_initialized(self) -> None:
        if not self._pending_initial_entries:
            return
        for entry in self._pending_initial_entries:
            _append_session_entry_sync(self._config.storage, entry)
        self._pending_initial_entries = ()

    def _index_current_session(self) -> None:
        if self._config.session_id is None or self._config.session_manager is None:
            return
        existing = self._config.session_manager.get_session(self._config.session_id)
        if existing is not None:
            return
        self._config.session_manager.create_session(
            cwd=self.cwd,
            model=self.model,
            provider_name=self.provider_name,
            session_id=self._config.session_id,
        )

    # -- message persistence ---------------------------------------------------

    async def _persist_loaded_interrupted_tool_repairs(self) -> None:
        """Persist repairs for loaded sessions with dangling tool calls.

        Older Tau builds repaired interrupted tool-call transcripts only in the
        in-memory harness. If the app was later resumed from JSONL, the synthetic
        tool result was absent and providers rejected the whole transcript. Repair
        the active branch on load so resume/tree branches are durable and
        provider-safe.
        """
        repair = _interrupted_tool_repair_plan(
            self._state.messages,
            context_entry_ids=self._state.context_entry_ids,
        )
        if repair is None:
            return

        parent_id, suffix = repair
        for message in suffix:
            entry = MessageEntry(parent_id=parent_id, message=message)
            await self._append_session_entry(entry)
            parent_id = entry.id
        leaf = LeafEntry(parent_id=parent_id, entry_id=parent_id)
        await self._append_session_entry(leaf)
        self._last_parent_id = parent_id
        await self._refresh_persisted_state(leaf_id=parent_id)
        self._harness = AgentHarness(
            AgentHarnessConfig(
                provider=self._harness.config.provider,
                model=self._harness.config.model,
                system=self._harness.config.system,
                tools=self._harness.config.tools,
                max_turns=self._harness.config.max_turns,
                queue_mode=self._harness.config.queue_mode,
            ),
            messages=self._state.messages,
        )

    async def _persist_messages_since(self, persisted_count: int) -> int:
        """Persist completed harness messages after ``persisted_count``.

        Message lifecycle events are the durable-message boundary. Each persisted
        message advances the append-only tree and records a leaf pointer so tree
        navigation can observe the current branch while a run is still active.
        """
        new_messages = self._harness.messages[persisted_count:]
        if not new_messages:
            return persisted_count

        for message in new_messages:
            entry = MessageEntry(parent_id=self._last_parent_id, message=message)
            await self._append_session_entry(entry)
            self._last_parent_id = entry.id
            leaf = LeafEntry(parent_id=entry.id, entry_id=entry.id)
            await self._append_session_entry(leaf)

        await self._refresh_persisted_state(leaf_id=self._last_parent_id)
        self._invalidate_context_usage_cache()
        return persisted_count + len(new_messages)
