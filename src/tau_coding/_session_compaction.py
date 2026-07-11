"""Compaction mixin for CodingSession."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tau_agent.messages import AgentMessage, UserMessage
from tau_agent.session import CompactionEntry, LeafEntry
from tau_ai.events import ProviderErrorEvent, ProviderResponseEndEvent, ProviderTextDeltaEvent
from tau_coding._session_persistence import _PersistenceMixin
from tau_coding.branch_summary import summarize_branch_messages_with_model
from tau_coding.context_window import (
    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
    SUMMARIZATION_SYSTEM_PROMPT,
    build_compaction_summary_prompt,
    summarize_messages_for_compaction,
)
from tau_coding.diagnostics import AgentCallDiagnosticContext
from tau_coding.session_compaction import (
    _first_recent_context_index,
)
from tau_coding.session_models import CompactionPlan

if TYPE_CHECKING:
    from tau_agent import AgentHarness
    from tau_agent.session import SessionState
    from tau_coding.diagnostics import AgentCallDiagnosticLogger
    from tau_coding.session_models import CodingSessionConfig


class _CompactionMixin(_PersistenceMixin):
    """Compaction operations for CodingSession.

    Depends on ``_PersistenceMixin`` for ``self._append_session_entry()``,
    ``self._refresh_persisted_state()``, etc.

    Mixin — accesses ``self`` for CodingSession internals set in ``__init__``.
    """

    # Attributes accessed from CodingSession — declared for mypy strict
    _diagnostic_logger: AgentCallDiagnosticLogger
    model: str
    _config: CodingSessionConfig
    _harness: AgentHarness
    _state: SessionState
    auto_compact_token_threshold: int | None
    context_token_estimate: int
    _last_diagnostic_log_path: Path | None

    async def compact(self, instructions: str | None = None) -> str:
        """Generate a manual compaction summary and rebuild active context."""
        plan = self._manual_compaction_plan()
        summary = await self._generate_compaction_summary(
            plan.messages_to_summarize,
            custom_instructions=instructions,
        )
        compaction = await self._append_compaction(
            summary,
            replace_entry_ids=plan.replace_entry_ids,
        )
        return f"Compacted {len(compaction.replaces_entry_ids)} context entries."

    # -- auto-compaction -------------------------------------------------------

    async def _try_auto_compact(
        self,
        *,
        context: AgentCallDiagnosticContext,
        phase: str,
    ) -> bool:
        try:
            return await self._maybe_auto_compact()
        except Exception as exc:  # noqa: BLE001 - automatic compaction must not lose a turn
            self._last_diagnostic_log_path = self._diagnostic_logger.log_exception(
                context=context,
                phase=phase,
                exc=exc,
            )
            return False

    async def _try_overflow_compact(
        self,
        *,
        context: AgentCallDiagnosticContext,
    ) -> bool:
        try:
            plan = self._recent_preserving_compaction_plan()
            if plan is None:
                return False
            summary = await self._generate_compaction_summary(plan.messages_to_summarize)
            await self._append_compaction(summary, replace_entry_ids=plan.replace_entry_ids)
            return True
        except Exception as exc:  # noqa: BLE001 - the original overflow remains visible
            self._last_diagnostic_log_path = self._diagnostic_logger.log_exception(
                context=context,
                phase="overflow_compact",
                exc=exc,
            )
            return False

    async def _maybe_auto_compact(self) -> bool:
        threshold = self.auto_compact_token_threshold
        if threshold is None or threshold <= 0:
            return False
        if len(self._state.context_entry_ids) < 2:
            return False
        if self.context_token_estimate <= threshold:
            return False
        plan = self._recent_preserving_compaction_plan()
        if plan is None:
            return False
        summary = await self._generate_compaction_summary(plan.messages_to_summarize)
        await self._append_compaction(summary, replace_entry_ids=plan.replace_entry_ids)
        return True

    async def _generate_compaction_summary(
        self,
        messages: tuple[AgentMessage, ...],
        *,
        custom_instructions: str | None = None,
    ) -> str:
        prompt = build_compaction_summary_prompt(
            messages,
            custom_instructions=custom_instructions,
        )
        text_parts: list[str] = []
        final_text: str | None = None
        summary_messages: list[AgentMessage] = [UserMessage(content=prompt)]
        async for event in self._harness.config.provider.stream_response(
            model=self.model,
            system=SUMMARIZATION_SYSTEM_PROMPT,
            messages=summary_messages,
            tools=[],
        ):
            if isinstance(event, ProviderTextDeltaEvent):
                text_parts.append(event.delta)
            elif isinstance(event, ProviderResponseEndEvent):
                final_text = event.message.content
            elif isinstance(event, ProviderErrorEvent):
                details = f": {event.data}" if event.data is not None else ""
                raise RuntimeError(f"Compaction summarization failed: {event.message}{details}")

        summary = (final_text if final_text is not None else "".join(text_parts)).strip()
        if not summary:
            raise RuntimeError("Compaction summarization returned an empty summary")
        return summary

    async def _summarize_branch_messages(
        self,
        messages: tuple[AgentMessage, ...],
        *,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
    ) -> str:
        try:
            summary = await summarize_branch_messages_with_model(
                provider=self._harness.config.provider,
                model=self.model,
                messages=messages,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )
        except Exception:
            summary = None
        return summary or summarize_messages_for_compaction(messages)

    # -- compaction planning ---------------------------------------------------

    def _manual_compaction_plan(self) -> CompactionPlan:
        rows = self._active_context_rows()
        if not rows:
            raise ValueError("No active context messages to compact")
        return CompactionPlan(
            replace_entry_ids=tuple(entry_id for entry_id, _message in rows),
            messages_to_summarize=tuple(message for _entry_id, message in rows),
        )

    def _recent_preserving_compaction_plan(self) -> CompactionPlan | None:
        rows = self._active_context_rows()
        if len(rows) < 2:
            return None

        first_kept_index = _first_recent_context_index(
            rows,
            keep_recent_tokens=DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
        )
        if first_kept_index <= 0:
            return None

        replaced = rows[:first_kept_index]
        if not replaced:
            return None
        return CompactionPlan(
            replace_entry_ids=tuple(entry_id for entry_id, _message in replaced),
            messages_to_summarize=tuple(message for _entry_id, message in replaced),
        )

    def _active_context_rows(self) -> tuple[tuple[str, AgentMessage], ...]:
        return tuple(zip(self._state.context_entry_ids, self._state.messages, strict=True))

    async def _append_compaction(
        self,
        summary: str,
        *,
        replace_entry_ids: tuple[str, ...],
    ) -> CompactionEntry:
        if not replace_entry_ids:
            raise ValueError("No active context messages to compact")

        compaction = CompactionEntry(
            parent_id=self._last_parent_id,
            summary=summary,
            replaces_entry_ids=list(replace_entry_ids),
        )
        await self._append_session_entry(compaction)
        leaf = LeafEntry(parent_id=compaction.id, entry_id=compaction.id)
        await self._append_session_entry(leaf)
        self._last_parent_id = compaction.id

        await self._refresh_persisted_state(leaf_id=compaction.id)
        self._harness.replace_messages(self._state.messages)
        self._invalidate_context_usage_cache()  # type: ignore[attr-defined]
        return compaction
